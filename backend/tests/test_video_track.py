"""视频检测框 track_id 兼容性测试（A1 目标跟踪）。

验证：save → load 能透传 ``track_id``；无 ``track_id`` 的框与旧行为一致（合法）；
同一帧内同一 ``track_id`` 至多一框（重复则拒绝）；同一 ``track_id`` 可跨帧出现（轨迹）。
采用与 ``test_video_annotation`` 一致的方式：直接构造 DB 行并调用
``AnnotationService.save_video_annotations`` / ``load_video_annotations``。
"""
import asyncio
from types import SimpleNamespace

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
            ds = DatasetModel(name="track_compat集")
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


def test_track_save_load_passes_track_id():
    """带 track_id 的框 save → load 透传 track_id。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    boxes = [
        {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
         "track_id": "track-1", "x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.7},
        {"id": "b", "type": "AxisAlignedBox", "class_id": 1,
         "track_id": "track-2", "x1": 0.3, "y1": 0.4, "x2": 0.6, "y2": 0.9},
    ]

    result = asyncio.run(
        AnnotationService.save_video_annotations(task_id, video_id, 10, boxes, auth)
    )
    assert result["version"] == 1
    assert result["annotation_count"] == 2

    loaded = asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 10))
    assert loaded == boxes


def test_track_without_track_id_still_works():
    """无 track_id 的框行为与现状一致（合法，可存取，且不破坏旧数据）。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    boxes = [
        {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
         "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
        {"id": "b", "type": "AxisAlignedBox", "class_id": 1,
         "x1": 0.3, "y1": 0.3, "x2": 0.4, "y2": 0.4},
    ]

    result = asyncio.run(
        AnnotationService.save_video_annotations(task_id, video_id, 5, boxes, auth)
    )
    assert result["annotation_count"] == 2
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 5)) == boxes


def test_track_duplicate_same_frame_rejected():
    """同一帧内同一 track_id 出现两框应被拒绝（一帧一框一目标）。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    boxes = [
        {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
         "track_id": "track-1", "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
        {"id": "b", "type": "AxisAlignedBox", "class_id": 0,
         "track_id": "track-1", "x1": 0.3, "y1": 0.3, "x2": 0.4, "y2": 0.4},
    ]

    with pytest.raises(CustomException) as exc:
        asyncio.run(
            AnnotationService.save_video_annotations(task_id, video_id, 3, boxes, auth)
        )
    assert exc.value.status_code == 400
    assert "track_id" in exc.value.msg


def test_track_same_track_id_across_frames_allowed():
    """同一 track_id 可跨帧出现（构成轨迹），每帧单独持久化。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    box_a = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
             "track_id": "track-1", "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}
    box_b = {"id": "b", "type": "AxisAlignedBox", "class_id": 0,
             "track_id": "track-1", "x1": 0.5, "y1": 0.5, "x2": 0.6, "y2": 0.6}

    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 1, [box_a], auth))
    asyncio.run(AnnotationService.save_video_annotations(task_id, video_id, 2, [box_b], auth))

    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 1)) == [box_a]
    assert asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 2)) == [box_b]


def test_track_legacy_format_without_field_loads():
    """旧格式（框无 track_id 字段）仍可加载。"""
    video_id, task_id = _make_video_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    legacy_box = {"id": "a", "type": "AxisAlignedBox", "class_id": 0,
                  "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    asyncio.run(
        AnnotationService.save_video_annotations(task_id, video_id, 8, [legacy_box], auth)
    )
    loaded = asyncio.run(AnnotationService.load_video_annotations(task_id, video_id, 8))
    assert loaded == [legacy_box]
    assert "track_id" not in loaded[0]
