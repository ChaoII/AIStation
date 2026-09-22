"""文本 NER 文档标注按文档读写与关系/重叠校验测试。

验证 save → load 同一批实体/关系；``task_id`` 显式传入且任务与文档归属关系
不合法时被拒绝；实体（start/end/label_id/超范围/负数）、关系（unknown
relation_type / from/to 引用不存在实体）非法时被拒绝；重叠实体被拒绝；
``version`` 在重复保存时递增。采用与 ``test_video_annotation.py`` 一致的
方式：直接构造 DB 行并调用 service，另加一条走 HTTP 接口的端到端用例。
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationDocumentModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.core.exceptions import CustomException

_TASK_CLASSES = {
    "entities": [{"id": 1, "name": "人名"}, {"id": 2, "name": "地名"}],
    "relations": [{"id": 1, "name": "任职"}],
}

# 中文文本（UTF-16 code unit 数 = 8），用于字符偏移校验
_TEXT = "小明在北京工作\n"
_CHAR_COUNT = len(_TEXT.encode("utf-16-le")) // 2


def _make_document_and_task(text: str = _TEXT) -> tuple[int, int]:
    """建数据集 + 文档 + text_ner 任务，返回 (document_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5A文本集")
            db.add(ds)
            await db.flush()
            doc = AnnotationDocumentModel(
                dataset_id=ds.id,
                filename="doc.txt",
                object_key="doc.txt",
                content_hash="abc123",
                encoding="utf-8",
                character_count=len(text.encode("utf-16-le")) // 2,
                line_count=text.count("\n") + 1,
                status="unannotated",
            )
            db.add(doc)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="文本NER任务",
                task_type=AnnotationType.TEXT_NER,
                status="pending",
                assignees=[],
                classes=_TASK_CLASSES,
            )
            db.add(task)
            await db.flush()
            return doc.id, task.id

    return asyncio.run(_run())


def _make_dataset() -> int:
    """建一个独立数据集（用于无关任务归属校验），返回 ds_id。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5A无关数据集")
            db.add(ds)
            await db.flush()
            return ds.id

    return asyncio.run(_run())


def test_text_save_then_load_returns_same_batch():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    annotations = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
        {"id": "e2", "type": "EntitySpan", "start": 3, "end": 5, "label_id": 2, "text": "北京"},
        {"id": "r1", "type": "Relation", "from": "e1", "to": "e2", "relation_type": 1},
    ]

    result = asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, annotations, auth))
    assert result["version"] == 1
    assert result["annotation_count"] == 3

    loaded = asyncio.run(AnnotationService.load_text_annotations(task_id, document_id))
    assert loaded["annotation_data"] == annotations
    assert loaded["version"] == 1


def test_text_load_empty_returns_empty():
    document_id, task_id = _make_document_and_task()
    loaded = asyncio.run(AnnotationService.load_text_annotations(task_id, document_id))
    assert loaded == {"annotation_data": [], "version": 0}


def test_text_save_same_document_increments_version():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"}]

    r1 = asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    r2 = asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert r1["version"] == 1
    assert r2["version"] == 2


def test_text_save_invalid_task_relation_refused():
    """任务与文档无归属关系（不同数据集/错误类型/不存在）时保存应被拒绝。"""
    document_id, _ = _make_document_and_task()
    stray_dataset = _make_dataset()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"}]

    # 不同数据集的任务
    async def _stray_task(ds_id: int, task_type: AnnotationType) -> int:
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="无关任务",
                task_type=task_type,
                status="pending",
                assignees=[],
                classes=_TASK_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    stray_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.TEXT_NER))
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(stray_task, document_id, ann, auth))
    assert exc.value.status_code == 400

    # 任务类型不是 text_ner（视频任务）也应被拒绝
    video_task = asyncio.run(_stray_task(stray_dataset, AnnotationType.VIDEO_DETECTION))
    with pytest.raises(CustomException) as exc2:
        asyncio.run(AnnotationService.save_text_annotations(video_task, document_id, ann, auth))
    assert exc2.value.status_code == 400

    # 不存在的任务
    with pytest.raises(CustomException) as exc3:
        asyncio.run(AnnotationService.save_text_annotations(999999, document_id, ann, auth))
    assert exc3.value.status_code == 400


def test_text_save_invalid_entity_label_id():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 99, "text": "小明"}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert exc.value.status_code == 400


def test_text_save_entity_end_le_start():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    for bad in [
        {"start": 2, "end": 2},
        {"start": 3, "end": 2},
    ]:
        ann = [{"id": "e1", "type": "EntitySpan", "label_id": 1, "text": "小明", **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
        assert exc.value.status_code == 400


def test_text_save_entity_out_of_range():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    for bad in [
        {"start": -1, "end": 2},
        {"start": 0, "end": _CHAR_COUNT + 1},
    ]:
        ann = [{"id": "e1", "type": "EntitySpan", "label_id": 1, "text": "小明", **bad}]
        with pytest.raises(CustomException) as exc:
            asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
        assert exc.value.status_code == 400


def test_text_save_relation_unknown_type():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
        {"id": "e2", "type": "EntitySpan", "start": 3, "end": 5, "label_id": 2, "text": "北京"},
        {"id": "r1", "type": "Relation", "from": "e1", "to": "e2", "relation_type": 99},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert exc.value.status_code == 400


def test_text_save_relation_unknown_entity():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    # from 引用不存在的实体
    ann = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
        {"id": "r1", "type": "Relation", "from": "eX", "to": "e1", "relation_type": 1},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert exc.value.status_code == 400


def test_text_save_relation_before_entity_accepted():
    """Relation 出现在其引用 EntitySpan 之前时也应被接受（与输入顺序无关）。"""
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "r1", "type": "Relation", "from": "e1", "to": "e2", "relation_type": 1},
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
        {"id": "e2", "type": "EntitySpan", "start": 3, "end": 5, "label_id": 2, "text": "北京"},
    ]

    result = asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert result["version"] == 1
    assert result["annotation_count"] == 3


def test_text_save_overlap_rejected():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 5, "label_id": 1, "text": "小明在北"},
        {"id": "e2", "type": "EntitySpan", "start": 2, "end": 6, "label_id": 2, "text": "在北京"},
    ]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert exc.value.status_code == 400


def test_text_save_unknown_type_rejected():
    document_id, task_id = _make_document_and_task()
    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    ann = [{"id": "x", "type": "Unknown", "start": 0, "end": 2}]
    with pytest.raises(CustomException) as exc:
        asyncio.run(AnnotationService.save_text_annotations(task_id, document_id, ann, auth))
    assert exc.value.status_code == 400


def test_text_save_and_load_http(test_client, auth_headers, monkeypatch):
    """走 HTTP 接口：POST /anno/document/save 后 GET /anno/document/load 返回同一批。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"doc-http-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    doc_resp = test_client.post(
        f"/api/v1/annotation/document/upload?dataset_id={ds_id}",
        files={"file": ("doc.txt", _TEXT.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    assert doc_resp.status_code == 200, doc_resp.text
    doc_id = doc_resp.json()["data"]["id"]

    # 直接插入一条 text_ner 任务（避免依赖前端任务创建表单的 classes 结构注入）
    async def _add_task():
        async with async_db_session.begin() as db:
            task = AnnotationTaskModel(
                dataset_id=ds_id,
                name="文本NER任务",
                task_type=AnnotationType.TEXT_NER,
                status="pending",
                assignees=[],
                classes=_TASK_CLASSES,
            )
            db.add(task)
            await db.flush()
            return task.id

    task_id = asyncio.run(_add_task())

    annotations = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
    ]
    save_resp = test_client.post(
        "/api/v1/annotation/anno/document/save",
        json={"task_id": task_id, "document_id": doc_id, "annotations": annotations},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, save_resp.text
    assert save_resp.json()["data"]["version"] == 1

    load_resp = test_client.get(
        "/api/v1/annotation/anno/document/load",
        params={"task_id": task_id, "d_id": doc_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 200, load_resp.text
    assert load_resp.json()["data"]["annotation_data"] == annotations
    assert load_resp.json()["data"]["version"] == 1


def test_text_save_invalid_task_relation_http(test_client, auth_headers, monkeypatch):
    """HTTP 端到端：传入归属关系不存在的 task_id 时保存/读取应被拒绝。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds_resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"doc-http-bad-{uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert ds_resp.status_code == 200, ds_resp.text
    ds_id = ds_resp.json()["data"]["id"]

    doc_resp = test_client.post(
        f"/api/v1/annotation/document/upload?dataset_id={ds_id}",
        files={"file": ("doc.txt", _TEXT.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    assert doc_resp.status_code == 200, doc_resp.text
    doc_id = doc_resp.json()["data"]["id"]

    save_resp = test_client.post(
        "/api/v1/annotation/anno/document/save",
        json={"task_id": 999999, "document_id": doc_id, "annotations": []},
        headers=auth_headers,
    )
    assert save_resp.status_code == 400, save_resp.text

    load_resp = test_client.get(
        "/api/v1/annotation/anno/document/load",
        params={"task_id": 999999, "d_id": doc_id},
        headers=auth_headers,
    )
    assert load_resp.status_code == 400, load_resp.text
