"""音频事件导出测试（SED 事件 JSONL / CSV）。

验证：对 ``audio_event`` 数据集每个音频用「标注任务 id」读 ``load_audio_annotations``，
生成 ``<stem>_{audio_id}.jsonl``（每行 ``{"start","end","label"}``，label 取任务
``classes`` 中 ``label_id`` 对应的名称，秒级 float）与可选 CSV（表头 ``start,end,label``）。
关键回归：训练/评估路径经 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
进入时，标注读取必须用「标注任务 id」（同视频/文本导出修复，不得把训练任务 id 误传）。
音频事件导出只依赖标注元数据，无需下载音频文件本身，故 s3/文件内容全部不 mock。
"""
import asyncio
import json
import os

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationAudioModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.plugin.module_train.exporter import _export_audio_event, _export_core

_AUDIO_CLASSES = [
    {"id": 1, "name": "狗叫"},
    {"id": 2, "name": "鸟鸣"},
]

# 两段 AudioSegment：秒级 float + label_id 映射
_AUDIO_ANN = [
    {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.5, "label_id": 1},
    {"id": "a2", "type": "AudioSegment", "start": 3.0, "end": 5.0, "label_id": 2},
]


def _make_audio_and_task() -> tuple[int, int, int]:
    """建数据集 + 音频 + audio_event 任务，返回 (dataset_id, audio_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="音频导出集")
            db.add(ds)
            await db.flush()
            audio = AnnotationAudioModel(
                dataset_id=ds.id,
                name="demo.wav",
                object_key="demo.wav",
                duration=10.0,
                sample_rate=44100,
                channels=2,
                size_bytes=64,
                status="unannotated",
            )
            db.add(audio)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="音频事件导出任务",
                task_type=AnnotationType.AUDIO_EVENT,
                status="pending",
                assignees=[],
                classes=_AUDIO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return ds.id, audio.id, task.id

    return asyncio.run(_run())


def _patch_audio_mocks(monkeypatch, annotations):
    """打桩 ``load_audio_annotations``：按 (task_id, audio_id) 返回固定标注。"""

    async def _load(t, a_id):
        return {"annotation_data": annotations, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_audio_annotations", _load)


def test_audio_export_jsonl(monkeypatch, tmp_path):
    """JSONL：每行 {start,end,label}，多事件 + 秒级 float + label 取类名。"""
    ds_id, audio_id, task_id = _make_audio_and_task()
    _patch_audio_mocks(monkeypatch, _AUDIO_ANN)
    out = str(tmp_path / "out")

    asyncio.run(_export_audio_event(ds_id, out, annotation_task_id=task_id))

    path = os.path.join(out, f"demo_{audio_id}.jsonl")
    assert os.path.exists(path)
    rows = [
        json.loads(line)
        for line in open(path, encoding="utf-8").read().strip().splitlines()
    ]
    assert rows == [
        {"start": 0.0, "end": 2.5, "label": "狗叫"},
        {"start": 3.0, "end": 5.0, "label": "鸟鸣"},
    ]


def test_audio_export_csv(monkeypatch, tmp_path):
    """CSV：表头 start,end,label，每行一段事件的秒级 float 与 label 名。"""
    ds_id, audio_id, task_id = _make_audio_and_task()
    _patch_audio_mocks(monkeypatch, _AUDIO_ANN)
    out = str(tmp_path / "outcsv")

    asyncio.run(_export_audio_event(ds_id, out, annotation_task_id=task_id, csv=True))

    path = os.path.join(out, f"demo_{audio_id}.csv")
    assert os.path.exists(path)
    lines = open(path, encoding="utf-8").read().strip().splitlines()
    assert lines == [
        "start,end,label",
        "0.0,2.5,狗叫",
        "3.0,5.0,鸟鸣",
    ]


def test_audio_export_unknown_label_falls_back(monkeypatch, tmp_path):
    """classes 中不存在的 label_id：label 回退为 ``class_<id>``。"""
    ds_id, audio_id, task_id = _make_audio_and_task()
    ann = [{"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 99}]
    _patch_audio_mocks(monkeypatch, ann)
    out = str(tmp_path / "outunknown")

    asyncio.run(_export_audio_event(ds_id, out, annotation_task_id=task_id))

    rows = [
        json.loads(line)
        for line in open(os.path.join(out, f"demo_{audio_id}.jsonl"), encoding="utf-8")
        .read()
        .strip()
        .splitlines()
    ]
    assert rows == [{"start": 0.0, "end": 2.0, "label": "class_99"}]


def test_audio_export_through_core_entry(monkeypatch, tmp_path):
    """真实入口 ``_export_core``：audio_event 数据集应走到音频导出并产出文件。

    回归：若按图片空集提前 return，音频导出永远不会执行（数据集无 AnnotationImageModel 行）。
    """
    ds_id, audio_id, task_id = _make_audio_and_task()
    _patch_audio_mocks(monkeypatch, _AUDIO_ANN)
    out = str(tmp_path / "outcore")

    asyncio.run(_export_core(ds_id, task_id, "ultralytics", out, annotation_task_id=task_id))

    assert os.path.exists(os.path.join(out, f"demo_{audio_id}.jsonl"))


def test_audio_export_training_path_uses_annotation_task_id(monkeypatch, tmp_path):
    """训练式路径回归：传入的训练任务 id 与标注任务 id 不同仍导出。

    训练/评估 pipeline 通过 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
    进入；标注读取必须用「标注任务 id」，否则 ``_verify_audio_task_relation`` 拒绝、
    导致标注静默为空。断言实际传给 ``load_audio_annotations`` 的确实是标注任务 id，
    且 JSONL 文件确实产出（非空，含正确 label）。
    """
    ds_id, audio_id, ann_task_id = _make_audio_and_task()
    train_task_id = 9999  # 模拟训练任务 id，与标注任务 id 不同

    seen_ids: list[int] = []

    async def _load(task_id, a_id):
        seen_ids.append(task_id)
        return {"annotation_data": _AUDIO_ANN, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_audio_annotations", _load)

    out = str(tmp_path / "outtrain")
    asyncio.run(_export_core(
        ds_id, train_task_id, "ultralytics", out, annotation_task_id=ann_task_id,
    ))

    assert seen_ids and all(i == ann_task_id for i in seen_ids), seen_ids
    path = os.path.join(out, f"demo_{audio_id}.jsonl")
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "狗叫" in content and "鸟鸣" in content
