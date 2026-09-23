"""时间序列事件标注按序列读写与区间/重叠/越界校验测试。

验证 save → load 同一批 ``TimeSeriesSegment``；``task_id`` 显式传入且任务与序列归属关系
不合法时被拒绝；``start/end``（非法/越界/负值）、``label_id`` 非法、**区间重叠**被拒绝；
``version`` 在重复保存时递增；空列表清除；序列被他人锁定拒绝。采用与
``test_audio_event_annotation.py`` 一致的构造 DB 行并直接调用 service 的方式，
另加一条走 HTTP 接口的端到端用例。
"""
import asyncio
from uuid import uuid4

import pytest

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationTimeSeriesModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.core.exceptions import CustomException

_START = 0.0
_END = 10.0

_TS_CLASSES = [
    {"id": 1, "name": "故障", "color": "#ff0000"},
    {"id": 2, "name": "峰值", "color": "#00ff00"},
]


def _make_series_and_task(
    start: float = _START, end: float = _END, locked_by: int | None = None
) -> tuple[int, int]:
    """建数据集 + 时间序列 + time_series_event 任务，返回 (series_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="时间序列事件集")
            db.add(ds)
            await db.flush()
            series = AnnotationTimeSeriesModel(
                dataset_id=ds.id,
                name="demo.csv",
                object_key="demo.csv",
                time_column="timestamp",
                value_columns=["value"],
                row_count=10,
                time_unit="s",
                start_time=start,
                end_time=end,
                size_bytes=64,
                status="unannotated",
                locked_by=locked_by,
            )
            db.add(series)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="时间序列事件任务",
                task_type=AnnotationType.TIME_SERIES_EVENT,
                status="pending",
                assignees=[],
                classes=_TS_CLASSES,
            )
            db.add(task)
            await db.flush()
            return series.id, task.id

    return asyncio.run(_run())


def _make_dataset() -> int:
    """建一个独立数据集（用于无关任务归属校验），返回 ds_id。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="时间序列事件无关数据集")
            db.add(ds)
            await db.flush()
            return ds.id

    return asyncio.run(_run())


def test_ts_save_then_load_returns_same_batch():
    series_id, task_id = _make_series_and_task()
    annotations = [
        {"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.5, "label_id": 1},
        {"id": "a2", "type": "TimeSeriesSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]

    result = asyncio.run(
        AnnotationService.save_time_series_annotations(task_id, series_id, annotations, 1)
    )
    assert result["version"] == 1
    assert result["annotation_count"] == 2

    loaded = asyncio.run(AnnotationService.load_time_series_annotations(task_id, series_id))
    assert loaded["annotation_data"] == annotations
    assert loaded["version"] == 1


def test_ts_load_empty_returns_empty():
    series_id, task_id = _make_series_and_task()
    loaded = asyncio.run(AnnotationService.load_time_series_annotations(task_id, series_id))
    assert loaded == {"annotation_data": [], "version": 0}


def test_ts_save_same_series_increments_version():
    series_id, task_id = _make_series_and_task()
    ann = [{"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    r1 = asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    r2 = asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert r1["version"] == 1
    assert r2["version"] == 2


def test_ts_save_empty_list_clears():
    """空列表允许保存，写入空内容的新版本，读回为空（清除既有标注）。"""
    series_id, task_id = _make_series_and_task()
    ann = [{"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 1}]
    r1 = asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert r1["version"] == 1

    r2 = asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, [], 1))
    assert r2["version"] == 2
    assert r2["annotation_count"] == 0

    loaded = asyncio.run(AnnotationService.load_time_series_annotations(task_id, series_id))
    assert loaded["annotation_data"] == []
    assert loaded["version"] == 2


def test_ts_save_invalid_task_relation_refused():
    """任务与序列无归属关系（不同数据集/错误类型/不存在）时保存应被拒绝。"""
    series_id, _ = _make_series_and_task()
    stray_dataset = _make_dataset()
    ann = [{"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    async def _stray_task(ds_id: int, task_type: AnnotationType) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="无关任务",
                task_type=task_type,
                status="pending",
                assignees=[],
                classes=_TS_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    # 不同数据集的任务
    stray_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.TIME_SERIES_EVENT))
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(stray_task, series_id, ann, 1))
    assert exc.value.status_code == 400

    # 任务类型不是 time_series_event（音频任务）也应被拒绝
    text_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.AUDIO_EVENT))
    with pytest.raises(CustomException) as exc2:
        asyncio.run(AnnotationService.save_time_series_annotations(text_task, series_id, ann, 1))
    assert exc2.value.status_code == 400

    # 不存在的任务
    with pytest.raises(CustomException) as exc3:
        asyncio.run(AnnotationService.save_time_series_annotations(999999, series_id, ann, 1))
    assert exc3.value.status_code == 400


def test_ts_save_invalid_label_id():
    series_id, task_id = _make_series_and_task()
    ann = [{"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 99}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert exc.value.status_code == 400


def test_ts_save_non_numeric_endpoints():
    """start/end 为非数值（字符串/bool）时应被拒绝。"""
    series_id, task_id = _make_series_and_task()
    for bad in [
        {"start": "0", "end": 2.0},
        {"start": 0.0, "end": "2"},
        {"start": True, "end": 2.0},
    ]:
        ann = [{"id": "a1", "type": "TimeSeriesSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
        assert exc.value.status_code == 400


def test_ts_save_end_le_start():
    series_id, task_id = _make_series_and_task()
    for bad in [
        {"start": 2.0, "end": 2.0},
        {"start": 3.0, "end": 2.0},
    ]:
        ann = [{"id": "a1", "type": "TimeSeriesSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
        assert exc.value.status_code == 400


def test_ts_save_out_of_time_range():
    series_id, task_id = _make_series_and_task()
    for bad in [
        {"start": -1.0, "end": 2.0},   # 负值（越界起点）
        {"start": 0.0, "end": 11.0},   # end 越界（end_time=10）
    ]:
        ann = [{"id": "a1", "type": "TimeSeriesSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
        assert exc.value.status_code == 400


def test_ts_save_unknown_type_rejected():
    series_id, task_id = _make_series_and_task()
    ann = [{"id": "a1", "type": "Unknown", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert exc.value.status_code == 400


def test_ts_save_overlap_rejected():
    series_id, task_id = _make_series_and_task()
    ann = [
        {"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 3.0, "label_id": 1},
        {"id": "a2", "type": "TimeSeriesSegment", "start": 2.0, "end": 5.0, "label_id": 2},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert exc.value.status_code == 400


def test_ts_save_overlap_rejected_order_independent():
    """重叠检测与输入顺序无关：颠倒区间顺序后仍应拒绝（先收集全部区间再两两检测）。"""
    series_id, task_id = _make_series_and_task()
    ann = [
        {"id": "a2", "type": "TimeSeriesSegment", "start": 2.0, "end": 5.0, "label_id": 2},
        {"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 3.0, "label_id": 1},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert exc.value.status_code == 400


def test_ts_save_adjacent_not_overlap():
    """相邻区间（[0,2) 与 [2,4)）应视为不重叠，允许保存。"""
    series_id, task_id = _make_series_and_task()
    ann = [
        {"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 1},
        {"id": "a2", "type": "TimeSeriesSegment", "start": 2.0, "end": 4.0, "label_id": 2},
    ]
    result = asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert result["version"] == 1
    assert result["annotation_count"] == 2


def test_ts_save_locked_by_other_refused():
    """序列被其他用户锁定时保存应被拒绝（409）。"""
    series_id, task_id = _make_series_and_task(locked_by=2)
    ann = [{"id": "a1", "type": "TimeSeriesSegment", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_time_series_annotations(task_id, series_id, ann, 1))
    assert exc.value.status_code == 409


def test_ts_save_and_load_http(test_client, auth_headers, monkeypatch):
    """走 HTTP 接口：POST /anno/timeseries/save 后 GET /anno/timeseries/load 返回同一批。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ts-http-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    series_resp = test_client.post(
        f"/api/v1/annotation/timeseries/upload?dataset_id={ds_id}",
        files={"file": ("data.csv", b"timestamp,value\n1,10\n2,20\n3,30\n", "text/csv")},
        headers=auth_headers,
    )
    assert series_resp.status_code == 200, series_resp.text
    series_id = series_resp.json()["data"]["id"]

    async def _add_task():
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="时间序列事件任务",
                task_type=AnnotationType.TIME_SERIES_EVENT,
                status="pending",
                assignees=[],
                classes=_TS_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    task_id = asyncio.run(_add_task())

    annotations = [
        {"id": "a1", "type": "TimeSeriesSegment", "start": 1.0, "end": 2.0, "label_id": 1},
    ]
    save_resp = test_client.post(
        "/api/v1/annotation/anno/timeseries/save",
        json={"task_id": task_id, "time_series_id": series_id, "annotations": annotations},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()["data"]["version"] == 1

    load_resp = test_client.get(
        "/api/v1/annotation/anno/timeseries/load",
        params={"task_id": task_id, "t_id": series_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"]["annotation_data"] == annotations
    assert load_resp.json()["data"]["version"] == 1
