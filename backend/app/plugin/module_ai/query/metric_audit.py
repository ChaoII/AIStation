"""指标体检（治理用）：找出自动生成的脏指标、绑定错位、以及与业务问法抢答的指标。

供 `GET /ai/query/metrics/audit` 与 `scripts/audit_metrics.py` 共用；**只读**，
停用/改名由界面上的操作按钮走指标接口完成。
"""
from __future__ import annotations

import re

FIELD_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]{3,}")
AGG_SUFFIX_RE = re.compile(r"(合计|总和|数量|计数|平均值|最大值|最小值|记录数)$")
TABLE_WORD_RE = re.compile(r"(明细表|主表|表)")


def _reasons(m: dict) -> list[str]:
    out: list[str] = []
    name = str(m.get("name") or "")
    if FIELD_CODE_RE.search(name):
        out.append("名字里带字段码")
    if TABLE_WORD_RE.search(name) and AGG_SUFFIX_RE.search(name):
        out.append("「表名+聚合」拼装")
    if len(name) > 16:
        out.append("名字过长")
    tpl = str(m.get("sql_template") or "")
    if not m.get("object_code") and "FROM" not in tpl.upper():
        out.append("绑定型但没对象（SQL 是 SELECT 1）")
    return out


async def audit_metrics(datasource: str = "ds:6", top: int = 100) -> dict:
    from . import metric_rules as M
    from .eval_set import list_cases
    from .service import AiQueryService as S

    metrics = [m for m in await S.list_metrics(datasource) if m.get("enabled")]
    cases = []
    for ds in ("holdout-v1", "holdout-v2"):
        try:
            cases += await list_cases(datasource=datasource, dataset=ds, enabled=True)
        except Exception:  # noqa: BLE001
            pass
    aliases = await S._metric_alias_map()
    hits: dict[str, list[str]] = {}
    for c in cases:
        q = c["question"]
        got = M.match_metric(q, metrics, [], [], {}, table_alias=aliases)
        if got:
            hits.setdefault(got["key"], []).append(q)

    rows = []
    for m in metrics:
        rs = _reasons(m)
        if not rs:
            continue
        rows.append({
            "key": m["key"], "name": m.get("name") or "", "agg": m.get("agg") or "",
            "table": M.metric_main_table(m) or (m.get("object_code") or ""),
            "reasons": rs, "questions": hits.get(m["key"], []),
            "action": "disable" if hits.get(m["key"]) else "rename",
        })
    rows.sort(key=lambda r: (-len(r["questions"]), -len(r["reasons"]), r["key"]))
    return {
        "total_metrics": len(metrics),
        "suspect": len(rows),
        "hijacking": sum(1 for r in rows if r["questions"]),
        "items": rows[: max(1, int(top))],
    }


__all__ = ["audit_metrics"]
