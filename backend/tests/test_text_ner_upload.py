"""文档上传 service 单测：白名单校验、编码探测、字符/行数/哈希、去重与失败清理。

仅 mock s3_client 与 db 会话，验证 DocumentService.upload_document 的核心行为。
"""
import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.module_annotation.dataset.document_service import DocumentService
from app.core.exceptions import CustomException


def _make_file(name, content, size=None):
    """构造一个模拟 UploadFile。"""
    f = AsyncMock()
    f.filename = name
    f.size = size if size is not None else len(content)
    f.read = AsyncMock(return_value=content)
    return f


def _make_db(dataset=None, existing=None):
    """构造一个模拟 async db 会话。

    - ``db.get`` 返回 ``dataset``
    - ``db.execute`` 用于去重查询，``.scalars().first()`` 返回 ``existing``
    """
    db = AsyncMock()
    db.get = AsyncMock(return_value=dataset)
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _dataset():
    ds = MagicMock()
    ds.id = 7
    ds.is_deleted = False
    ds.document_count = 0
    return ds


def _run(coro):
    return asyncio.run(coro)


# 一份中文 GBK 编码样本（utf-8 严格解码必然失败，从而触发 GBK 探测）
_GBK_TEXT = "你好，世界\n第二行内容\n"
_GBK_BYTES = _GBK_TEXT.encode("gbk")
_UTF8_BYTES = _GBK_TEXT.encode("utf-8")
_DIGEST = hashlib.sha256(_UTF8_BYTES).hexdigest()
_UTF16_UNITS = len(_GBK_TEXT.encode("utf-16-le")) // 2
_LINES = _GBK_TEXT.count("\n") + 1


def test_rejects_non_text_extension():
    # 白名单外的扩展名（如 .exe）应直接拒绝，不写对象也不入库。
    db = _make_db(dataset=_dataset())
    file = _make_file("malware.exe", b"hello")
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client") as s3:
        try:
            _run(DocumentService.upload_document(db, 7, file, auth=None))
        except CustomException as e:
            assert "不支持" in e.msg or "格式" in e.msg
        else:
            raise AssertionError("应抛出业务异常")
    s3.upload_fileobj.assert_not_called()
    db.add.assert_not_called()


def test_rejects_oversize_file():
    # 超过 2MB 应拒绝。
    db = _make_db(dataset=_dataset())
    file = _make_file("big.txt", b"x", size=2 * 1024 * 1024 + 1)
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client") as s3:
        try:
            _run(DocumentService.upload_document(db, 7, file, auth=None))
        except CustomException as e:
            assert "过大" in e.msg
        else:
            raise AssertionError("应抛出业务异常")
    s3.upload_fileobj.assert_not_called()


def test_encoding_probe_gbk():
    # GBK 样本应被正确探测为 gbk，且存储内容为 UTF-8 规范化结果。
    db = _make_db(dataset=_dataset())
    file = _make_file("sample.txt", _GBK_BYTES)
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client") as s3:
        doc = _run(DocumentService.upload_document(db, 7, file, auth=None))
    assert doc.encoding == "gbk"
    assert s3.upload_fileobj.called
    uploaded = s3.upload_fileobj.call_args[0][0]
    assert uploaded.getvalue() == _UTF8_BYTES


def test_encoding_probe_utf8():
    # UTF-8 样本应被探测为 utf-8。
    db = _make_db(dataset=_dataset())
    file = _make_file("sample2.txt", "纯文本内容".encode())
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client"):
        doc = _run(DocumentService.upload_document(db, 7, file, auth=None))
    assert doc.encoding == "utf-8"


def test_character_line_count_and_hash():
    # 校验字符数（UTF-16 code unit）、行数、内容哈希与 object_key。
    db = _make_db(dataset=_dataset())
    file = _make_file("sample.txt", _GBK_BYTES)
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client"):
        doc = _run(DocumentService.upload_document(db, 7, file, auth=None))
    assert doc.content_hash == _DIGEST
    assert doc.character_count == _UTF16_UNITS
    assert doc.line_count == _LINES
    assert doc.object_key.startswith("datasets/7/documents/")


def test_dedup_returns_existing_record():
    # 已存在相同 content_hash 时，应直接返回已有记录，不重复上传/入库。
    existing = MagicMock()
    existing.id = 99
    existing.content_hash = _DIGEST
    db = _make_db(dataset=_dataset(), existing=existing)
    file = _make_file("sample.txt", _GBK_BYTES)
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client") as s3:
        doc = _run(DocumentService.upload_document(db, 7, file, auth=None))
    assert doc is existing
    s3.upload_fileobj.assert_not_called()
    db.add.assert_not_called()


def test_failure_cleans_up_uploaded_object():
    # 入库失败（flush 抛错）时，应删除已上传对象并重新抛错。
    db = _make_db(dataset=_dataset())
    db.flush = AsyncMock(side_effect=RuntimeError("db boom"))
    file = _make_file("sample.txt", _GBK_BYTES)
    with patch("app.api.v1.module_annotation.dataset.document_service.s3_client") as s3:
        try:
            _run(DocumentService.upload_document(db, 7, file, auth=None))
        except RuntimeError:
            pass
        else:
            raise AssertionError("应重新抛出入库异常")
    s3.delete_object.assert_called()
