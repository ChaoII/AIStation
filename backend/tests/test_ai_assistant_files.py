"""AI 助手上传文件处理：data URL 解析、文档文本抽取、图片识别、个人空间引用（纯逻辑，无需 app）。"""
import asyncio
import base64

from app.plugin.module_ai.assistant.agno_service import (
    _extract_doc_text,
    _parse_data_uri,
    _process_uploaded_files,
)


def _B64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def test_parse_data_uri_image():
    data_url = f"data:image/png;base64,{_B64('x')}"
    raw, mime = _parse_data_uri(data_url)
    assert raw == b"x"
    assert mime == "image/png"


def test_parse_data_uri_invalid():
    assert _parse_data_uri("garbage") == (b"", "")
    assert _parse_data_uri("") == (b"", "")


def test_extract_doc_text_txt():
    assert _extract_doc_text("你好".encode(), "text/plain", "a.txt") == "你好"


def test_extract_doc_text_unknown_format_returns_empty():
    assert _extract_doc_text(b"whatever", "application/octet-stream", "a.bin") == ""


def test_process_files_image_returns_agno_image():
    data_url = f"data:image/jpeg;base64,{_B64('img')}"
    imgs, doc = asyncio.run(
        _process_uploaded_files([{"name": "a.jpg", "type": "image/jpeg", "dataUrl": data_url}])
    )
    assert len(imgs) == 1
    assert doc == ""


def test_process_files_doc_extracts_text_context():
    data_url = f"data:text/plain;base64,{_B64('这里是文档内容')}"
    imgs, doc = asyncio.run(
        _process_uploaded_files(
            [{"name": "说明.txt", "type": "text/plain", "dataUrl": data_url}]
        )
    )
    assert imgs == []
    assert "这里是文档内容" in doc


def test_process_files_none_or_empty():
    assert asyncio.run(_process_uploaded_files(None)) == ([], "")
    assert asyncio.run(_process_uploaded_files([])) == ([], "")


def test_process_files_invalid_data_url_skipped():
    imgs, doc = asyncio.run(
        _process_uploaded_files(
            [{"name": "a.png", "type": "image/png", "dataUrl": "not-a-data-url"}]
        )
    )
    assert imgs == []


def test_process_files_workspace_image(monkeypatch):
    """个人空间引用：图片 → Agno Image。"""
    import app.plugin.module_ai.assistant.agno_service as svc

    async def fake(file_id, user_id):
        return {"data": b"img", "mime_type": "image/png", "name": "a.png", "file_type": "image"}

    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = asyncio.run(
        _process_uploaded_files([{"type": "workspace", "file_id": 1, "name": "a.png"}], user_id=7)
    )
    assert len(imgs) == 1 and doc == ""


def test_process_files_workspace_doc_extracts_text(monkeypatch):
    """个人空间引用：文档 → 抽取文本进上下文。"""
    import app.plugin.module_ai.assistant.agno_service as svc

    async def fake(file_id, user_id):
        return {
            "data": "这是文档内容".encode(),
            "mime_type": "text/plain",
            "name": "说明.txt",
            "file_type": "txt",
        }

    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = asyncio.run(
        _process_uploaded_files(
            [{"type": "workspace", "file_id": 1, "name": "说明.txt"}], user_id=7
        )
    )
    assert imgs == [] and "这是文档内容" in doc


def test_process_files_workspace_missing_skipped(monkeypatch):
    """个人空间引用失败（越权/不存在）→ 返回 None → 跳过不阻断对话。"""
    import app.plugin.module_ai.assistant.agno_service as svc

    async def fake(file_id, user_id):
        return None

    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = asyncio.run(
        _process_uploaded_files([{"type": "workspace", "file_id": 99}], user_id=7)
    )
    assert imgs == [] and doc == ""
    assert doc == ""
