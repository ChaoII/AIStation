"""问句语言规则（**词表可配**）：把路由/快路径里的「中文词证据」从代码搬到设置里。

原则（AGENTS.md）：语义/口径不写死在代码里。这里搬的是**词表**，不是算法：
- 能配的：计数诉求词、物理量词、条数问法、排序词、列举词、全量列举词、
  非计数前缀、组上聚合词、列举覆盖词、分组词；
- 仍留代码的：**结构**（如「前 N 名」的 N、`按.{0,8}(数量|统计)` 这类模式），
  以及聚合映射（avg/sum/max/min）——改这些属于改算法，不是改说法。

存储：`ai_query_settings.query_language_rules`（JSON，界面「语言规则」）。
读取：`set_from_settings(cfg)` 在每次问数入口设置一次（ContextVar，任务级隔离），
纯函数里用 `current()` 取，避免把参数一路透传、也避免全局污染。
"""
from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Any

#: 默认词表 = 改造前写死在代码里的那份（逐项一致，行为不变）。
DEFAULT_LANGUAGE_RULES: dict[str, Any] = {
    "switches": {
        "count_intent": True,
        "physical_qty": True,
        "rowcount": True,
        "order": True,
        "listing": True,
        "all_list": True,
    },
    "count_quantifiers": ["多少", "几"],
    "count_units": ["条", "份", "个", "张", "家", "次", "种", "名", "项", "台", "套", "样", "批"],
    "count_nouns": ["数量", "条数", "记录数", "计数", "总数"],
    "physical_qty_words": [
        "存煤", "库存", "总量", "合计", "总和", "吨数", "多少吨", "多少方", "大卡",
        "金额", "余额", "耗用", "发热量", "硫分", "灰分", "水分",
    ],
    "rowcount_ask_words": ["条数", "记录数", "笔数", "多少条", "多少笔"],
    "order_words": ["排序", "升序", "降序", "从大到小", "从小到大", "排名"],
    "non_count_prefixes": ["平均", "最大", "最小", "最高", "最低"],
    "listing_words": [
        "哪些", "列出", "列表", "清单", "明细", "罗列", "有哪些",
        "分别是什么", "各叫什么", "的名称", "的名字", "叫啥", "叫什么名字",
    ],
    "listing_verbs": ["列出", "列表", "清单", "罗列", "哪些", "分别", "名称", "叫啥", "叫什么"],
    "count_override_words": [
        "条数", "数量", "总数", "总条数", "多少个", "多少条", "多少份", "多少张",
        "多少人", "多少家", "合计", "总和", "总量",
    ],
    "all_list_words": [
        "每个", "各", "所有", "全部", "分别", "每类", "每种", "列出",
        "逐个", "清单", "都有哪些", "有哪些",
    ],
    "agg_over_groups_words": ["平均", "均值", "人均", "户均", "占比", "百分比", "比例",
                             "最多", "最少", "最高", "最低", "最大", "最小"],
    "group_words": ["每个", "各", "分别", "分组"],
    "group_nouns": ["数量", "统计", "平均", "总计"],
}


def _as_list(v: Any, fallback: list[str]) -> list[str]:
    if isinstance(v, list):
        out = [str(x).strip() for x in v if str(x).strip()]
        if out:
            return out
    return list(fallback)


def merge_rules(raw: Any) -> dict[str, Any]:
    """库里的 JSON 覆盖默认值（逐键；非法值回落默认，不要求用户重存）。"""
    cfg: dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        try:
            cfg = json.loads(raw)
        except Exception:  # noqa: BLE001
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    out: dict[str, Any] = {"switches": dict(DEFAULT_LANGUAGE_RULES["switches"])}
    sw = cfg.get("switches")
    if isinstance(sw, dict):
        for k, v in sw.items():
            if k in out["switches"] and isinstance(v, bool):
                out["switches"][k] = v
    for key, default in DEFAULT_LANGUAGE_RULES.items():
        if key == "switches":
            continue
        out[key] = _as_list(cfg.get(key), default)
    return out


def _alt(words: list[str]) -> str:
    return "|".join(re.escape(str(w)) for w in words if str(w).strip())


def _never() -> re.Pattern:
    return re.compile(r"(?!)")


def compile_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """由词表生成 **与历史写法等价** 的正则/词表（默认配置下行为一字不变）。"""
    sw = rules["switches"]
    quant = _alt(rules["count_quantifiers"])
    units = _alt(rules["count_units"])
    nouns = _alt(rules["count_nouns"])
    count_intent = (
        re.compile(rf"(?:{quant})\s*(?:{units})|(?:{nouns})")
        if sw.get("count_intent", True) else _never()
    )
    physical = (
        re.compile(rf"(?:{_alt(rules['physical_qty_words'])})")
        if sw.get("physical_qty", True) else _never()
    )
    rowcount = (
        re.compile(rf"(?:{_alt(rules['rowcount_ask_words'])})")
        if sw.get("rowcount", True) else _never()
    )
    order_body = _alt(rules["order_words"])
    order = (
        re.compile(rf"(?:{order_body}|按.{{0,6}}排|前\s*\d+\s*(?:名|条|个))")
        if sw.get("order", True) else _never()
    )
    listing = (
        re.compile(rf"(?:{_alt(rules['listing_words'])})")
        if sw.get("listing", True) else _never()
    )
    all_list = list(rules["all_list_words"]) if sw.get("all_list", True) else []
    group_words = _alt(rules["group_words"])
    group_nouns = _alt(rules["group_nouns"])
    grouping = re.compile(
        rf"(?:{group_words}|按[个条]|按.{{0,8}}(?:{group_nouns}))"
    )
    return {
        "count_intent": count_intent,
        "physical_qty": physical,
        "rowcount": rowcount,
        "order": order,
        "listing": listing,
        "all_list_words": all_list,
        "grouping": grouping,
        "non_count_prefixes": re.compile(
            rf"^(?:{_alt(rules['non_count_prefixes'])})"),
        "listing_verbs": re.compile(rf"(?:{_alt(rules['listing_verbs'])})"),
        "count_override": re.compile(rf"(?:{_alt(rules['count_override_words'])})"),
        "agg_over_groups": re.compile(rf"(?:{_alt(rules['agg_over_groups_words'])})"),
    }


_DEFAULT_COMPILED = compile_rules(DEFAULT_LANGUAGE_RULES)
_CTX: ContextVar[dict[str, Any] | None] = ContextVar("query_language_rules", default=None)


def set_rules(rules: dict[str, Any] | None) -> None:
    _CTX.set(compile_rules(rules) if rules else None)


def set_from_settings(cfg: dict | None) -> None:
    """问数入口调用：按 `query_language_rules` 设置当前任务的词表。"""
    raw = (cfg or {}).get("query_language_rules")
    try:
        set_rules(merge_rules(raw))
    except Exception:  # noqa: BLE001 - 配置坏了就用默认，绝不能拖垮问数
        set_rules(None)


def reset() -> None:
    _CTX.set(None)


def current() -> dict[str, Any]:
    return _CTX.get() or _DEFAULT_COMPILED


def effective(raw: Any) -> dict[str, Any]:
    """给界面：**生效**的词表（默认 + 覆盖）。"""
    return merge_rules(raw)


def probe(question: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """预览：这句话会被判成什么（界面「语言规则 → 试一句」用）。"""
    c = compile_rules(rules) if rules else current()
    q = question or ""
    return {
        "count_intent": bool(c["count_intent"].search(q)),
        "physical_qty": bool(c["physical_qty"].search(q)),
        "rowcount_ask": bool(c["rowcount"].search(q)),
        "order": bool(c["order"].search(q)),
        "listing": bool(c["listing"].search(q)),
        "all_list": any(w in q for w in c["all_list_words"]),
        "grouping": bool(c["grouping"].search(q)),
        "non_count_prefix": bool(c["non_count_prefixes"].match(q)),
        "listing_verb": bool(c["listing_verbs"].search(q)),
        "count_override": bool(c["count_override"].search(q)),
        "agg_over_groups": bool(c["agg_over_groups"].search(q)),
        "matched": {
            "count_intent": c["count_intent"].search(q).group(0) if c["count_intent"].search(q) else "",
            "physical_qty": c["physical_qty"].search(q).group(0) if c["physical_qty"].search(q) else "",
            "rowcount": c["rowcount"].search(q).group(0) if c["rowcount"].search(q) else "",
            "order": c["order"].search(q).group(0) if c["order"].search(q) else "",
            "listing": c["listing"].search(q).group(0) if c["listing"].search(q) else "",
        },
    }


__all__ = [
    "DEFAULT_LANGUAGE_RULES", "merge_rules", "compile_rules", "set_rules",
    "set_from_settings", "reset", "current", "effective", "probe",
]
