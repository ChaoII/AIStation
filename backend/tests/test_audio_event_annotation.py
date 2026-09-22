"""音频事件标注按音频读写与区间/重叠/越界校验测试。

验证 save → load 同一批 ``AudioSegment``；``task_id`` 显式传入且任务与音频归属关系
不合法时被拒绝；``start/end``（非法/越界/负值）、``label_id`` 非法、**区间重叠**
被拒绝；``version`` 在重复保存时递增。采用与 ``test_text_ner_annotation.py`` 一致的
方式：直接构造 DB 行并调用 service，另加一条走 HTTP 接口的端到端用例。
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationAudioModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.core.exceptions import CustomException

_DURATION = 10.0

_AUDIO_CLASSES = [
    {"id": 1, "name": "狗叫", "color": "#ff0000"},
    {"id": 2, "name": "鸟鸣", "color": "#00ff00"},
]


def _make_audio_and_task(duration: float = _DURATION) -> tuple[int, int]:
    """建数据集 + 音频 + audio_event 任务，返回 (audio_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="音频事件集")
            db.add(ds)
            await db.flush()
            audio = AnnotationAudioModel(
                dataset_id=ds.id,
                name="demo.wav",
                object_key="demo.wav",
                duration=duration,
                sample_rate=44100,
                channels=2,
                size_bytes=64,
                status="unannotated",
            )
            db.add(audio)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="音频事件任务",
                task_type=AnnotationType.AUDIO_EVENT,
                status="pending",
                assignees=[],
                classes=_AUDIO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return audio.id, task.id

    return asyncio.run(_run())


def _make_dataset() -> int:
    """建一个独立数据集（用于无关任务归属校验），返回 ds_id。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="音频事件无关数据集")
            db.add(ds)
            await db.flush()
            return ds.id

    return asyncio.run(_run())


def test_audio_save_then_load_returns_same_batch():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    annotations = [
        {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.5, "label_id": 1},
        {"id": "a2", "type": "AudioSegment", "start": 3.0, "end": 5.0, "label_id": 2},
    ]

    result = asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, annotations, auth))
    assert result["version"] == 1
    assert result["annotation_count"] == 2

    loaded = asyncio.run(AnnotationService.load_audio_annotations(task_id, audio_id))
    assert loaded["annotation_data"] == annotations
    assert loaded["version"] == 1


def test_audio_load_empty_returns_empty():
    audio_id, task_id = _make_audio_and_task()
    loaded = asyncio.run(AnnotationService.load_audio_annotations(task_id, audio_id))
    assert loaded == {"annotation_data": [], "version": 0}


def test_audio_save_same_audio_increments_version():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    r1 = asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    r2 = asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert r1["version"] == 1
    assert r2["version"] == 2


def test_audio_save_invalid_task_relation_refused():
    """任务与音频无归属关系（不同数据集/错误类型/不存在）时保存应被拒绝。"""
    audio_id, _ = _make_audio_and_task()
    stray_dataset = _make_dataset()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 1}]

    async def _stray_task(ds_id: int, task_type: AnnotationType) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="无关任务",
                task_type=task_type,
                status="pending",
                assignees=[],
                classes=_AUDIO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    # 不同数据集的任务
    stray_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.AUDIO_EVENT))
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_audio_annotations(stray_task, audio_id, ann, auth))
    assert exc.value.status_code == 400

    # 任务类型不是 audio_event（文本任务）也应被拒绝
    text_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.TEXT_NER))
    with pytest.raises(CustomException) as exc2:
        asyncio.run(AnnotationService.save_audio_annotations(text_task, audio_id, ann, auth))
    assert exc2.value.status_code == 400

    # 不存在的任务
    with pytest.raises(CustomException) as exc3:
        asyncio.run(AnnotationService.save_audio_annotations(999999, audio_id, ann, auth))
    assert exc3.value.status_code == 400


def test_audio_save_invalid_label_id():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 99}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert exc.value.status_code == 400


def test_audio_save_end_le_start():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    for bad in [
        {"start": 2.0, "end": 2.0},
        {"start": 3.0, "end": 2.0},
    ]:
        ann = [{"id": "a1", "type": "AudioSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
        assert exc.value.status_code == 400


def test_audio_save_out_of_range():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    for bad in [
        {"start": -1.0, "end": 2.0},   # 负值
        {"start": 0.0, "end": 11.0},   # end 越界（duration=10）
    ]:
        ann = [{"id": "a1", "type": "AudioSegment", "label_id": 1, **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
        assert exc.value.status_code == 400


def test_audio_save_overlap_rejected():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 3.0, "label_id": 1},
        {"id": "a2", "type": "AudioSegment", "start": 2.0, "end": 5.0, "label_id": 2},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert exc.value.status_code == 400


def test_audio_save_overlap_rejected_order_independent():
    """重叠检测与输入顺序无关：颠倒区间顺序后仍应拒绝（先收集全部区间再两两检测）。"""
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "a2", "type": "AudioSegment", "start": 2.0, "end": 5.0, "label_id": 2},
        {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 3.0, "label_id": 1},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert exc.value.status_code == 400


def test_audio_save_adjacent_not_overlap():
    """相邻区间（[0,2) 与 [2,4)）应视为不重叠，允许保存。"""
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 1},
        {"id": "a2", "type": "AudioSegment", "start": 2.0, "end": 4.0, "label_id": 2},
    ]
    result = asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert result["version"] == 1
    assert result["annotation_count"] == 2


def test_audio_save_unknown_type_rejected():
    audio_id, task_id = _make_audio_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "a1", "type": "Unknown", "start": 0.0, "end": 2.0, "label_id": 1}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_audio_annotations(task_id, audio_id, ann, auth))
    assert exc.value.status_code == 400


def test_audio_save_and_load_http(test_client, auth_headers, monkeypatch):
    """走 HTTP 接口：POST /anno/audio/save 后 GET /anno/audio/load 返回同一批。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"audio-http-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    with patch(
        "app.api.v1.module_annotation.dataset.audio_service._probe_audio",
        return_value={"duration": 10.0, "sample_rate": 44100, "channels": 2, "bitrate": 128},
    ):
        audio_resp = test_client.post(
            f"/api/v1/annotation/audio/upload?dataset_id={ds_id}",
            files={"file": ("demo.wav", b"\x00" * 64, "audio/wav")},
            headers=auth_headers,
        )
    assert audio_resp.status_code == 200, audio_resp.text
    audio_id = audio_resp.json()["data"]["id"]

    async def _add_task():
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="音频事件任务",
                task_type=AnnotationType.AUDIO_EVENT,
                status="pending",
                assignees=[],
                classes=_AUDIO_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    task_id = asyncio.run(_add_task())

    annotations = [
        {"id": "a1", "type": "AudioSegment", "start": 0.0, "end": 2.0, "label_id": 1},
    ]
    save_resp = test_client.post(
        "/api/v1/annotation/anno/audio/save",
        json={"task_id": task_id, "audio_id": audio_id, "annotations": annotations},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()["data"]["version"] == 1

    load_resp = test_client.get(
        "/api/v1/annotation/anno/audio/load",
        params={"task_id": task_id, "a_id": audio_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"]["annotation_data"] == annotations
    assert load_resp.json()["data"]["version"] == 1


def test_audio_save_invalid_task_relation_http(test_client, auth_headers, monkeypatch):
    """HTTP 端到端：传入归属关系不存在的 task_id 时保存/读取应被拒绝。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"audio-http-bad-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    with patch(
        "app.api.v1.module_annotation.dataset.audio_service._probe_audio",
        return_value={"duration": 10.0, "sample_rate": 44100, "channels": 2, "bitrate": 128},
    ):
        audio_resp = test_client.post(
            f"/api/v1/annotation/audio/upload?dataset_id={ds_id}",
            files={"file": ("demo.wav", b"\x00" * 64, "audio/wav")},
            headers=auth_headers,
        )
    assert audio_resp.status_code == 200, audio_resp.text
    audio_id = audio_resp.json()["data"]["id"]

    save_resp = test_client.post(
        "/api/v1/annotation/anno/audio/save",
        json={"task_id": 999999, "audio_id": audio_id, "annotations": []},
        headers=auth_headers,
    )
    assert save_resp.status_code == 400, save_resp.text

    load_resp = test_client.get(
        "/api/v1/annotation/anno/audio/load",
        params={"task_id": 999999, "a_id": audio_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 400, load_resp.text
