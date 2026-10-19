"""文本类解析：编码探测与 CSV→Markdown 表格。"""
from __future__ import annotations

import csv
import io


def decode_text(data: bytes) -> str:
    """按 BOM → utf-8 → gbk → 宽松 utf-8 的顺序解码。

    二进制文件（图片等）也可能走到这里，务必剔除 NUL：PostgreSQL 的 text 列
    不接受 ``0x00``，否则入库会报 ``CharacterNotInRepertoireError``。
    """
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding).replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").replace("\x00", "")


def csv_to_markdown(text: str) -> str:
    """CSV 文本转 Markdown 管道表（首行为表头）。"""
    rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    if not rows:
        return text
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    def _fmt(row: list[str]) -> str:
        cells = [str(cell).replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        return "| " + " | ".join(cells) + " |"

    body = [_fmt(rows[0]), "| " + " | ".join(["---"] * width) + " |"]
    body.extend(_fmt(row) for row in rows[1:])
    return "\n".join(body)


def parse_text_file(filename: str, data: bytes) -> tuple[str, dict]:
    """解析纯文本类文件，返回 ``(正文, 元信息)``。"""
    text = decode_text(data)
    suffix = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else "txt"
    if suffix == "csv":
        return csv_to_markdown(text), {"parser": "csv"}
    return text, {"parser": "text"}
