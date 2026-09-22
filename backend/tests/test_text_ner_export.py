"""文本 NER 导出测试（字符级 BIO/BIESO + 关系）。

验证：对 ``text_ner`` 数据集每个文档读全文 + ``load_text_annotations``，
生成 ``<stem>_{document_id}.txt``（按换行分句，每句逐字符 ``字符\\tBIO标签``，
句间空行）与 ``<stem>_{document_id}.relations.jsonl``。关键回归：训练/评估路径
经 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入时，
标注读取必须用「标注任务 id」（同视频导出修复，不得把训练任务 id 误传）。
抽帧/下载/标注全部 mock，外部调用（s3/DB）按既有导出测试方式处理。
"""
import asyncio
import json
import os
from io import BytesIO

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationDocumentModel,
    AnnotationType,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.plugin.module_train.exporter import _export_core, _export_text_ner

_TASK_CLASSES = {
    "entities": [{"id": 1, "name": "人名"}, {"id": 2, "name": "地名"}],
    "relations": [{"id": 1, "name": "任职"}, {"id": 2, "name": "位于"}],
}

# 中文文本：两句，各自含实体；用于 BIO/BIESO 序列与多句空行校验
_TEXT = "小明在北京工作\n他喜欢上海。\n"


def _make_document_and_task(text: str = _TEXT) -> tuple[int, int, int]:
    """建数据集 + 文档 + text_ner 任务，返回 (dataset_id, document_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5导出文本集")
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
            return ds.id, doc.id, task.id

    return asyncio.run(_run())


def _patch_text_mocks(monkeypatch, text: str, annotations: list[dict]):
    """打桩文档下载 + 逐文档标注读取的可复用夹具。"""
    async def _load(t, d):
        return {"annotation_data": annotations, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_text_annotations", _load)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(
        s3_client, "download_fileobj", lambda key: BytesIO(text.encode("utf-8"))
    )
    return text


_ENTITIES_BIO = [
    {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
    {"id": "e2", "type": "EntitySpan", "start": 3, "end": 5, "label_id": 2, "text": "北京"},
    {"id": "e3", "type": "EntitySpan", "start": 11, "end": 13, "label_id": 2, "text": "上海"},
]


def test_text_export_bio_sequence(monkeypatch, tmp_path):
    """BIO：逐字符标签正确，多句间空行，文件名含 document_id。"""
    ds_id, doc_id, task_id = _make_document_and_task()
    _patch_text_mocks(monkeypatch, _TEXT, _ENTITIES_BIO)
    out = str(tmp_path / "out")

    asyncio.run(_export_text_ner(ds_id, out, annotation_task_id=task_id))

    txt_path = os.path.join(out, f"doc_{doc_id}.txt")
    assert os.path.exists(txt_path)
    content = open(txt_path, encoding="utf-8").read().rstrip("\n")
    expected = "\n".join([
        "小\tB-人名", "明\tI-人名", "在\tO", "北\tB-地名", "京\tI-地名", "工\tO", "作\tO",
        "",
        "他\tO", "喜\tO", "欢\tO", "上\tB-地名", "海\tI-地名", "。\tO",
    ])
    assert content == expected


def test_text_export_bieso_sequence(monkeypatch, tmp_path):
    """BIESO：单字实体 S、多字首 B / 尾 E、其余 I。"""
    ds_id, doc_id, task_id = _make_document_and_task()
    entities = [
        {"id": "e1", "type": "EntitySpan", "start": 0, "end": 2, "label_id": 1, "text": "小明"},
        {"id": "e2", "type": "EntitySpan", "start": 3, "end": 5, "label_id": 2, "text": "北京"},
        {"id": "e3", "type": "EntitySpan", "start": 8, "end": 9, "label_id": 1, "text": "他"},
        {"id": "e4", "type": "EntitySpan", "start": 11, "end": 13, "label_id": 2, "text": "上海"},
    ]
    _patch_text_mocks(monkeypatch, _TEXT, entities)
    out = str(tmp_path / "outbieso")

    asyncio.run(_export_text_ner(ds_id, out, annotation_task_id=task_id, mode="bieso"))

    txt_path = os.path.join(out, f"doc_{doc_id}.txt")
    assert os.path.exists(txt_path)
    content = open(txt_path, encoding="utf-8").read().rstrip("\n")
    expected = "\n".join([
        "小\tB-人名", "明\tE-人名", "在\tO", "北\tB-地名", "京\tE-地名", "工\tO", "作\tO",
        "",
        "他\tS-人名", "喜\tO", "欢\tO", "上\tB-地名", "海\tE-地名", "。\tO",
    ])
    assert content == expected


def test_text_export_relations_jsonl(monkeypatch, tmp_path):
    """relations.jsonl：每行一个关系 {from,to,relation_type,label}，label 取类名。"""
    ds_id, doc_id, task_id = _make_document_and_task()
    annotations = _ENTITIES_BIO + [
        {"id": "r1", "type": "Relation", "from": "e1", "to": "e2", "relation_type": 1},
        {"id": "r2", "type": "Relation", "from": "e2", "to": "e3", "relation_type": 2},
    ]
    _patch_text_mocks(monkeypatch, _TEXT, annotations)
    out = str(tmp_path / "outrel")

    asyncio.run(_export_text_ner(ds_id, out, annotation_task_id=task_id))

    rel_path = os.path.join(out, f"doc_{doc_id}.relations.jsonl")
    assert os.path.exists(rel_path)
    rows = [
        json.loads(line)
        for line in open(rel_path, encoding="utf-8").read().strip().splitlines()
    ]
    assert rows == [
        {"from": "e1", "to": "e2", "relation_type": 1, "label": "任职"},
        {"from": "e2", "to": "e3", "relation_type": 2, "label": "位于"},
    ]


def test_text_export_through_core_entry(monkeypatch, tmp_path):
    """真实入口 ``_export_core``：text_ner 数据集应走到文本导出并产出文件。

    回归：若按图片空集提前 return，文本导出永远不会执行。
    """
    ds_id, doc_id, task_id = _make_document_and_task()
    _patch_text_mocks(monkeypatch, _TEXT, _ENTITIES_BIO)
    out = str(tmp_path / "outcore")

    asyncio.run(_export_core(ds_id, task_id, "ultralytics", out, annotation_task_id=task_id))

    assert os.path.exists(os.path.join(out, f"doc_{doc_id}.txt"))


def test_text_export_training_path_uses_annotation_task_id(monkeypatch, tmp_path):
    """训练式路径回归：传入的训练任务 id 与标注任务 id 不同仍导出。

    训练/评估 pipeline 通过 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
    进入；标注读取必须用「标注任务 id」，否则 ``_verify_document_task_relation`` 拒绝、
    导致标注静默为空。断言实际传给 ``load_text_annotations`` 的确实是标注任务 id，
    且 BIO 文件确实产出（非空）。
    """
    ds_id, doc_id, ann_task_id = _make_document_and_task()
    train_task_id = 9999  # 模拟训练任务 id，与标注任务 id 不同

    seen_ids: list[int] = []

    async def _load(task_id, d_id):
        seen_ids.append(task_id)
        return {"annotation_data": _ENTITIES_BIO, "version": 1}

    monkeypatch.setattr(AnnotationService, "load_text_annotations", _load)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(
        s3_client, "download_fileobj", lambda key: BytesIO(_TEXT.encode("utf-8"))
    )

    out = str(tmp_path / "outtrain")
    asyncio.run(_export_core(
        ds_id, train_task_id, "ultralytics", out, annotation_task_id=ann_task_id,
    ))

    assert seen_ids and all(i == ann_task_id for i in seen_ids), seen_ids
    txt_path = os.path.join(out, f"doc_{doc_id}.txt")
    assert os.path.exists(txt_path)
    # 标注确实被读出并写入（否则 load 失败被吞掉会得到全 O）
    content = open(txt_path, encoding="utf-8").read()
    assert "B-人名" in content
