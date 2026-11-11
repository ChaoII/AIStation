"""问数评测：跨运行对比（纯逻辑，便于单测）。

用途：同一题库在「不同模型 / 不同提示词与开关」下各跑一轮，回答
「哪些题被修好了、哪些被跑坏了、耗时变了多少」——单看两次准确率无法归因。

口径：
- 以 `testcase_id` 对齐两轮结果；
- `fixed`  = 基线错、对比对；`regressed` = 基线下、对比错；`same` = 结果相同；
- `only_base` / `only_target` = 只在某一轮出现的题（题集中途增删）。
"""
from __future__ import annotations


def _idx(rows: list[dict]) -> dict[int, dict]:
    return {int(r.get("testcase_id") or 0): r for r in rows or []}


def compare_runs(base_rows: list[dict], target_rows: list[dict],
                 base_meta: dict | None = None, target_meta: dict | None = None,
                 limit: int = 500) -> dict:
    """按题对齐两轮结果，返回汇总 + 逐题差异。"""
    b, t = _idx(base_rows), _idx(target_rows)
    keys = sorted(set(b) | set(t))
    fixed = regressed = same = only_base = only_target = 0
    items: list[dict] = []
    for cid in keys:
        rb, rt = b.get(cid), t.get(cid)
        if rb is None:
            only_target += 1
            status = "only_target"
        elif rt is None:
            only_base += 1
            status = "only_base"
        elif not rb.get("gold_match") and rt.get("gold_match"):
            fixed += 1
            status = "fixed"
        elif rb.get("gold_match") and not rt.get("gold_match"):
            regressed += 1
            status = "regressed"
        else:
            same += 1
            status = "same"
        cur = rt or rb or {}
        prev = rb or rt or {}
        items.append({
            "testcase_id": cid,
            "question": cur.get("question") or prev.get("question") or "",
            "status": status,
            "base_ok": None if rb is None else bool(rb.get("gold_match")),
            "target_ok": None if rt is None else bool(rt.get("gold_match")),
            "base_error": None if rb is None else bool(rb.get("is_error")),
            "target_error": None if rt is None else bool(rt.get("is_error")),
            "base_path": (rb or {}).get("path") or "",
            "target_path": (rt or {}).get("path") or "",
            "base_ms": int((rb or {}).get("took_ms") or 0),
            "target_ms": int((rt or {}).get("took_ms") or 0),
            "delta_ms": int((rt or {}).get("took_ms") or 0) - int((rb or {}).get("took_ms") or 0),
            "base_sql": (rb or {}).get("sql") or "",
            "target_sql": (rt or {}).get("sql") or "",
        })
    # 变化优先展示：回退 → 修复 → 单边 → 不变
    order = {"regressed": 0, "fixed": 1, "only_base": 2, "only_target": 3, "same": 4}
    items.sort(key=lambda x: (order.get(x["status"], 9), x["testcase_id"]))
    meta_b = (base_meta or {}).get("fingerprint") or {}
    meta_t = (target_meta or {}).get("fingerprint") or {}
    return {
        "total": len(keys),
        "fixed": fixed,
        "regressed": regressed,
        "same": same,
        "only_base": only_base,
        "only_target": only_target,
        "net": fixed - regressed,
        "base": {
            "run_id": (base_meta or {}).get("run_id", ""),
            "model": meta_b.get("model", ""),
            "config": meta_b.get("config") or {},
            "rules": _rules_brief(meta_b),
            "data_accuracy": _acc(base_rows),
        },
        "target": {
            "run_id": (target_meta or {}).get("run_id", ""),
            "model": meta_t.get("model", ""),
            "config": meta_t.get("config") or {},
            "rules": _rules_brief(meta_t),
            "data_accuracy": _acc(target_rows),
        },
        "model_changed": _model_changed(meta_b, meta_t),
        # 生成规则差异（本轮新增）：A/B 时最需要看的就是"两轮规则哪里不同"
        "rules_changed": _rules_changed(meta_b, meta_t),
        "items": items[:limit],
        "truncated": len(items) > limit,
    }


def _rules_brief(meta: dict) -> dict:
    """从指纹里取规则摘要（兼容没有该字段的老运行）。"""
    rules = (meta or {}).get("rules") or {}
    return {
        "hash": rules.get("hash", ""),
        "count": rules.get("count", 0),
        "enabled_count": rules.get("enabled_count", 0),
        "disabled_override": list(rules.get("disabled_override") or []),
    }


def _rules_changed(a: dict, b: dict) -> bool:
    """两轮规则是否不同：文案/启用状态（hash）或本轮禁用清单不同即算变更。

    老运行没有 rules 指纹 → 返回 False（"未知"不能当成"改过"，与 ``_model_changed`` 同口径）。
    """
    ra, rb = _rules_brief(a), _rules_brief(b)
    if not ra["hash"] or not rb["hash"]:
        return False
    if ra["hash"] != rb["hash"]:
        return True
    return sorted(ra["disabled_override"]) != sorted(rb["disabled_override"])


def _model_changed(a: dict, b: dict) -> bool:
    """只有两轮**都记录了**模型且不同才算换模型。

    老运行没有 fingerprint（本轮才加），直接比较会把「未知」误报成「已变更」。
    """
    ma, mb = (a or {}).get("model") or "", (b or {}).get("model") or ""
    return bool(ma and mb and ma != mb)


def _acc(rows: list[dict]) -> float:
    rows = [r for r in (rows or []) if not r.get("degenerate")]
    if not rows:
        return 0.0
    return round(sum(1 for r in rows if r.get("gold_match")) / len(rows), 4)
