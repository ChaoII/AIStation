"""时间序列区间事件导出测试（区间 JSONL / CSV）。

验证：对 ``time_series_event`` 数据集每个时间序列用「标注任务 id」读
``load_time_series_annotations``，生成 ``<stem>_{time_series_id}.jsonl``（每行
``{"start","end","label"}``，start/end 为时间戳原始精度，label 取任务 ``classes``
列表中 ``label_id`` 对应的名称）与可选 CSV（表头 ``start,end,label``）。
关键回归：训练/评估路径经 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
进入时，标注读取必须用「标注任务 id」（同视频/文本/音频导出修复，不得把训练任务 id 误传）。
时间序列事件导出只依赖标注元数据，无需下载序列文件本身，故 s3/文件内容全部不 mock。
"""
import asyncio
import json
import os

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationTimeSeriesModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.plugin.module_train.exporter import (
    _export_core,
    _export_time_series_event,
)

_TS_CLASSES = [
    {"id": 1, "name": "故障"},
    {"id": 2, "name": "峰值"},
]

# 两段 TimeSeriesSegment：时间戳原始精度 + label_id 映射
_TS_ANN = [
    {"id": "t1", "type": "TimeSeriesSegment", "start": 0, "end": 2.5, "label_id": 1},
    {"id": "t2", "type": "TimeSeriesSegment", "start": 3.0, "end": 5.0, "label_id": 2},
]


def _make_series_and_task() -> tuple[int, int, int]:
    """建数据集 + 时间序列 + time_series_event 任务，返回 (dataset_id, series_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="时间序列导出集")
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
                start_time=0.0,
                end_time=10.0,
                size_bytes=64,
                status="unannotated",
            )
            db.add(series)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="时间序列事件导出任务",
                task_type=AnnotationType.TIME_SERIES_EVENT,
                status="pending",
                assignees=[],
                classes=_TS_CLASSES,
            )
            db.add(task)
            await db.flush()
            return ds.id, series.id, task.id

    return asyncio.run(_run())


def _patch_ts_mocks(monkeypatch, annotations):
    """打桩 ``load_time_series_annotations``：按 (task_id, series_id) 返回固定标注。"""

    async def _load(t, s_id):
        return {"annotation_data": annotations, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_time_series_annotations", _load)


def test_ts_export_jsonl(monkeypatch, tmp_path):
    """JSONL：每行 {start,end,label}，多事件 + 时间戳原始精度 + label 取类名。"""
    ds_id, series_id, task_id = _make_series_and_task()
    _patch_ts_mocks(monkeypatch, _TS_ANN)
    out = str(tmp_path / "out")

    asyncio.run(_export_time_series_event(ds_id, out, annotation_task_id=task_id))

    path = os.path.join(out, f"demo_{series_id}.jsonl")
    assert os.path.exists(path)
    rows = [
        json.loads(line)
        for line in open(path, encoding="utf-8").read().strip().splitlines()
    ]
    assert rows == [
        {"start": 0, "end": 2.5, "label": "故障"},
        {"start": 3.0, "end": 5.0, "label": "峰值"},
    ]


def test_ts_export_csv(monkeypatch, tmp_path):
    """CSV：表头 start,end,label，每行一段事件的时间戳与 label 名。"""
    ds_id, series_id, task_id = _make_series_and_task()
    _patch_ts_mocks(monkeypatch, _TS_ANN)
    out = str(tmp_path / "outcsv")

    asyncio.run(_export_time_series_event(ds_id, out, annotation_task_id=task_id, csv=True))

    path = os.path.join(out, f"demo_{series_id}.csv")
    assert os.path.exists(path)
    lines = open(path, encoding="utf-8").read().strip().splitlines()
    assert lines == [
        "start,end,label",
        "0,2.5,故障",
        "3.0,5.0,峰值",
    ]


def test_ts_export_empty_annotations_write_empty_jsonl(monkeypatch, tmp_path):
    """空标注列表：仍产出空 JSONL 文件（同 audio 语义，保证下游文件存在）。"""
    ds_id, series_id, task_id = _make_series_and_task()
    _patch_ts_mocks(monkeypatch, [])
    out = str(tmp_path / "outempty")

    asyncio.run(_export_time_series_event(ds_id, out, annotation_task_id=task_id))

    path = os.path.join(out, f"demo_{series_id}.jsonl")
    assert os.path.exists(path)
    assert open(path, encoding="utf-8").read() == ""


def test_ts_export_none_annotation_task_id_skips(monkeypatch, tmp_path):
    """annotation_task_id=None 兜底：warning + return，不读标注、不产出文件。"""
    ds_id, series_id, _ = _make_series_and_task()

    called = []

    async def _load(t, s_id):
        called.append((t, s_id))
        return {"annotation_data": _TS_ANN, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_time_series_annotations", _load)
    out = str(tmp_path / "outnone")

    asyncio.run(_export_time_series_event(ds_id, out, annotation_task_id=None))

    assert called == []
    assert not os.path.exists(os.path.join(out, f"demo_{series_id}.jsonl"))


def test_ts_export_through_core_entry(monkeypatch, tmp_path):
    """真实入口 ``_export_core``：time_series_event 数据集应走到序列导出并产出文件。

    回归：若按图片空集提前 return，序列导出永远不会执行（数据集无 AnnotationImageModel 行）。
    """
    ds_id, series_id, task_id = _make_series_and_task()
    _patch_ts_mocks(monkeypatch, _TS_ANN)
    out = str(tmp_path / "outcore")

    asyncio.run(_export_core(ds_id, task_id, "ultralytics", out, annotation_task_id=task_id))

    assert os.path.exists(os.path.join(out, f"demo_{series_id}.jsonl"))


def test_ts_export_training_path_uses_annotation_task_id(monkeypatch, tmp_path):
    """训练式路径回归：传入的训练任务 id 与标注任务 id 不同仍导出。

    训练/评估 pipeline 通过 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
    进入；标注读取必须用「标注任务 id」，否则 ``_verify_time_series_task_relation`` 拒绝、
    导致标注静默为空。断言实际传给 ``load_time_series_annotations`` 的确实是标注任务 id，
    且 JSONL 文件确实产出（非空，含正确 label）。
    """
    ds_id, series_id, ann_task_id = _make_series_and_task()
    train_task_id = 9999  # 模拟训练任务 id，与标注任务 id 不同

    seen_ids: list[int] = []

    async def _load(task_id, s_id):
        seen_ids.append(task_id)
        return {"annotation_data": _TS_ANN, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_time_series_annotations", _load)

    out = str(tmp_path / "outtrain")
    asyncio.run(_export_core(
        ds_id, train_task_id, "ultralytics", out, annotation_task_id=ann_task_id,
    ))

    assert seen_ids and all(i == ann_task_id for i in seen_ids), seen_ids
    path = os.path.join(out, f"demo_{series_id}.jsonl")
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "故障" in content and "峰值" in content
