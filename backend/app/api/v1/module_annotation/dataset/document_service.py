"""文档上传 service：编码探测 + UTF-8 规范化 + RustFS 存储 + 去重 + 计数。

文本 NER 用。文件按扩展名白名单与大小（≤2MB）校验；读取字节后按
utf-8 → gbk → latin1 兜底探测原始编码，统一写回 UTF-8；以
sha256(UTF-8 内容) 去重；字符数用 UTF-16 code unit 数（与前端 offset 对齐）。
"""
import asyncio
import hashlib
import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.model import (
    AnnotationDocumentModel,
    DatasetModel,
    ImageStatus,
)
from app.core.audit import set_create_audit
from app.core.database import async_db_session
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

    LOCK_TIMEOUT_MINUTES = 5

    @classmethod
    async def list_documents(cls, dataset_id: int) -> list[dict]:
        """按数据集列出文档（不含已删除），仅返回元数据、不含全文。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AnnotationDocumentModel)
                    .where(
                        AnnotationDocumentModel.dataset_id == dataset_id,
                        AnnotationDocumentModel.is_deleted == False,  # noqa: E712
                    )
                    .order_by(AnnotationDocumentModel.id.desc())
                )
            ).scalars().all()
            return [cls.document_out(v) for v in rows]

    @classmethod
    async def get_document(cls, document_id: int) -> dict:
        """查询单个文档元数据，不存在抛 404。"""
        async with async_db_session() as db:
            doc = await db.get(AnnotationDocumentModel, document_id)
            if not doc or doc.is_deleted:
                raise CustomException(
                    msg=f"文档不存在: {document_id}", code=404, status_code=404
                )
            return cls.document_out(doc)

    @classmethod
    async def get_document_content(cls, document_id: int) -> str:
        """返回文档全文（UTF-8 解码）。存储内容已按 Task2 规范化为 UTF-8。"""
        async with async_db_session() as db:
            doc = await db.get(AnnotationDocumentModel, document_id)
            if not doc or doc.is_deleted:
                raise CustomException(
                    msg=f"文档不存在: {document_id}", code=404, status_code=404
                )
            object_key = doc.object_key
        buf = await asyncio.to_thread(s3_client.download_fileobj, object_key)
        return buf.read().decode("utf-8")

    @classmethod
    async def lock_document(cls, document_id: int, user_id: int) -> dict:
        """按文档整体上锁，被他人持有且未超时则返回冲突信息。"""
        async with async_db_session.begin() as db:
            doc = await db.get(AnnotationDocumentModel, document_id)
            if not doc or doc.is_deleted:
                raise CustomException(
                    msg=f"文档不存在: {document_id}", code=404, status_code=404
                )
            if doc.locked_by and doc.locked_at:
                if datetime.utcnow() - doc.locked_at > timedelta(minutes=cls.LOCK_TIMEOUT_MINUTES):
                    doc.locked_by = None
                    doc.locked_at = None
            if doc.locked_by and doc.locked_by != user_id:
                return {"locked": True, "locked_by": doc.locked_by}
            doc.locked_by = user_id
            doc.locked_at = datetime.utcnow()
            return {"locked": False, "locked_by": user_id}

    @classmethod
    async def unlock_document(cls, document_id: int, user_id: int) -> None:
        """解锁文档，仅锁持有者可解除。"""
        async with async_db_session.begin() as db:
            doc = await db.get(AnnotationDocumentModel, document_id)
            if doc and not doc.is_deleted and doc.locked_by == user_id:
                doc.locked_by = None
                doc.locked_at = None

    @classmethod
    def document_out(cls, doc: AnnotationDocumentModel) -> dict:
        """文档行 → 输出 dict（不含全文，status 序列化为字符串）。"""
        return {
            "id": doc.id,
            "dataset_id": doc.dataset_id,
            "filename": doc.filename,
            "object_key": doc.object_key,
            "content_hash": doc.content_hash,
            "encoding": doc.encoding,
            "character_count": doc.character_count,
            "line_count": doc.line_count,
            "status": doc.status.value if hasattr(doc.status, "value") else doc.status,
            "locked_by": doc.locked_by,
            "annotation_count": doc.annotation_count,
        }
