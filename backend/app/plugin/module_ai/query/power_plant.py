"""火电厂（燃煤业务库）数据整理的**纯逻辑**：前缀→业务域、表名/列名→关系推断、载荷构造。

刻意与 IO 解耦：测试库是 SQLite、没有该数据源的 schema，因此把这些规则做成纯函数，
单测用**合成记录**驱动（可跑 ``PYTEST_NO_APP=1`` 快速模式）。

设计见：本轮「火电厂数据集全流程」任务；数据源 = ``ezdcs_pg``（ds:4，331 张表）。
"""
from __future__ import annotations

import re

#: 核心业务域前缀（其余如 SYS_/VIEW_/U3D_ 属系统/技术/视图，不在本轮范围）。
CORE_PREFIXES: tuple[str, ...] = ("FUEL", "CMMS", "DTXY")

#: 前缀 → 业务域。**顺序敏感**（长前缀在前）。
DOMAIN_RULES: tuple[tuple[str, str], ...] = (
    ("FUEL_CB_", "燃煤采购结算"),
    ("FUEL_CMCS_", "燃料设备与化验"),
    ("FUEL_MIX_", "配煤掺烧"),
    ("FUEL_STG_", "燃料数据暂存"),
    ("FUEL_REPORT_", "燃料报表"),
    ("FUEL_INF_", "燃料接口"),
    ("FUEL_SIS_", "燃料SIS"),
    ("FUEL_JOB_", "燃料作业"),
    ("FUEL_", "燃料"),
    ("CMMS_", "组态与设备"),
    ("DTXY_", "供应商与品名"),
)

#: 可作主键的列名（按优先级）。
_KEY_CANDIDATES: tuple[str, ...] = ("ID", "Id", "id")
#: 可作显示名的列名（按优先级）。
_NAME_CANDIDATES: tuple[str, ...] = ("NAME", "Name", "name", "SHORTNAME", "TITLE")

#: 列名形如 ``xxxId`` / ``xxx_ID`` → 指向 ``xxx`` 主表。
_LINK_COL_RE = re.compile(r"^(.+?)(?:_?ID)$", re.IGNORECASE)


def is_core(table: str) -> bool:
    """是否属于本轮核心业务域。"""
    up = str(table or "").upper()
    return any(up.startswith(p) for p in CORE_PREFIXES)


def domain_of(table: str) -> str:
    """按前缀给出业务域；未匹配返回空串。"""
    up = f"{table}_".upper()
    for prefix, dom in DOMAIN_RULES:
        if up.startswith(prefix):
            return dom
    return ""


def table_tokens(table: str) -> list[str]:
    """表名的可匹配后缀。

    ``FUEL_CB_COALCONTRACT`` → ``["CB_COALCONTRACT", "COALCONTRACT"]``
    —— 这样列名 ``COALCONTRACTID`` 才能匹配到它。
    """
    parts = str(table or "").upper().split("_")
    return ["_".join(parts[i:]) for i in range(1, len(parts))]


def build_entity_index(tables: list[str]) -> dict[str, str]:
    """后缀 token → 表名（同 token 取字母序靠前者，保证确定性）。"""
    index: dict[str, str] = {}
    for t in sorted({str(x or "").upper() for x in tables}):
        for tok in table_tokens(t):
            index.setdefault(tok, t)
    return index


def find_key_col(columns: list[dict] | None) -> str:
    names = [str(c.get("name") or "") for c in (columns or [])]
    for want in _KEY_CANDIDATES:
        if want in names:
            return want
    return ""


def find_name_col(columns: list[dict] | None) -> str:
    names = [str(c.get("name") or "") for c in (columns or [])]
    for want in _NAME_CANDIDATES:
        if want in names:
            return want
    return ""


def infer_links(
    table: str,
    columns: list[dict] | None,
    entity_index: dict[str, str],
    has_id: dict[str, bool],
) -> list[dict]:
    """按「列名 ``xxxId`` → 表 token``xxx``」推断 ``many_to_one`` 关系（纯函数）。

    只保留：目标表存在、目标表有 ID 列、且非自引用；同一目标只保留第一条。
    """
    table_up = str(table or "").upper()
    out: list[dict] = []
    for c in columns or []:
        name = str(c.get("name") or "")
        m = _LINK_COL_RE.match(name)
        if not m:
            continue
        token = m.group(1).upper().strip("_")
        if len(token) < 3:
            continue
        tgt = entity_index.get(token)
        if not tgt or tgt == table_up or not has_id.get(tgt):
            continue
        out.append(
            {
                "source_object": table,
                "target_object": tgt,
                "name": tgt,
                "card": "many_to_one",
                "join_method": "foreign_key",
                "source_field": name,
                "target_field": "ID",
            }
        )
    seen: set[str] = set()
    uniq: list[dict] = []
    for link in out:
        if link["target_object"] in seen:
            continue
        seen.add(link["target_object"])
        uniq.append(link)
    return uniq


def asset_payload(record: dict, description: str | None = None) -> dict:
    """把一条同步记录转成 ``upsert_asset`` 需要的载荷（中文名取表注释）。"""
    table = str(record.get("table") or "")
    cols = record.get("columns") or []
    comment = str(record.get("comment") or "").strip()
    key = find_key_col(cols)
    return {
        "table_name": table,
        "alias": comment,
        "domain": domain_of(table),
        "description": (comment if description is None else description).strip(),
        "business_scenarios": "",
        "included": True,
        "remark": "",
        "object_enabled": bool(key),
        "object_key_col": key,
        "object_name_col": find_name_col(cols),
        "object_icon": "el-icon-Box",
    }


def column_payloads(record: dict) -> list[dict]:
    """把一条同步记录转成一组 ``upsert_asset_column`` 载荷（中文名取列注释）。"""
    table = str(record.get("table") or "")
    out: list[dict] = []
    for c in record.get("columns") or []:
        name = str(c.get("name") or "")
        if not name:
            continue
        out.append(
            {
                "table_name": table,
                "column_name": name,
                "description": str(c.get("comment") or "").strip(),
                "business_scenarios": "",
                "related_table": "",
                "related_field": "",
                "included": True,
                "sensitive": bool(c.get("is_sensitive")),
            }
        )
    return out
