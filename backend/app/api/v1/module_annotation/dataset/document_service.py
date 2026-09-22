"""文档上传 service：编码探测 + UTF-8 规范化 + RustFS 存储 + 去重 + 计数。

文本 NER 用。文件按扩展名白名单与大小（≤2MB）校验；读取字节后按
utf-8 → gbk → latin1 兜底探测原始编码，统一写回 UTF-8；以
sha256(UTF-8 内容) 去重；字符数用 UTF-16 code unit 数（与前端 offset 对齐）。
"""
import asyncio
import hashlib
import io
import uuid
from pathlib import Path

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.model import (
    AnnotationDocumentModel,
    DatasetModel,
    ImageStatus,
)
from app.core.audit import set_create_audit
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.s3_client import s3_client

ALLOWED_DOCUMENT_EXTENSIONS: set[str] = {
    ".txt", ".text", ".md", ".csv", ".tsv", ".json", ".log",
}

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024  # 2MB

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".txt": "text/plain",
    ".text": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".log": "text/plain",
}


def content_type_for(ext: str) -> str:
    """按扩展名返回 Content-Type，未知类型回退 octet-stream。"""
    return _EXT_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def _probe_encoding(content: bytes) -> tuple[str, str]:
    """探测原始编码，返回 ``(解码后的文本, 编码名)``。

    依次尝试 utf-8（严格）→ gbk；两者都失败则回退 latin1（永不失败）。
    """
    for enc in ("utf-8", "gbk"):
        try:
            return content.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return content.decode("latin1"), "latin1"


class DocumentService:

    @classmethod
    async def upload_document(cls, db, dataset_id: int, file, auth) -> AnnotationDocumentModel:
        """上传单个文本文档：编码探测、RustFS 存储、去重、入库并更新计数。

        ``db`` 为调用方传入的 async 会话（便于复用事务）；异常时删除已上传
        对象并重新抛出。
        """
        filename = file.filename or "unnamed"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise CustomException(
                msg=f"不支持的文档格式: {filename}", code=400, status_code=400
            )
        size = getattr(file, "size", None)
        if size is not None and size > MAX_DOCUMENT_BYTES:
            raise CustomException(
                msg=f"文件过大（>2MB）: {filename}", code=400, status_code=400
            )

        content = await file.read()
        if not content:
            raise CustomException(msg="上传内容为空", code=400, status_code=400)

        text, encoding = _probe_encoding(content)
        utf8_bytes = text.encode("utf-8")
        content_hash = hashlib.sha256(utf8_bytes).hexdigest()

        # 去重：同一数据集内相同 content_hash 直接返回已有记录
        existing = (
            await db.execute(
                select(AnnotationDocumentModel).where(
                    AnnotationDocumentModel.dataset_id == dataset_id,
                    AnnotationDocumentModel.content_hash == content_hash,
                    AnnotationDocumentModel.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().first()
        if existing:
            return existing

        object_key = f"datasets/{dataset_id}/documents/{uuid.uuid4().hex}{ext}"

        await asyncio.to_thread(
            s3_client.upload_fileobj,
            io.BytesIO(utf8_bytes),
            object_key,
            None,
            content_type_for(ext),
        )
        uploaded = True

        try:
            dataset = await db.get(DatasetModel, dataset_id)
            if not dataset or dataset.is_deleted:
                raise CustomException(
                    msg=f"数据集不存在: {dataset_id}", code=404, status_code=404
                )
            document = AnnotationDocumentModel(
                dataset_id=dataset_id,
                filename=filename,
                object_key=object_key,
                content_hash=content_hash,
                encoding=encoding,
                character_count=len(text.encode("utf-16-le")) // 2,
                line_count=text.count("\n") + 1,
                status=ImageStatus.UNANNOTATED,
            )
            set_create_audit(document, auth)
            db.add(document)
            await db.flush()
            dataset.document_count += 1
        except Exception:
            # 入库失败：删除本次已上传对象，避免孤儿
            if uploaded:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    log.warning(f"[文档上传] 补偿删除对象失败: {e2}")
            raise

        return document
