"""视频时间轴事件标注按 video_id 读写与区间/重叠/越界校验测试。

验证 save → load 同一批 ``VideoSegment``；``task_type`` 必须为 ``video_event`` 且任务与
视频归属关系不合法时被拒绝；``start/end``（非法/越界）与 ``label_id`` 非法、
**区间重叠**被拒绝（顺序无关）；空列表即清除；锁冲突（视频被他人锁定）拒绝。
另附导出（JSONL/CSV/annotation_task_id 透传/图片空集守卫前）用例。
采用与 ``test_audio_event_annotation.py`` 一致的方式：直接构造 DB 行并调用 service。
"""
import asyncio
import datetime
import json
import os
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
from app.plugin.module_train.exporter import _export_core, _export_video_event

_DURATION = 10.0

_VIDEO_CLASSES = [
    {"id": 1, "name": "跑步", "color": "#ff0000"},
    {"id": 2, "name": "跳跃", "color": "#00ff00"},
]


def _make_video_and_task(duration: float = _DURATION) -> tuple[int, int]:
    """建数据集 + 视频 + video_event 任务，返回 (video_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="视频事件集")
            db.add(ds)
            await db.flush()
            video = AnnotationVideoModel(
                dataset_id=ds.id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=duration,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="视频事件任务",
                task_type=AnnotationType.VIDEO_EVENT,
                status="pending",
                assignees=[],
                classes=_VIDEO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return video.id, task.id

    return asyncio.run(_run())


def _make_dataset() -> int:
    """建一个独立数据集（用于无关任务归属校验），返回 ds_id。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="视频事件无关数据集")
            db.add(ds)
            await db.flush()
            return ds.id

    return asyncio.run(_run())


def _lock_video(video_id: int, user_id: int) -> None:
    """把视频锁定到指定用户，用于锁冲突用例。"""

    async def _run():
        async with async_db_session.begin() as db:
            video = await db.get(AnnotationVideoModel, video_id)
            video.locked_by = user_id
            video.locked_at = datetime.datetime.now(datetime.UTC)

    asyncio.run(_run())


def test_annotation_type_has_video_event():
    """AnnotationType 枚举应含 VIDEO_EVENT = "video_event"。"""
    assert AnnotationType.VIDEO_EVENT == "video_event"


def test_video_event_save_then_load_returns_same_batch():
    video_id, task_id = _make_video_and_task()
    segments = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.5, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]

    result = asyncio.run(
        AnnotationService.save_video_event_annotations(task_id, video_id, segments, 1)
    )
    assert result["version"] == 1
    assert result["annotation_count"] == 2

    loaded = asyncio.run(AnnotationService.load_video_event_annotations(task_id, video_id))
    assert loaded["annotation_data"] == segments
    assert loaded["version"] == 1


def test_video_event_load_empty_returns_empty():
    video_id, task_id = _make_video_and_task()
    loaded = asyncio.run(AnnotationService.load_video_event_annotations(task_id, video_id))
    assert loaded == {"annotation_data": [], "version": 0}


def test_video_event_save_increments_version():
    video_id, task_id = _make_video_and_task()
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    r1 = asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    r2 = asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert r1["version"] == 1
    assert r2["version"] == 2


def test_video_event_save_empty_list_clears():
    """空列表保存后最新版本标注为空（清除事件标注）。"""
    video_id, task_id = _make_video_and_task()
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    r1 = asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert r1["version"] == 1
    r2 = asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, [], 1))
    assert r2["version"] == 2
    loaded = asyncio.run(AnnotationService.load_video_event_annotations(task_id, video_id))
    assert loaded["annotation_data"] == []
    assert loaded["version"] == 2


def test_video_event_invalid_task_relation_refused():
    """任务与视频无归属关系（不同数据集/错误类型/不存在）时保存或读取应被拒绝。"""
    video_id, _ = _make_video_and_task()
    stray_dataset = _make_dataset()
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    async def _stray_task(ds_id: int, task_type: AnnotationType) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="无关任务",
                task_type=task_type,
                status="pending",
                assignees=[],
                classes=_VIDEO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    # 不同数据集的任务
    stray_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.VIDEO_EVENT))
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(stray_task, video_id, seg, 1))
    assert exc.value.status_code == 400

    # 任务类型不是 video_event（video_detection 任务）也应被拒绝
    det_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.VIDEO_DETECTION))
    with pytest.raises(CustomException) as exc2:
        asyncio.run(AnnotationService.save_video_event_annotations(det_task, video_id, seg, 1))
    assert exc2.value.status_code == 400

    # 不存在的任务
    with pytest.raises(CustomException) as exc3:
        asyncio.run(AnnotationService.save_video_event_annotations(999999, video_id, seg, 1))
    assert exc3.value.status_code == 400


def test_video_event_lock_conflict_refused():
    """视频被其他用户锁定时保存应返回 409。"""
    video_id, task_id = _make_video_and_task()
    _lock_video(video_id, 99)
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert exc.value.status_code == 409


def test_video_event_video_not_found():
    """视频不存在时保存/读取应被拒绝（404）。"""
    _, task_id = _make_video_and_task()
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_event_annotations(task_id, 999999, seg, 1)
        )
    assert exc.value.status_code == 404


def test_video_event_invalid_label_id():
    video_id, task_id = _make_video_and_task()
    seg = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 99}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert exc.value.status_code == 400


def test_video_event_end_le_start():
    video_id, task_id = _make_video_and_task()
    for bad in [
        {"start": 2.0, "end": 2.0},
        {"start": 3.0, "end": 2.0},
    ]:
        seg = [{"id": "s1", "type": "VideoSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
        assert exc.value.status_code == 400


def test_video_event_out_of_range():
    video_id, task_id = _make_video_and_task()
    for bad in [
        {"start": -1.0, "end": 2.0},   # 负值
        {"start": 0.0, "end": 11.0},   # end 越界（duration=10）
    ]:
        seg = [{"id": "s1", "type": "VideoSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
        assert exc.value.status_code == 400


def test_video_event_non_numeric_start_end():
    video_id, task_id = _make_video_and_task()
    for bad in [
        {"start": "abc", "end": 2.0},
        {"start": 0.0, "end": True},
        {"start": True, "end": 2.0},
    ]:
        seg = [{"id": "s1", "type": "VideoSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
        assert exc.value.status_code == 400


def test_video_event_unknown_type_rejected():
    video_id, task_id = _make_video_and_task()
    seg = [{"id": "s1", "type": "Unknown", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert exc.value.status_code == 400


def test_video_event_overlap_rejected():
    video_id, task_id = _make_video_and_task()
    seg = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 3.0, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 2.0, "end": 5.0, "label_id": 2},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert exc.value.status_code == 400


def test_video_event_overlap_rejected_order_independent():
    """重叠检测与输入顺序无关：颠倒区间顺序后仍应拒绝。"""
    video_id, task_id = _make_video_and_task()
    seg = [
        {"id": "s2", "type": "VideoSegment", "start": 2.0, "end": 5.0, "label_id": 2},
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 3.0, "label_id": 1},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert exc.value.status_code == 400


def test_video_event_adjacent_not_overlap():
    """相邻区间（[0,2) 与 [2,4)）应视为不重叠，允许保存。"""
    video_id, task_id = _make_video_and_task()
    seg = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 2.0, "end": 4.0, "label_id": 2},
    ]
    result = asyncio.run(AnnotationService.save_video_event_annotations(task_id, video_id, seg, 1))
    assert result["version"] == 1
    assert result["annotation_count"] == 2


def test_video_event_save_and_load_http(test_client, auth_headers):
    """走 HTTP 接口：POST /anno/video-event/save 后 GET /anno/video-event/load 返回同一批。"""
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ve-http-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    async def _add_video_and_task():
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
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="视频事件任务",
                task_type=AnnotationType.VIDEO_EVENT,
                status="pending",
                assignees=[],
                classes=_VIDEO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return video.id, task.id

    video_id, task_id = asyncio.run(_add_video_and_task())

    segments = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1},
    ]
    save_resp = test_client.post(
        "/api/v1/annotation/anno/video-event/save",
        json={"task_id": task_id, "video_id": video_id, "segments": segments},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()["data"]["version"] == 1

    load_resp = test_client.get(
        "/api/v1/annotation/anno/video-event/load",
        params={"task_id": task_id, "video_id": video_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"]["annotation_data"] == segments
    assert load_resp.json()["data"]["version"] == 1


def test_video_event_invalid_task_relation_http(test_client, auth_headers):
    """HTTP 端到端：传入归属关系不存在的 task_id 时保存/读取应被拒绝。"""
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ve-http-bad-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

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
        "/api/v1/annotation/anno/video-event/save",
        json={"task_id": 999999, "video_id": video_id, "segments": []},
        headers=auth_headers,
    )
    assert save_resp.status_code == 400, save_resp.text

    load_resp = test_client.get(
        "/api/v1/annotation/anno/video-event/load",
        params={"task_id": 999999, "video_id": video_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 400, load_resp.text


# ------------------------------------------------------------------
# 导出（JSONL / CSV / annotation_task_id 透传 / None 兜底 / 图片守卫前）
# ------------------------------------------------------------------


def _make_export_video_and_task() -> tuple[int, int, int]:
    """建数据集 + 视频 + video_event 任务，返回 (dataset_id, video_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="视频事件导出集")
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
                name="视频事件导出任务",
                task_type=AnnotationType.VIDEO_EVENT,
                status="pending",
                assignees=[],
                classes=_VIDEO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return ds.id, video.id, task.id

    return asyncio.run(_run())


def _patch_video_event_mocks(monkeypatch, segments):
    """打桩 ``load_video_event_annotations``：按 (task_id, video_id) 返回固定标注。"""

    async def _load(task_id, v_id):
        return {"annotation_data": segments, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_video_event_annotations", _load)


def test_video_event_export_jsonl(monkeypatch, tmp_path):
    """JSONL：每行 {start,end,label}，多事件 + 秒级 float + label 取类名。"""
    ds_id, video_id, task_id = _make_export_video_and_task()
    segments = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.5, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]
    _patch_video_event_mocks(monkeypatch, segments)
    out = str(tmp_path / "out")

    asyncio.run(_export_video_event(ds_id, out, annotation_task_id=task_id))

    path = os.path.join(out, f"demo_{video_id}.jsonl")
    assert os.path.exists(path)
    rows = [
        json.loads(line)
        for line in open(path, encoding="utf-8").read().strip().splitlines()
    ]
    assert rows == [
        {"start": 0.0, "end": 2.5, "label": "跑步"},
        {"start": 3.0, "end": 5.0, "label": "跳跃"},
    ]


def test_video_event_export_csv(monkeypatch, tmp_path):
    """CSV：表头 start,end,label，每行一段事件的秒级 float 与 label 名。"""
    ds_id, video_id, task_id = _make_export_video_and_task()
    segments = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.5, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]
    _patch_video_event_mocks(monkeypatch, segments)
    out = str(tmp_path / "outcsv")

    asyncio.run(_export_video_event(ds_id, out, annotation_task_id=task_id, csv=True))

    path = os.path.join(out, f"demo_{video_id}.csv")
    assert os.path.exists(path)
    lines = open(path, encoding="utf-8").read().strip().splitlines()
    assert lines == [
        "start,end,label",
        "0.0,2.5,跑步",
        "3.0,5.0,跳跃",
    ]


def test_video_event_export_none_annotation_task_id(monkeypatch, tmp_path):
    """annotation_task_id 为空时预警并跳过（不产出任何文件）。"""
    ds_id, _, _ = _make_export_video_and_task()
    out = str(tmp_path / "outnone")
    os.makedirs(out, exist_ok=True)
    asyncio.run(_export_video_event(ds_id, out, annotation_task_id=None))
    assert os.listdir(out) == []


def test_video_event_export_unknown_label_falls_back(monkeypatch, tmp_path):
    """classes 中不存在的 label_id：label 回退为 ``class_<id>``。"""
    ds_id, video_id, task_id = _make_export_video_and_task()
    segments = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 99}]
    _patch_video_event_mocks(monkeypatch, segments)
    out = str(tmp_path / "outunknown")

    asyncio.run(_export_video_event(ds_id, out, annotation_task_id=task_id))

    rows = [
        json.loads(line)
        for line in open(os.path.join(out, f"demo_{video_id}.jsonl"), encoding="utf-8")
        .read()
        .strip()
        .splitlines()
    ]
    assert rows == [{"start": 0.0, "end": 2.0, "label": "class_99"}]


def test_video_event_export_through_core_entry(monkeypatch, tmp_path):
    """真实入口 ``_export_core``：video_event 数据集应走到视频事件导出并产出文件。

    回归：若按图片空集提前 return，视频事件导出永远不会执行（数据集无 AnnotationImageModel 行）。
    """
    ds_id, video_id, task_id = _make_export_video_and_task()
    segments = [{"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1}]
    _patch_video_event_mocks(monkeypatch, segments)
    out = str(tmp_path / "outcore")

    asyncio.run(_export_core(ds_id, task_id, "video-event-csv", out, annotation_task_id=task_id))

    assert os.path.exists(os.path.join(out, f"demo_{video_id}.jsonl"))


def test_video_event_export_training_path_uses_annotation_task_id(monkeypatch, tmp_path):
    """训练式路径回归：传入的训练任务 id 与标注任务 id 不同仍导出。

    训练/评估 pipeline 通过 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
    进入；标注读取必须用「标注任务 id」，否则 ``_verify_video_event_task_relation`` 拒绝、
    导致标注静默为空。断言实际传给 ``load_video_event_annotations`` 的确实是标注任务 id，
    且 JSONL 文件确实产出。
    """
    ds_id, video_id, ann_task_id = _make_export_video_and_task()
    train_task_id = 9999  # 模拟训练任务 id，与标注任务 id 不同

    seen_ids: list[int] = []

    segments = [
        {"id": "s1", "type": "VideoSegment", "start": 0.0, "end": 2.0, "label_id": 1},
        {"id": "s2", "type": "VideoSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]

    async def _load(task_id, v_id):
        seen_ids.append(task_id)
        return {"annotation_data": segments, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_video_event_annotations", _load)

    out = str(tmp_path / "outtrain")
    asyncio.run(_export_core(
        ds_id, train_task_id, "video-event-csv", out, annotation_task_id=ann_task_id,
    ))

    assert seen_ids and all(i == ann_task_id for i in seen_ids), seen_ids
    path = os.path.join(out, f"demo_{video_id}.jsonl")
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "跑步" in content and "跳跃" in content
