"""指标审计（只读）：找出自动生成的脏指标、绑定错位、与业务问法抢答的指标。

输出：`docs/metric-cleanup-<date>.md`（建议改名/停用清单），不改任何数据。

用法：
    uv run python scripts/audit_metrics.py
    uv run python scripts/audit_metrics.py --datasource ds:6 --top 40
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

#: 自动生成痕迹：大写字段码（STOQTY / QCAL_MIN / MIXCOALS）、「表」+聚合后缀、超长名字
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


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default="ds:6")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    from main import create_app

    create_app()

    from app.plugin.module_ai.query import metric_rules as M
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import AiQueryService as S

    metrics = [m for m in await S.list_metrics(args.datasource) if m.get("enabled")]
    # 影响面：留出集里被它抢答的题目
    cases = []
    for ds in ("holdout-v1", "holdout-v2"):
        try:
            cases += await list_cases(datasource=args.datasource, dataset=ds, enabled=True)
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
            "obj": m.get("object_code") or "",
            "table": M.metric_main_table(m) or (m.get("object_code") or ""),
            "reasons": rs, "questions": hits.get(m["key"], []),
        })
    rows.sort(key=lambda r: (-len(r["questions"]), -len(r["reasons"]), r["key"]))

    today = date.today().isoformat()
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(repo_root, "docs", f"metric-cleanup-{today}.md")
    lines = [
        f"# 指标清洗清单（{today}，只读审计）", "",
        f"数据源 `{args.datasource}`，启用指标 {len(metrics)} 个；有自动生成痕迹 {len(rows)} 个。",
        "标记为「建议」的动作需要人工确认后再执行（不改数据也能先看影响面）。", "",
        "| # | 指标名 | key | 绑定表/对象 | 问题 | 抢答的留出题 | 建议 |",
        "|---|--------|-----|-------------|------|--------------|------|",
    ]
    for i, r in enumerate(rows[: args.top], 1):
        action = "**停用**" if r["questions"] else "改名"
        qs = "；".join(q[:18] for q in r["questions"][:2]) or "—"
        lines.append(
            f"| {i} | {r['name']} | `{r['key']}` | {r['table'] or '—'} | "
            f"{'、'.join(r['reasons'])} | {qs} | {action} |")
    lines += ["", "## 汇总", ""]
    with_q = [r for r in rows if r["questions"]]
    lines.append(f"- 有留出题被抢答的指标：**{len(with_q)} 个**（优先停用/改名）")
    lines.append(f"- 仅命名不规范的指标：{len(rows) - len(with_q)} 个（可批量改名）")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[ok] 审计完成：{len(rows)} 个可疑指标（其中 {len(with_q)} 个抢答）→ {out}")
    for r in rows[:12]:
        print("  -", r["name"][:34], "|", "、".join(r["reasons"]),
              "| 抢答:", len(r["questions"]))


if __name__ == "__main__":
    asyncio.run(main())
