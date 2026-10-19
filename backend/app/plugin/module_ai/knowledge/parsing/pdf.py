"""PDF 解析：文本层提取 + 逐页偏移 + 扫描件判定（OCR 由 MinerU 负责）。"""
from __future__ import annotations

import io
import re


def is_scanned(text: str, min_chars: int = 50) -> bool:
    """去空白后字符数低于阈值 → 视为扫描件（无有效文本层）。"""
    return len(re.sub(r"\s+", "", text or "")) < min_chars


def parse_pdf(data: bytes) -> tuple[str, list[int], dict]:
    """逐页提取文本，返回 ``(正文, 每页起始偏移, 元信息)``。"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    offsets: list[int] = []
    cursor = 0
    for page in reader.pages:
        offsets.append(cursor)
        try:
            page_text = page.extract_text() or ""
        except Exception:  # noqa: BLE001  个别页损坏不影响整篇
            page_text = ""
        parts.append(page_text)
        cursor += len(page_text) + 1
    text = "\n".join(parts)
    return text, offsets or [0], {"parser": "pypdf", "pages": len(reader.pages)}
