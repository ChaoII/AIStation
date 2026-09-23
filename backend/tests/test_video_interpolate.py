"""视频关键帧批量插值保存接口测试（B1）。

验证：批量保存成功且各中间帧版本递增；frame_a/frame_b 范围校验（含越界、
frame_a>=frame_b）；track_id 非空校验；中间帧必须严格落在 (frame_a, frame_b)；
每帧框 track_id 一致（同一 track_id 一帧至多一框）；关键帧不被覆盖；
事务回滚（某帧非法则整批回滚）；关键帧必须实际存在该 track 的框。
采用与 ``test_video_annotation`` 一致的方式：直接构造 DB 行并调用
``AnnotationService.save_video_interpolation``。
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


def _make_video_and_task() -> tuple[int, int]:
    """建数据集 + 视频 + video_detection 任务，返回 (video_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="插值测试集")
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


def _box(track_id: str, x1, y1, x2, y2, class_id=0) -> dict:
    """构造一个带 track_id 的 AxisAlignedBox。"""
    return {
        "id": uuid4().hex,
        "type": "AxisAlignedBox",
        "class_id": class_id,
        "track_id": track_id,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }


def _save_keyframes(task_id: int, video_id: int, track_id: str, frame_a: int, frame_b: int):
    """在 frame_a/frame_b 各保存一条该 track 的关键帧框。"""
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    asyncio.run(
        AnnotationService.save_video_annotations(
            task_id, video_id, frame_a, [_box(track_id, 0.1, 0.1, 0.2, 0.2)], auth
        )
    )
    asyncio.run(
        AnnotationService.save_video_annotations(
            task_id, video_id, frame_b, [_box(track_id, 0.5, 0.5, 0.6, 0.6)], auth
        )
    )


def test_interpolate_batch_save_increments_versions():
    """批量保存成功：各中间帧版本递增，且重复保存版本号 +1。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)

    frames = [
        {"frame_index": 12, "annotations": [_box(track, 0.2, 0.2, 0.3, 0.3)]},
        {"frame_index": 15, "annotations": [_box(track, 0.3, 0.3, 0.4, 0.4)]},
    ]
    result = asyncio.run(
        AnnotationService.save_video_interpolation(task_id, video_id, track, 10, 20, frames, auth)
    )
    assert result["count"] == 2
    assert result["saved"] == [
        {"frame_index": 12, "version": 1},
        {"frame_index": 15, "version": 1},
    ]
    # 重复保存同批帧 → 版本递增到 2
    result2 = asyncio.run(
        AnnotationService.save_video_interpolation(task_id, video_id, track, 10, 20, frames, auth)
    )
    assert result2["saved"] == [
        {"frame_index": 12, "version": 2},
        {"frame_index": 15, "version": 2},
    ]


def test_interpolate_frame_range_validation():
    """frame_a/frame_b 越界（负值或 >= frame_count）应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"

    # frame_b 超出帧范围
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, track, 0, 250, [], auth)
        )
    assert exc.value.status_code == 400

    # frame_a 为负
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, track, -1, 10, [], auth)
        )
    assert exc.value.status_code == 400


def test_interpolate_frame_a_ge_frame_b_rejected():
    """frame_a >= frame_b 应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, track, 20, 20, [], auth)
        )
    assert exc.value.status_code == 400

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, track, 30, 10, [], auth)
        )
    assert exc.value.status_code == 400


def test_interpolate_empty_track_id_rejected():
    """空字符串 track_id 应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, "  ", 10, 20, [], auth)
        )
    assert exc.value.status_code == 400


def test_interpolate_middle_frame_not_strictly_between():
    """中间帧 frame_index 必须严格落在 (frame_a, frame_b)，不含关键帧。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)

    # 中间帧等于 frame_a
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, track, 10, 20,
                [{"frame_index": 10, "annotations": [_box(track, 0.2, 0.2, 0.3, 0.3)]}],
                auth,
            )
        )
    assert exc.value.status_code == 400
    # 中间帧等于 frame_b
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, track, 10, 20,
                [{"frame_index": 20, "annotations": [_box(track, 0.2, 0.2, 0.3, 0.3)]}],
                auth,
            )
        )
    assert exc.value.status_code == 400
    # 中间帧越出 (frame_a, frame_b)
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, track, 10, 20,
                [{"frame_index": 25, "annotations": [_box(track, 0.2, 0.2, 0.3, 0.3)]}],
                auth,
            )
        )
    assert exc.value.status_code == 400


def test_interpolate_track_consistency_rejected():
    """中间帧框的 track_id 与顶层 track_id 不一致应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    _save_keyframes(task_id, video_id, "track-1", 10, 20)

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, "track-1", 10, 20,
                [{"frame_index": 15, "annotations": [_box("track-2", 0.3, 0.3, 0.4, 0.4)]}],
                auth,
            )
        )
    assert exc.value.status_code == 400


def test_interpolate_duplicate_track_same_frame_rejected():
    """同一中间帧内同一 track_id 出现两框应被拒绝（一帧一框一目标）。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, track, 10, 20,
                [{
                    "frame_index": 15,
                    "annotations": [
                        _box(track, 0.3, 0.3, 0.4, 0.4),
                        _box(track, 0.5, 0.5, 0.6, 0.6),
                    ],
                }],
                auth,
            )
        )
    assert exc.value.status_code == 400
    assert "track_id" in exc.value.msg


def test_interpolate_duplicate_frame_index_rejected():
    """frames 中出现重复 frame_index 应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, track, 10, 20,
                [
                    {"frame_index": 15, "annotations": [_box(track, 0.3, 0.3, 0.4, 0.4)]},
                    {"frame_index": 15, "annotations": [_box(track, 0.5, 0.5, 0.6, 0.6)]},
                ],
                auth,
            )
        )
    assert exc.value.status_code == 400


def test_interpolate_keyframe_not_overwritten():
    """关键帧（frame_a/frame_b）的框不被插值覆盖。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)
    keyframe_a = asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 10))
    keyframe_b = asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 20))

    asyncio.run(
        AnnotationService.save_video_interpolation(
            task_id, video_id, track, 10, 20,
            [{"frame_index": 15, "annotations": [_box(track, 0.9, 0.9, 0.95, 0.95)]}],
            auth,
        )
    )
    # 关键帧内容保持原样
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 10)) == keyframe_a
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 20)) == keyframe_b


def test_interpolate_transaction_rollback():
    """某中间帧非法则整批回滚：已写入的前帧也不落库。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    track = "track-1"
    _save_keyframes(task_id, video_id, track, 10, 20)

    frames = [
        {"frame_index": 12, "annotations": [_box(track, 0.2, 0.2, 0.3, 0.3)]},
        # 第二帧 track_id 不一致 → 整批回滚
        {"frame_index": 15, "annotations": [_box("track-other", 0.3, 0.3, 0.4, 0.4)]},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(task_id, video_id, track, 10, 20, frames, auth)
        )
    assert exc.value.status_code == 400
    # 前一帧不得落库（事务回滚）
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 12)) is None


def test_interpolate_keyframe_missing_track_rejected():
    """frame_a/frame_b 不存在该 track 的关键帧框时应被拒绝。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    _save_keyframes(task_id, video_id, "track-1", 10, 20)

    # frame_b 无该 track 的框
    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_interpolation(
                task_id, video_id, "track-2", 10, 20,
                [{"frame_index": 15, "annotations": [_box("track-2", 0.3, 0.3, 0.4, 0.4)]}],
                auth,
            )
        )
    assert exc.value.status_code == 400


def test_interpolate_endpoint_http(test_client, auth_headers, monkeypatch):
    """走 HTTP 接口：先存关键帧，再 POST /video/interpolate 批量保存中间帧。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"interp-http-{uuid4().hex[:8]}"},
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

    # 先保存两个关键帧（同一 track）
    track = "track-http"
    for fi, box in ((10, _box(track, 0.1, 0.1, 0.2, 0.2)), (20, _box(track, 0.5, 0.5, 0.6, 0.6))):
        save_resp = test_client.post(
            "/api/v1/annotation/anno/video/save",
            json={"task_id": task_id, "video_id": video_id, "frame_index": fi,
                  "annotations": [box]},
            headers=auth_headers,
        )
        assert save_resp.status_code == 200, save_resp.text

    interp_resp = test_client.post(
        "/api/v1/annotation/anno/video/interpolate",
        json={
            "task_id": task_id,
            "video_id": video_id,
            "track_id": track,
            "frame_a": 10,
            "frame_b": 20,
            "frames": [
                {"frame_index": 15,
                 "annotations": [_box(track, 0.3, 0.3, 0.4, 0.4)]},
            ],
        },
        headers=auth_headers,
    )
    assert interp_resp.status_code == 200, interp_resp.text
    data = interp_resp.json()["data"]
    assert data["count"] == 1
    assert data["saved"] == [{"frame_index": 15, "version": 1}]

    load_resp = test_client.get(
        "/api/v1/annotation/anno/video/load",
        params={"task_id": task_id, "v_id": video_id, "frame_index": 15},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"][0]["track_id"] == track
