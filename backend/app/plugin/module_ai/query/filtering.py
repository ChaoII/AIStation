"""通用筛选规则引擎（纯逻辑）。

背景：每个数据源可配置一套规则，用于自动分类：
- **业务表 / 系统表**（系统表通常来自框架/运维，如 alembic、定时任务表）；
- **业务字段 / 审计字段**（审计字段由框架统一注入，如 created_time、is_deleted）。

本模块只做**纯逻辑匹配**，不触碰数据库：给定表名/字段名 + 规则字典，
返回是否为系统表/审计字段。后续 Task 会消费 `DEFAULT_FILTER_RULES`、
`is_system_table`、`is_audit_field`。
"""
from __future__ import annotations

import re
from typing import Any

# 缺省规则：前缀、关键词、精确名、正则、审计字段名集合。
DEFAULT_FILTER_RULES: dict[str, Any] = {
    "enabled": True,
    "system_table": {
        "prefixes": ["SYS_", "FUEL_", "VIEW_", "V_"],
        "keywords": ["_BAK", "_temp", "log", "history", "_log"],
        "exact": ["alembic_version", "apscheduler_jobs", "__EFMigrationsHistory"],
        "regex": "",
    },
    "audit_fields": [
        "is_deleted",
        "deleted_time",
        "created_time",
        "updated_time",
        "deleted_id",
        "created_id",
        "updated_id",
        "tenant_id",
        "created_by",
        "updated_by",
    ],
}


def _norm(value: Any) -> str:
    """统一转成小写字符串，用于大小写不敏感匹配。"""
    return str(value or "").lower()


def _match_system_table(name: str, table_cfg: dict[str, Any]) -> tuple[bool, str]:
    """按系统表规则配置匹配表名，返回 ``(是否命中, 命中原因)``。

    命中优先级：prefix → keyword → exact → regex（均大小写不敏感）。
    命中原因使用规则中**原始大小写**的取值；未命中时 reason 为空字符串。
    """
    table = _norm(name)

    # 前缀匹配（大小写不敏感）
    for prefix in table_cfg.get("prefixes") or []:
        if table.startswith(_norm(prefix)):
            return True, f"前缀 {prefix}"

    # 关键词包含（大小写不敏感）
    for keyword in table_cfg.get("keywords") or []:
        if _norm(keyword) in table:
            return True, f"关键词 {keyword}"

    # 精确匹配（大小写不敏感）
    for exact in table_cfg.get("exact") or []:
        if table == _norm(exact):
            return True, f"精确表名 {exact}"

    # 正则匹配（大小写不敏感）
    regex = table_cfg.get("regex") or ""
    if regex:
        try:
            if re.search(regex, table, re.IGNORECASE):
                return True, f"正则 {regex}"
        except re.error:  # noqa: PERF203 - 正则非法时忽略该项，避免单条规则拖垮整个判定
            pass

    return False, ""


def _match_audit_field(name: str, audit_fields: list[Any]) -> tuple[bool, str]:
    """按审计字段规则配置匹配字段名，返回 ``(是否命中, 命中原因)``。

    在 ``audit_fields`` 中做大小写不敏感精确匹配，命中第一个即返回
    ``"审计字段 <字段名>"``（使用规则中原始大小写的字段名）。
    """
    field = _norm(name)
    for f in audit_fields:
        if _norm(f) == field:
            return True, f"审计字段 {f}"
    return False, ""


def classify_tables(tables: list[str], rules: dict | None = None) -> list[dict]:
    """分类给定表名列表，返回每项 ``{"name", "is_system", "reason"}``。

    规则来源：``rules`` 为 ``None`` 时使用 ``DEFAULT_FILTER_RULES``；否则使用传入规则。
    命中任一条件（前缀/关键词/精确名/正则）即为系统表，``reason`` 说明命中的规则项。
    规则 ``enabled`` 为 ``False`` 时一律返回 ``is_system=False``、``reason=""``。
    """
    cfg = rules if rules is not None else DEFAULT_FILTER_RULES
    enabled = bool(cfg.get("enabled", True))
    table_cfg = cfg.get("system_table") or {}
    results: list[dict] = []
    for name in tables:
        if not enabled:
            results.append({"name": str(name), "is_system": False, "reason": ""})
            continue
        is_system, reason = _match_system_table(name, table_cfg)
        results.append({"name": str(name), "is_system": is_system, "reason": reason})
    return results


def classify_fields(fields: list[str], rules: dict | None = None) -> list[dict]:
    """分类给定字段名列表，返回每项 ``{"name", "is_audit", "reason"}``。

    规则来源：``rules`` 为 ``None`` 时使用 ``DEFAULT_FILTER_RULES``；否则使用传入规则。
    在 ``audit_fields`` 集合中大小写不敏感精确匹配，命中即为审计字段，
    ``reason`` 形如 ``"审计字段 <字段名>"``。
    规则 ``enabled`` 为 ``False`` 时一律返回 ``is_audit=False``、``reason=""``。
    """
    cfg = rules if rules is not None else DEFAULT_FILTER_RULES
    enabled = bool(cfg.get("enabled", True))
    audit_fields = cfg.get("audit_fields") or []
    results: list[dict] = []
    for name in fields:
        if not enabled:
            results.append({"name": str(name), "is_audit": False, "reason": ""})
            continue
        is_audit, reason = _match_audit_field(name, audit_fields)
        results.append({"name": str(name), "is_audit": is_audit, "reason": reason})
    return results


def is_system_table(name: str, rules: dict | None = None) -> bool:
    """判断表名是否为系统表（大小写不敏感）。

    等价于 ``classify_tables([name], rules)[0]["is_system"]``，保持原签名与既有行为。
    命中任一条件即为系统表：
    - 以任一 prefix 开头；
    - 包含任一 keyword；
    - 等于任一 exact；
    - ``regex`` 非空且 ``re.search`` 命中。

    规则 ``enabled`` 为 ``False`` 时一律返回 ``False``。
    """
    return bool(classify_tables([name], rules)[0]["is_system"])


def is_audit_field(name: str, rules: dict | None = None) -> bool:
    """判断字段名是否为审计字段（大小写不敏感精确匹配）。

    等价于 ``classify_fields([name], rules)[0]["is_audit"]``，保持原签名与既有行为。
    ``audit_fields`` 为字段名集合；命中任一即返回 ``True``。
    规则 ``enabled`` 为 ``False`` 时一律返回 ``False``。
    """
    return bool(classify_fields([name], rules)[0]["is_audit"])
