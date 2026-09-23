"""视频标注按帧读写测试。

验证 save → load 同一批标注；空列表清除该帧记录；
显式传入 task_id，且任务与视频归属关系不合法时被拒绝。
采用与 ``test_annotation_rollback`` 一致的方式：直接构造 DB 行并调用
``AnnotationService.save_video_annotations`` / ``load_video_annotations``，
以及一条走 HTTP 接口的端到端用例。
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationType,
    AnnotationVideoModel,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.core.exceptions import CustomException


def _make_dataset_and_user() -> int:
    """建一个独立数据集，返回 ds_id。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5A无关数据集")
            db.add(ds)
            await db.flush()
            return ds.id

    return asyncio.run(_run())


def _make_video_and_task() -> tuple[int, int]:
    """建数据集 + 视频 + video_detection 任务，返回 (video_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5A视频帧集")
            db.add(ds)
            await db.flush()
            video = AnnotationVideoModel(
                dataset_id=ds.id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=10.0,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="视频检测任务",
                task_type=AnnotationType.VIDEO_DETECTION,
                status="pending",
                assignees=[],
                classes=[],
            )
            db.add(task)
            await db.flush()
            return video.id, task.id

    return asyncio.run(_run())


def test_video_save_then_load_returns_same_batch():
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    boxes = [
        {"type": "AxisAlignedBox", "class_id": 0,
         "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.7},
        {"id": "b", "type": "AxisAlignedBox", "class_id": 1,
         "x1": 0.3, "y1": 0.4, "x2": 0.6, "y2": 0.9},
    ]

    result = asyncio.run(
        AnnotationService.save_video_annotations(task_id, video_id, 42, boxes, auth)
    )
    assert result["version"] == 1
    assert result["annotation_count"] == 2

    loaded = asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 42))
    assert loaded == boxes


def test_video_save_same_frame_increments_version():
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    r1 = asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 7, [box], auth))
    r2 = asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 7, [box], auth))
    assert r1["version"] == 1
    assert r2["version"] == 2


def test_video_save_empty_list_clears_row():
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 5, [box], auth))
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 5)) == [box]

    # 空列表保存 → 清除该帧记录
    r = asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 5, [], auth))
    assert r["annotation_count"] == 0
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 5)) is None


def _get_video(video_id: int) -> AnnotationVideoModel:
    """读取视频行，用于核对 annotation_count / status。"""

    async def _run():
        async with async_db_session.begin() as db:
            return await db.get(AnnotationVideoModel, video_id)

    return asyncio.run(_run())


def test_video_annotation_count_is_annotated_frames():
    """保存多帧后 annotation_count 应为该视频「已标注帧数」，而非单帧框数。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}
    two_boxes = [box, {"id": "b", "type": "AxisAlignedBox", "class_id": 1,
                       "x1": 0.3, "y1": 0.3, "x2": 0.5, "y2": 0.5}]

    # 共 3 个框分布于 2 帧 → annotation_count 应为 2（已标注帧数）
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 10, two_boxes, auth))
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 20, [box], auth))
    video = _get_video(video_id)
    assert video.annotation_count == 2
    assert video.status == "annotated"


def test_video_annotation_count_recalc_after_clear_and_status():
    """清空某帧后应重算已标注帧数；全部清空后 status 回落为 unannotated。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 5, [box], auth))
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 6, [box], auth))
    assert _get_video(video_id).annotation_count == 2

    # 清空一帧 → 计数回落为 1
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 5, [], auth))
    assert _get_video(video_id).annotation_count == 1

    # 清空最后一帧 → 计数为 0 且 status unannotated
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 6, [], auth))
    video = _get_video(video_id)
    assert video.annotation_count == 0
    assert video.status == "unannotated"


def test_video_annotation_count_scoped_by_task_id():
    """同一视频被多个视频检测任务共享时，annotation_count 仅统计当前 task_id 的已标注帧。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    # 再建一个指向同一数据集/视频的任务
    async def _sibling_task(ds_id: int) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="视频检测任务2",
                task_type=AnnotationType.VIDEO_DETECTION,
                status="pending",
                assignees=[],
                classes=[],
            )
            db.add(task)
            await db.flush()
            return task.id

    video = _get_video(video_id)
    task2_id = asyncio.run(_sibling_task(video.dataset_id))

    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 1, [box], auth))
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 2, [box], auth))
    # 任务1 重算（限定 task_id）应为 2 帧
    assert _get_video(video_id).annotation_count == 2

    # 另一任务只标注第 3 帧 → 重算时限定 task2，只计 1 帧（不计任务1 的 2 帧）
    asyncio.run(AnnotationService.save_video_annotations(task2_id, video_id, 3, [box], auth))
    assert _get_video(video_id).annotation_count == 1


def test_video_save_invalid_task_relation_refused():
    """任务与视频无归属关系（不同数据集）或任务不存在时，保存应被拒绝。"""
    video_id, _ = _make_video_and_task()
    stray_dataset = _make_dataset_and_user()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
           "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    # 不同数据集的任务
    async def _stray_task(ds_id: int) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="无关任务",
                task_type=AnnotationType.VIDEO_DETECTION,
                status="pending",
                assignees=[],
                classes=[],
            )
            db.add(task)
            await db.flush()
            return task.id

    stray_task = asyncio.run(_stray_task(stray_dataset))
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_annotations(stray_task, video_id, 10, [box], auth)
        )
    assert exc.value.status_code == 400

    # 不存在的任务
    with pytest.raises(CustomException) as exc2:
        asyncio.run(
            AnnotationService.save_video_annotations(999999, video_id, 10, [box], auth)
        )
    assert exc2.value.status_code == 400


def test_video_save_and_load_http(test_client, auth_headers, monkeypatch):
    """走 HTTP 接口：POST /video/save 后 GET /video/load 返回同一批。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"vid-http-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    task_resp = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": "视频检测", "task_type": "video_detection"},
        headers=auth_headers,
    )
    assert task_resp.status_code == 200, task_resp.text
    task_id = task_resp.json()["data"]["id"]

    # 直接插入一条视频行（避免依赖真实 ffprobe/对象存储）
    async def _add_video():
        async with async_db_session.begin() as db:
            video = AnnotationVideoModel(
                dataset_id=ds_id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=10.0,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            return video.id

    video_id = asyncio.run(_add_video())

    boxes = [
        {"type": "AxisAlignedBox", "class_id": 0,
         "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
    ]
    save_resp = test_client.post(
        "/api/v1/annotation/anno/video/save",
        json={"task_id": task_id, "video_id": video_id, "frame_index": 42, "annotations": boxes},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()["data"]["version"] == 1

    load_resp = test_client.get(
        "/api/v1/annotation/anno/video/load",
        params={"task_id": task_id, "v_id": video_id, "frame_index": 42},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"] == boxes


def test_video_save_invalid_task_relation_http(test_client, auth_headers, monkeypatch):
    """HTTP 端到端：传入归属关系不存在的 task_id 时保存应被拒绝（fix-1 步骤生效）。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"vid-http-bad-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    task_resp = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": "视频检测", "task_type": "video_detection"},
        headers=auth_headers,
    )
    assert task_resp.status_code == 200, task_resp.text

    async def _add_video():
        async with async_db_session.begin() as db:
            video = AnnotationVideoModel(
                dataset_id=ds_id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=10.0,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            return video.id

    video_id = asyncio.run(_add_video())

    save_resp = test_client.post(
        "/api/v1/annotation/anno/video/save",
        json={"task_id": 999999, "video_id": video_id, "frame_index": 1, "annotations": []},
        headers=auth_headers,
    )
    assert save_resp.status_code == 400, save_resp.text

    load_resp = test_client.get(
        "/api/v1/annotation/anno/video/load",
        params={"task_id": 999999, "v_id": video_id, "frame_index": 1},
        headers=auth_headers,
    )
    assert load_resp.status_code == 400, load_resp.text
