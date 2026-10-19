"""Office 解析：docx（段落 + 表格）、xlsx/xls（多 sheet 表格）。

表格统一转成 Markdown 管道表，便于分块后仍保留表头结构。
"""
from __future__ import annotations

import io


def table_to_markdown(rows: list[list[str]]) -> str:
    """二维单元格转 Markdown 管道表（列数取最大、空单元格补齐、转义竖线）。"""
    cleaned = [
        [str(cell or "").replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        for row in rows
        if row
    ]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]

    def _fmt(row: list[str]) -> str:
        return "| " + " | ".join(row) + " |"

    lines = [_fmt(cleaned[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(_fmt(row) for row in cleaned[1:])
    return "\n".join(lines)


def parse_docx(data: bytes) -> tuple[str, dict]:
    """docx：段落按原顺序拼接，表格转为 Markdown 管道表（表格附在正文后）。"""
    from docx import Document

    document = Document(io.BytesIO(data))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if text:
            style = getattr(paragraph.style, "name", "") or ""
            if style.lower().startswith("heading"):
                level = "".join(ch for ch in style if ch.isdigit()) or "1"
                parts.append(f"{'#' * min(int(level), 6)} {text}")
            else:
                parts.append(text)
    tables: list[str] = []
    for table in document.tables:
        rows = [[cell.text or "" for cell in row.cells] for row in table.rows]
        markdown = table_to_markdown(rows)
        if markdown:
            tables.append(markdown)
    if tables:
        parts.append("")
        parts.append("\n\n".join(tables))
    return "\n\n".join(parts), {"parser": "docx", "tables": len(tables)}


def parse_xlsx(data: bytes) -> tuple[str, dict]:
    """xlsx/xls：每个 sheet 输出「## sheet 名 + Markdown 表」。"""
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in workbook.worksheets:
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
        rows = [row for row in rows if any(str(cell).strip() for cell in row)]
        if not rows:
            continue
        parts.append(f"## {sheet.title}")
        markdown = table_to_markdown(rows)
        if markdown:
            parts.append(markdown)
    return "\n\n".join(parts), {"parser": "xlsx", "sheets": len(workbook.worksheets)}
