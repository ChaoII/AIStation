"""Step 2b：语义层草稿生成（只返回草稿，不落库）。

已有的 ``generate_asset_descriptions`` 是「批量直接写库」，适合全量重建；
本模块补的是「选几张表 → 生成草稿 → 人工确认/修改 → 再保存」的日常路径，
避免 AI 猜错时污染资产目录。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

MAX_TABLES = 20


class DraftColumn(BaseModel):
    """单列草稿。"""

    name: str
    description: str = ""


class DraftTable(BaseModel):
    """单表草稿。"""

    table: str
    alias: str = ""
    description: str = ""
    columns: list[DraftColumn] = []


class DraftResult(BaseModel):
    """模型返回结构。"""

    tables: list[DraftTable] = []


def build_draft_prompt(tables: dict[str, list[str]]) -> str:
    """按表结构拼提示词；不取样本值，避免把业务数据发出去。"""
    lines = [
        "你是数据库元数据专家。请为下面每张表生成简洁的中文业务描述，并给出每个字段的一句话说明。",
        "要求：",
        "1) 只描述业务含义，不推测数据内容；不确定就留空，不要编造。",
        "2) 表描述与字段说明各不超过 40 字。",
        "3) 必须原样返回表名与字段名，不要新增、改写或遗漏。",
        "4) 只输出 JSON，结构：{\"tables\":[{\"table\":\"...\",\"alias\":\"中文名\",\"description\":\"...\",\"columns\":[{\"name\":\"...\",\"description\":\"...\"}]}]}",
        "表清单：",
    ]
    for name, cols in tables.items():
        lines.append(f"- {name}: {', '.join(cols)}")
    return "\n".join(lines)


def filter_drafts(result: DraftResult, tables: dict[str, list[str]]) -> list[dict[str, Any]]:
    """只保留库里真实存在的表/列，模型幻觉出来的条目直接丢弃。"""
    out: list[dict[str, Any]] = []
    for item in result.tables:
        name = str(item.table or "").strip()
        known = tables.get(name)
        if known is None:
            # 大小写兜底（模型有时会改大小写）
            match = next((k for k in tables if k.lower() == name.lower()), None)
            if match is None:
                continue
            name = match
            known = tables[match]
        known_lower = {c.lower() for c in known}
        cols = []
        for col in item.columns:
            cname = str(col.name or "").strip()
            if cname.lower() not in known_lower:
                continue
            cols.append({"name": cname, "description": (col.description or "").strip()})
        out.append({
            "table": name,
            "alias": (item.alias or "").strip(),
            "description": (item.description or "").strip(),
            "columns": cols,
        })
    return out
