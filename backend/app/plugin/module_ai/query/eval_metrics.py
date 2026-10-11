"""问数评测：**纯函数**指标（金标抽表 / Recall@k / 总览 / 分维度聚合）。

与 IO 解耦，便于单测（可 ``PYTEST_NO_APP=1``）。
口径见 spec §六。
"""
from __future__ import annotations

import re

_TABLE_RE = re.compile(r'\b(?:from|join)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', re.IGNORECASE)


def gold_tables(sql: str, schema: dict | None = None) -> set[str]:
    """从金标 SQL 抽出「应使用的表」，并与 schema 求交（schema 为空则不过滤）。"""
    found = {m.group(1) for m in _TABLE_RE.finditer(sql or "")}
    if schema:
        return {t for t in found if t in schema}
    return found


def recall_at_k(expected: set[str], retrieved: list[str], k: int = 8) -> float:
    """召回命中率：``|expected ∩ retrieved[:k]| / |expected|``；expected 为空记 1.0。"""
    if not expected:
        return 1.0
    top = {str(t) for t in (retrieved or [])[:k]}
    return len(expected & top) / len(expected)


def _pct(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def is_degenerate_result(rows: list | None) -> bool:
    """结果是否**退化**（答对答错都没有信息量）。

    退化 = 空结果 / 全 NULL / 单值 0（或空串）。

    实测：ds:4 有 92% 的题建在空表上，``COUNT(*)`` 得 0、``AVG()`` 得 NULL，
    **任何 SQL 都能"答对"** → 必须把它们排除在精度分母之外，否则数字虚高。
    """
    rows = rows or []
    if not rows:
        return True
    # 容错：行可能是标量（如 [1]）而非数组（[[1]]），别在形状上崩
    flat: list = []
    for r in rows:
        if isinstance(r, (list, tuple)):
            flat.extend(r)
        else:
            flat.append(r)
    if not flat:
        return True
    if all(v is None or (isinstance(v, str) and not v.strip()) for v in flat):
        return True
    if len(flat) == 1:
        v = flat[0]
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0:
            return True
    return False


def _pctile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * q))
    return float(ordered[idx])


def summarize(results: list[dict], k: int = 8) -> dict:
    """总览指标（**排除退化题**）。

    - ``data_accuracy``：``gold_match`` 占比（分母只算非退化题）。
    - ``degenerate_n`` / ``all_total``：被排除的退化题数 / 总题数。
    - ``semantic_accuracy``：**带 expected_metric 的题**中 metric 命中的比例（分母只算这类题）。
    - ``fast_rate`` / ``error_rate``：path==fast / is_error 占比。
    - ``recall_at_k``：各题 ``recall`` 字段的平均（缺省按 0）。
    """
    rows_all = list(results or [])
    rows = [r for r in rows_all if not r.get("degenerate")]
    degenerate_n = len(rows_all) - len(rows)
    n = len(rows)
    if not n:
        return {"total": 0, "all_total": len(rows_all), "degenerate_n": degenerate_n,
                "data_accuracy": 0.0, "semantic_accuracy": 0.0,
                "fast_rate": 0.0, "recall_at_k": 0.0, "avg_ms": 0.0,
                "p50_ms": 0.0, "p95_ms": 0.0, "error_rate": 0.0}
    ms = [int(r.get("took_ms") or 0) for r in rows]
    with_metric = [r for r in rows if r.get("expected_metric")]
    sem_hit = sum(1 for r in with_metric if r.get("metric_key") == r.get("expected_metric"))
    recalls = [float(r.get("recall") or 0.0) for r in rows]
    return {
        "total": n,
        "all_total": len(rows_all),
        "degenerate_n": degenerate_n,
        "data_accuracy": _pct(sum(1 for r in rows if r.get("gold_match")), n),
        "semantic_accuracy": _pct(sem_hit, len(with_metric)),
        "fast_rate": _pct(sum(1 for r in rows if r.get("path") == "fast"), n),
        "recall_at_k": round(sum(recalls) / n, 4),
        "avg_ms": round(sum(ms) / n, 1),
        "p50_ms": _pctile(ms, 0.5),
        "p95_ms": _pctile(ms, 0.95),
        "error_rate": _pct(sum(1 for r in rows if r.get("is_error")), n),
        "k": k,
    }


def group_by(results: list[dict], field: str) -> dict[str, dict]:
    """按某维度分组：每组 ``{total, correct, accuracy}``（correct = gold_match）。

    **退化题不计入**（同 ``summarize``）。
    """
    out: dict[str, dict] = {}
    for r in results or []:
        if r.get("degenerate"):
            continue
        key = str(r.get(field) or "未分类")
        g = out.setdefault(key, {"total": 0, "correct": 0})
        g["total"] += 1
        g["correct"] += 1 if r.get("gold_match") else 0
    for g in out.values():
        g["accuracy"] = _pct(g["correct"], g["total"])
    return out
