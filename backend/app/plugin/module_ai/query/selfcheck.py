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
