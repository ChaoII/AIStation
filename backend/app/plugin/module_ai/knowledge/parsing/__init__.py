"""文档解析分派：按扩展名选择解析器，扫描件/图片走 MinerU OCR。

返回 :class:`ParsedDoc`（正文 + 每页起始偏移 + 元信息），供分块与引用溯源使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logger import log

from . import office, pdf, text as text_parser, web
from .mineru import parse_via_mineru

_IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp", "gif"}


@dataclass
class ParsedDoc:
    text: str
    page_offsets: list[int] = field(default_factory=lambda: [0])
    meta: dict = field(default_factory=dict)


def _suffix(filename: str) -> str:
    name = (filename or "").lower()
    return name.rsplit(".", 1)[-1] if "." in name else "txt"


async def parse_document(
    filename: str,
    data: bytes,
    *,
    use_ocr: bool = True,
    kb_id: int | None = None,
) -> ParsedDoc:
    """解析任意支持的文档；解析失败退化为文本解码（并记录 ``meta.fallback``）。"""
    suffix = _suffix(filename)
    try:
        if suffix in _IMAGE_SUFFIXES:
            if use_ocr:
                parsed = await parse_via_mineru(filename, data, kb_id=kb_id)
                if parsed:
                    body, offsets, meta = parsed
                    return ParsedDoc(body, offsets, meta)
            return ParsedDoc("", [0], {"parser": "image", "error": "OCR 不可用"})
        if suffix == "pdf":
            body, offsets, meta = pdf.parse_pdf(data)
            if pdf.is_scanned(body) and use_ocr:
                parsed = await parse_via_mineru(filename, data, kb_id=kb_id)
                if parsed:
                    body, offsets, meta = parsed
                    meta["ocr"] = True
                else:
                    log.warning("[RAG] PDF 疑似扫描件但 MinerU 不可用")
            return ParsedDoc(body, offsets, meta)
        if suffix == "docx":
            body, meta = office.parse_docx(data)
            return ParsedDoc(body, [0], meta)
        if suffix in ("xlsx", "xls"):
            body, meta = office.parse_xlsx(data)
            return ParsedDoc(body, [0], meta)
        if suffix in ("html", "htm"):
            return ParsedDoc(web.parse_html(text_parser.decode_text(data)), [0], {"parser": "html"})
        body, meta = text_parser.parse_text_file(filename, data)
        return ParsedDoc(body, [0], meta)
    except Exception as e:  # noqa: BLE001  兜底：按文本读取
        log.warning(f"[RAG] 解析 {filename} 失败，退化为文本：{e}")
        return ParsedDoc(
            text_parser.decode_text(data),
            [0],
            {"parser": "fallback", "fallback": True, "error": str(e)},
        )
