"""AI 助手上传文件处理：data URL 解析、文档文本抽取、图片识别（纯逻辑，无需 app）。"""
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
    imgs, doc = _process_uploaded_files([{"name": "a.jpg", "type": "image/jpeg", "dataUrl": data_url}])
    assert len(imgs) == 1
    assert doc == ""


def test_process_files_doc_extracts_text_context():
    data_url = f"data:text/plain;base64,{_B64('这里是文档内容')}"
    imgs, doc = _process_uploaded_files(
        [{"name": "说明.txt", "type": "text/plain", "dataUrl": data_url}]
    )
    assert imgs == []
    assert "这里是文档内容" in doc


def test_process_files_none_or_empty():
    assert _process_uploaded_files(None) == ([], "")
    assert _process_uploaded_files([]) == ([], "")


def test_process_files_invalid_data_url_skipped():
    imgs, doc = _process_uploaded_files(
        [{"name": "a.png", "type": "image/png", "dataUrl": "not-a-data-url"}]
    )
    assert imgs == []
    assert doc == ""
