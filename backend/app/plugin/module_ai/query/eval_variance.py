"""评测**方差**：同一批题重复跑 N 次后，回答"这个差异是真的吗"。

为什么需要它（实测教训）：同一配置（代码路径完全相同）三次跑同一批 B 半 53 题，
`data_accuracy` 分别是 **75.47% / 83.02% / 84.91%** —— 差 10 分。于是：
- 单次 A/B 的"−7.55 分"完全落在噪声里，**不能归因给功能**；
- 必须看**逐题翻转**（配对）与**跨次方差**，而不是聚合分的差值。

对标 Palantir AIP Evals 的 "examine the variance across executions"。

纯函数（不碰 DB / 不调模型）→ 可用 `PYTEST_NO_APP=1` 快速测。
"""
from __future__ import annotations

from math import comb
from statistics import mean, pstdev


def _key(row: dict) -> str:
    """逐题身份：优先 case_id，退化用 question。"""
    return str(row.get("case_id") or row.get("question") or "")


def per_question(runs: list[list[dict]]) -> dict[str, dict]:
    """逐题跨次通过率：``{题: {runs, passes, rate, degenerate}}``。"""
    out: dict[str, dict] = {}
    for rows in runs:
        for r in rows or []:
            k = _key(r)
            if not k:
                continue
            d = out.setdefault(k, {"question": r.get("question") or k, "runs": 0,
                                   "passes": 0, "degenerate": bool(r.get("degenerate"))})
            if r.get("degenerate"):
                d["degenerate"] = True
                continue
            d["runs"] += 1
            if r.get("gold_match"):
                d["passes"] += 1
    for d in out.values():
        d["rate"] = (d["passes"] / d["runs"]) if d["runs"] else 0.0
    return out


def _accuracy(rows: list[dict]) -> float:
    """单次运行的 data_accuracy（排除退化题），与 eval_metrics.summarize 同口径。"""
    rs = [r for r in rows or [] if not r.get("degenerate")]
    if not rs:
        return 0.0
    return 100.0 * sum(1 for r in rs if r.get("gold_match")) / len(rs)


def mcnemar_exact(a_pass: list[bool], b_pass: list[bool]) -> dict:
    """配对检验（McNemar 精确法，双侧）。

    只看**翻转**的题：``b01``=A 错 B 对，``b10``=A 对 B 错。
    p 大 → 差异可由噪声解释；p 小 → 差异显著。
    """
    b01 = sum(1 for x, y in zip(a_pass, b_pass) if (not x) and y)
    b10 = sum(1 for x, y in zip(a_pass, b_pass) if x and (not y))
    n = b01 + b10
    if n == 0:
        return {"b01": 0, "b10": 0, "n": 0, "p": 1.0, "significant": False}
    k = min(b01, b10)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    p = min(1.0, 2 * tail)
    return {"b01": b01, "b10": b10, "n": n, "p": round(p, 4), "significant": p < 0.05}


def variance_report(runs: list[list[dict]]) -> dict:
    """跨次方差报告：聚合分的离散度 + 逐题不稳定清单 + 两两配对检验。"""
    accs = [_accuracy(rows) for rows in runs or []]
    pq = per_question(runs)
    unstable = sorted(
        (d for d in pq.values() if not d["degenerate"] and 0 < d["rate"] < 1),
        key=lambda d: d["rate"],
    )
    always_fail = [d for d in pq.values() if not d["degenerate"] and d["rate"] == 0]
    always_pass = [d for d in pq.values() if not d["degenerate"] and d["rate"] == 1]

    # 逐题通过向量（供配对检验）
    keys = [k for k, d in pq.items() if not d["degenerate"]]
    vecs: list[list[bool]] = []
    for rows in runs or []:
        m = {_key(r): bool(r.get("gold_match")) for r in (rows or []) if not r.get("degenerate")}
        vecs.append([m.get(k, False) for k in keys])

    pairs = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            res = mcnemar_exact(vecs[i], vecs[j])
            res["a"] = i + 1
            res["b"] = j + 1
            pairs.append(res)

    n = len(accs)
    return {
        "n_runs": n,
        "per_run_accuracy": [round(a, 2) for a in accs],
        "mean": round(mean(accs), 2) if n else 0.0,
        "std": round(pstdev(accs), 2) if n > 1 else 0.0,
        "min": round(min(accs), 2) if n else 0.0,
        "max": round(max(accs), 2) if n else 0.0,
        "spread": round((max(accs) - min(accs)), 2) if n else 0.0,
        "n_questions": len(keys),
        "always_pass": len(always_pass),
        "always_fail": len(always_fail),
        "unstable": [
            {"question": d["question"][:48], "rate": round(d["rate"], 2), "runs": d["runs"]}
            for d in unstable
        ],
        "pairs": pairs,
        # 结论辅助：噪声带（用跨次极差当"同一配置的波动幅度"）
        "noise_band": round((max(accs) - min(accs)), 2) if n > 1 else None,
    }
