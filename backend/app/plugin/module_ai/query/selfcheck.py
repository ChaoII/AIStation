"""结果自校验：生成后**用结果反推**是否可疑，可疑就带错因重试一次。

设计原则（避免误报把正确结果判成错）：
- **只做提示 + 一次重试**，绝不阻断返回；
- 每个检查都**有明确的列名前提**（占比列 / 累计列 / 排名列），名字不匹配就不检查；
- 阈值取得宽松（占比 95~105 才算合理，其余不报）。
"""
from __future__ import annotations

import re

_RATIO_RE = re.compile(r"(占比|比例|百分比|rate|ratio|pct|percent)", re.IGNORECASE)
_CUM_RE = re.compile(r"(累计|累积|cum|running|total)", re.IGNORECASE)
_RANK_RE = re.compile(r"(排名|序号|名次|rank|row_num|rn)", re.IGNORECASE)
_GROUP_HINT_RE = re.compile(r"(每个|各|按.{1,8}(分组|统计|汇总)|分别)")


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _col_index(columns: list, pattern: re.Pattern) -> int | None:
    for i, c in enumerate(columns or []):
        if pattern.search(str(c)):
            return i
    return None


def check_ratio(columns: list, rows: list) -> list[dict]:
    """占比类列：合计应 ≈100（宽松 95~105）。"""
    i = _col_index(columns, _RATIO_RE)
    if i is None or not rows:
        return []
    vals = [_to_float(r[i]) for r in rows if i < len(r)]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return []
    total = sum(vals)
    if total < 95 or total > 105:
        return [{"kind": "ratio", "msg": f"占比列合计为 {total:.1f}%，明显偏离 100%"}]
    return []


def check_cumulative(columns: list, rows: list) -> list[dict]:
    """累计类列：应**单调不减**（按返回顺序）。"""
    i = _col_index(columns, _CUM_RE)
    if i is None or len(rows) < 3:
        return []
    vals = [_to_float(r[i]) for r in rows if i < len(r)]
    vals = [v for v in vals if v is not None]
    if len(vals) < 3:
        return []
    if any(vals[k + 1] < vals[k] - 1e-9 for k in range(len(vals) - 1)):
        return [{"kind": "cumulative", "msg": "累计列出现下降，可能窗口排序写错"}]
    return []


def check_rank(columns: list, rows: list) -> list[dict]:
    """排名类列：最大值不应**大于行数**（明显不合逻辑时才算可疑）。"""
    i = _col_index(columns, _RANK_RE)
    if i is None or not rows:
        return []
    vals = [_to_float(r[i]) for r in rows if i < len(r)]
    vals = [v for v in vals if v is not None]
    if not vals:
        return []
    if max(vals) > len(rows):
        return [{"kind": "rank", "msg": f"排名最大值为 {max(vals):.0f}，但只有 {len(rows)} 行"}]
    return []


def check_row_magnitude(question: str, rows: list) -> list[dict]:
    """「每个/各…」类问题只返回 1 行 → 很可能没分组。"""
    if not rows or len(rows) != 1:
        return []
    if _GROUP_HINT_RE.search(question or ""):
        return [{"kind": "rows", "msg": "问题要求分组/逐个统计，但只返回 1 行，可能漏了 GROUP BY"}]
    return []


def run_selfcheck(question: str, columns: list, rows: list) -> list[dict]:
    """返回可疑项列表（空 = 通过）。**只作提示**，不阻断。"""
    issues: list[dict] = []
    for fn in (check_ratio, check_cumulative, check_rank):
        try:
            issues.extend(fn(columns, rows))
        except Exception:  # noqa: BLE001
            continue
    try:
        issues.extend(check_row_magnitude(question, rows))
    except Exception:  # noqa: BLE001
        pass
    return issues


def format_issue(issues: list[dict]) -> str:
    """把可疑项拼成给模型看的**具体错因**（用于重试）。"""
    return "；".join(str(x.get("msg") or "") for x in (issues or []) if x.get("msg"))


# ---------------------------------------------------------------------------
# SQL 意图校验：拿**问句的措辞**去对**生成的 SQL**，而不是等结果回来才反推
#
# 为什么要有这一层：题库对比暴露的差异几乎全是"口径"而不是"能力"——
#   问「按名称分组」，SQL 却 GROUP BY 了 ID；
#   问「不为空」，SQL 没有 IS NOT NULL；
#   问「最近一个月」，SQL 里没有时间条件；
#   问「多少家不同」，SQL 用了 COUNT(*) 而不是 COUNT(DISTINCT)。
# 结果层面看不出来（数字都合理），只能靠"问句说要什么 / SQL 做了什么"来对。
# 全部是**高置信度**规则：只在措辞与 SQL 明确冲突时才报，宁可漏报不误报。
# ---------------------------------------------------------------------------
_ASK_BY_NAME_RE = re.compile(r"(按|每个|各)\s*[\u4e00-\u9fff]{0,6}(名称|名字)")
_ASK_NOT_NULL_RE = re.compile(r"(不为空|非空|有效|有值)")
_ASK_DISTINCT_RE = re.compile(r"多少(家|个|种|条|位)?不同|去重|不同.{0,4}数量")
_ASK_TIME_RE = re.compile(
    r"(最近|近\s*\d|过去|本(月|周|年)|这个月|今年|去年|上(月|周|年)"
    r"|\d{4}\s*年|\d+\s*(天|日|周|个?月))")
_SQL_DATE_RE = re.compile(
    r"(>=|<=|between|interval|current_date|date\(|to_char\(|date_trunc\(|\bnow\s*\()",
    re.IGNORECASE)
_GROUP_BY_ID_RE = re.compile(
    r"GROUP\s+BY\s+[^;]*?\"?([A-Za-z_][A-Za-z0-9_]*)\"?", re.IGNORECASE)


def check_sql_intent(question: str, sql: str) -> list[dict]:
    """问句措辞 vs SQL 的**口径冲突**（高置信度，只提示不阻断）。"""
    q = question or ""
    text = sql or ""
    up = text.upper()
    issues: list[dict] = []

    if _ASK_BY_NAME_RE.search(q):
        m = _GROUP_BY_ID_RE.search(text)
        grouped = re.findall(r"GROUP\s+BY\s+([^;]+?)(?:ORDER|LIMIT|$)", text, re.IGNORECASE)
        cols = " ".join(grouped).upper() if grouped else ""
        if re.search(r"\b\w*(ID|CODE)\b", cols) and not re.search(r"NAME", cols):
            issues.append({"kind": "group_key",
                           "msg": "问的是按名称分组，SQL 是按 ID/编码分组，结果可能对不上",
                           "detail": (m.group(1) if m else cols.strip())[:60]})

    if _ASK_NOT_NULL_RE.search(q) and "IS NOT NULL" not in up and "<> ''" not in text \
            and "!= ''" not in text:
        issues.append({"kind": "null_semantics",
                       "msg": "问句要求非空，SQL 没有排除空值",
                       "detail": ""})

    if _ASK_DISTINCT_RE.search(q) and "DISTINCT" not in up and "GROUP BY" not in up:
        issues.append({"kind": "distinct",
                       "msg": "问的是不同/去重数量，SQL 用了普通计数",
                       "detail": ""})

    if _ASK_TIME_RE.search(q) and not _SQL_DATE_RE.search(text):
        issues.append({"kind": "time_filter",
                       "msg": "问句带了时间范围，SQL 里没有时间条件",
                       "detail": ""})

    return issues


def format_sql_intent(issues: list[dict]) -> str:
    return "；".join(i.get("msg", "") for i in issues or [])
