"""文本 NER / 音频事件 / 时间序列事件 / 视频事件导出

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import os

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.logger import log


def _iter_sentence_spans(text: str):
    """按换行切分句子，产出 ``(句子, 句首绝对 UTF-16 偏移)``。

    偏移以 UTF-16 code unit 计（与前端/CodeMirror 一致）；每个换行符占 1 个
    code unit，逐句累加得到全局偏移，用于把文档级实体 span 映射到句内。
    """
    pos = 0
    for line in text.split("\n"):
        yield line, pos
        pos += len(line.encode("utf-16-le")) // 2 + 1


def _line_bio_tags(line: str, entities: list[dict], mode: str) -> list[str]:
    """对单个句子按句内 UTF-16 偏移计算逐字符 BIO/BIESO 标签。

    ``entities`` 为该句内实体（``start/end`` 为句内 UTF-16 偏移，含 ``label`` 名称）。
    每个字符（code point）产出一个标签，字符的 UTF-16 宽度按 BMP=1、代理对=2 累加，
    因此多 code unit 字符也能与实体偏移精确对应。``mode`` 为 ``bio`` 或 ``bieso``：
    - ``bio``：实体首字符 ``B-``，其余 ``I-``；
    - ``bieso``：单字符实体 ``S-``，多字符首 ``B-``、尾 ``E-``、中间 ``I-``。
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    for ch in line:
        width = len(ch.encode("utf-16-le")) // 2
        spans.append((pos, pos + width))
        pos += width

    tags: list[str] = []
    for cs, ce in spans:
        tag = "O"
        for ent in entities:
            if ent["start"] <= cs and ce <= ent["end"]:
                first = cs == ent["start"]
                last = ce == ent["end"]
                single = (ent["end"] - ent["start"]) == (ce - cs)
                if first and last and single and mode == "bieso":
                    tag = f"S-{ent['label']}"
                elif first:
                    tag = f"B-{ent['label']}"
                elif last and mode == "bieso":
                    tag = f"E-{ent['label']}"
                else:
                    tag = f"I-{ent['label']}"
                break
        tags.append(tag)
    return tags


async def _export_text_ner(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    mode: str = "bio",
) -> None:
    """文本 NER 导出：字符级 BIO/BIESO 序列 + 关系 JSONL。

    对数据集每个文档：读全文（RustFS，UTF-8）+ ``load_text_annotations`` 取标注，
    生成 ``<stem>_{document_id}.txt``（按换行分句，每句逐字符 ``字符\\t标签``，句间空行）
    与 ``<stem>_{document_id}.relations.jsonl``（每行一个关系）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_document_task_relation`` 拒绝、导致标注静默为空。
    """
    import asyncio

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationDocumentModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel
    from app.utils.s3_client import s3_client

    os.makedirs(output_dir, exist_ok=True)
    entity_names: dict[int, str] = {}
    relation_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, dict):
                for e in ann_task.classes.get("entities", []):
                    entity_names[int(e["id"])] = e.get("name", f"class_{e['id']}")
                for r in ann_task.classes.get("relations", []):
                    relation_names[int(r["id"])] = r.get("name", f"class_{r['id']}")

    async with async_db_session() as db:
        docs = (await db.execute(
            select(AnnotationDocumentModel).where(
                AnnotationDocumentModel.dataset_id == dataset_id,
                AnnotationDocumentModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not docs:
        log.warning(f"text-ner export: dataset {dataset_id} has no documents")
        return

    for doc in docs:
        data = await asyncio.to_thread(s3_client.download_fileobj, doc.object_key)
        text = data.read().decode("utf-8")
        anns = await AnnotationService.load_text_annotations(annotation_task_id, doc.id)
        ann_data = anns.get("annotation_data") or []
        entities = [a for a in ann_data if a.get("type") == "EntitySpan"]
        relations = [a for a in ann_data if a.get("type") == "Relation"]

        stem = os.path.splitext(doc.filename)[0] or f"doc_{doc.id}"
        # 构造 BIO/BIESO 序列：逐句映射文档级实体到句内偏移
        blocks: list[list[str]] = []
        for sentence, abs_start in _iter_sentence_spans(text):
            if not sentence:
                continue
            line_len = len(sentence.encode("utf-16-le")) // 2
            local_entities = [
                {
                    "start": e["start"] - abs_start,
                    "end": e["end"] - abs_start,
                    "label": entity_names.get(
                        int(e["label_id"]), f"class_{e['label_id']}"
                    ),
                }
                for e in entities
                if e["start"] >= abs_start and e["end"] <= abs_start + line_len
            ]
            tags = _line_bio_tags(sentence, local_entities, mode)
            blocks.append([f"{ch}\t{tag}" for ch, tag in zip(sentence, tags, strict=True)])

        seq_lines: list[str] = []
        for i, block in enumerate(blocks):
            seq_lines.extend(block)
            if i < len(blocks) - 1:
                seq_lines.append("")
        txt_path = os.path.join(output_dir, f"{stem}_{doc.id}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(seq_lines) + ("\n" if seq_lines else ""))

        # 关系 JSONL：每行一个关系
        rel_path = os.path.join(output_dir, f"{stem}_{doc.id}.relations.jsonl")
        with open(rel_path, "w", encoding="utf-8") as f:
            for rel in relations:
                rt = rel.get("relation_type")
                f.write(json.dumps({
                    "from": rel.get("from"),
                    "to": rel.get("to"),
                    "relation_type": rt,
                    "label": relation_names.get(
                        int(rt), f"class_{rt}" if rt is not None else "class_None"
                    ),
                }, ensure_ascii=False) + "\n")


async def _export_audio_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """音频事件导出：SED 事件 JSONL（可选 CSV）。

    对数据集每个音频用 ``load_audio_annotations`` 读事件标注，生成
    ``<stem>_{audio_id}.jsonl``（每行 ``{"start","end","label"}``，秒级 float，
    label 取任务 ``classes`` 中 ``label_id`` 对应的名称）；``csv=True`` 时再产出
    ``<stem>_{audio_id}.csv``（表头 ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_audio_task_relation`` 拒绝、导致标注静默为空。
    音频事件导出只依赖标注元数据，无需下载音频文件本身。
    """

    if not annotation_task_id:
        log.warning(f"audio-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationAudioModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        audios = (await db.execute(
            select(AnnotationAudioModel).where(
                AnnotationAudioModel.dataset_id == dataset_id,
                AnnotationAudioModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not audios:
        log.warning(f"audio-event export: dataset {dataset_id} has no audios")
        return

    for audio in audios:
        anns = await AnnotationService.load_audio_annotations(annotation_task_id, audio.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "AudioSegment"]
        stem = os.path.splitext(audio.name)[0] or f"audio_{audio.id}"
        base = os.path.join(output_dir, f"{stem}_{audio.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": float(ev["start"]),
                    "end": float(ev["end"]),
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{float(ev['start'])},{float(ev['end'])},{label}\n")


async def _export_time_series_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """时间序列区间事件导出：区间 JSONL（可选 CSV）。

    对数据集每个时间序列用 ``load_time_series_annotations`` 读区间标注，生成
    ``<stem>_{time_series_id}.jsonl``（每行 ``{"start","end","label"}``，start/end
    为该序列时间戳值并保留原始精度，label 取任务 ``classes`` 中 ``label_id`` 对应
    的名称）；``csv=True`` 时再产出 ``<stem>_{time_series_id}.csv``（表头
    ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_time_series_task_relation`` 拒绝、导致标注静默为空。
    时间序列事件导出只依赖标注元数据，无需下载序列文件本身。
    """

    if not annotation_task_id:
        log.warning(f"time-series-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationTimeSeriesModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        series_list = (await db.execute(
            select(AnnotationTimeSeriesModel).where(
                AnnotationTimeSeriesModel.dataset_id == dataset_id,
                AnnotationTimeSeriesModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not series_list:
        log.warning(f"time-series-event export: dataset {dataset_id} has no time series")
        return

    for series in series_list:
        anns = await AnnotationService.load_time_series_annotations(annotation_task_id, series.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "TimeSeriesSegment"]
        stem = os.path.splitext(series.name)[0] or f"time_series_{series.id}"
        base = os.path.join(output_dir, f"{stem}_{series.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": ev["start"],
                    "end": ev["end"],
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{ev['start']},{ev['end']},{label}\n")


async def _export_video_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """视频时间轴事件导出：区间事件 JSONL（可选 CSV）。

    对数据集每个视频用 ``load_video_event_annotations`` 读事件标注，生成
    ``<stem>_{video_id}.jsonl``（每行 ``{"start","end","label"}``，秒级 float，
    label 取任务 ``classes`` 中 ``label_id`` 对应的名称）；``csv=True`` 时再产出
    ``<stem>_{video_id}.csv``（表头 ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_video_event_task_relation`` 拒绝、导致标注静默为空。
    视频事件导出只依赖标注元数据，无需下载视频文件本身。
    """

    if not annotation_task_id:
        log.warning(f"video-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationVideoModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        videos = (await db.execute(
            select(AnnotationVideoModel).where(
                AnnotationVideoModel.dataset_id == dataset_id,
                AnnotationVideoModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not videos:
        log.warning(f"video-event export: dataset {dataset_id} has no videos")
        return

    for video in videos:
        anns = await AnnotationService.load_video_event_annotations(annotation_task_id, video.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "VideoSegment"]
        stem = os.path.splitext(video.name)[0] or f"video_{video.id}"
        base = os.path.join(output_dir, f"{stem}_{video.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": float(ev["start"]),
                    "end": float(ev["end"]),
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{float(ev['start'])},{float(ev['end'])},{label}\n")
