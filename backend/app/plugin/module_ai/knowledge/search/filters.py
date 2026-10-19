"""检索结果过滤与去重。

支持的元数据过滤键（其余键忽略，避免调用方拼错就报错）：
- ``file_name``：精确匹配文件名
- ``document_id``：精确匹配文档 ID
- ``file_type``：按扩展名匹配（如 ``pdf``）
- ``since`` / ``until``：ISO 字符串，按 ``created_time`` 过滤（行内含该字段时生效）
"""
from __future__ import annotations


def _file_type(row: dict) -> str:
    name = str(row.get("file_name") or "")
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _time_in_range(value, since: str | None, until: str | None) -> bool:
    if not value:
        return True
    text = str(value)
    if since and text < str(since):
        return False
    if until and text > str(until):
        return False
    return True


def match_filters(row: dict, filters: dict | None) -> bool:
    """单条结果是否满足元数据过滤条件。"""
    if not filters:
        return True
    if filters.get("file_name") and row.get("file_name") != filters["file_name"]:
        return False
    doc_id = filters.get("document_id")
    if doc_id is not None and row.get("document_id") != doc_id:
        return False
    if filters.get("file_type") and _file_type(row) != str(filters["file_type"]).lower():
        return False
    return _time_in_range(row.get("created_time"), filters.get("since"), filters.get("until"))


def apply_filters(rows: list[dict], filters: dict | None) -> list[dict]:
    if not filters:
        return rows
    return [row for row in rows if match_filters(row, filters)]


def drop_duplicates(rows: list[dict]) -> list[dict]:
    """按 ``(file_name, content)`` 去重，保留先出现（通常分数更高）的一条。"""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in rows:
        key = (str(row.get("file_name") or ""), str(row.get("content") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
