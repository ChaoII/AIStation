"""轻量知识图谱：从数据资产元数据（表/字段/关联/业务域/指标/术语）构建。

主流做法参考 RubikSQL 的图索引：节点 + 关系边（表-字段、字段↔字段关联、
指标-表、术语-指标、表-业务域），用 few-hop 遍历做 schema linking，
能补上「纯向量/关键词检索漏掉的联表路径与同域表」。

外部通过 `kg_explore(question)` 获取文本上下文，`kg_tables(question)` 取表集合。
"""
from __future__ import annotations

import re

_kg_cache: KgGraph | None = None


class KgGraph:
    """进程级知识图谱（节点+边），惰性构建。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}          # id -> {type,label,extra}
        self.edges: list[tuple[str, str, str]] = []  # (src, dst, rel)
        self._adj: dict[str, list[tuple[str, str]]] = {}  # node -> [(rel, dst)]

    def add_node(self, nid: str, ntype: str, label: str, extra: dict | None = None) -> None:
        self.nodes.setdefault(nid, {"type": ntype, "label": label, "extra": extra or {}})

    def add_edge(self, src: str, dst: str, rel: str) -> None:
        if src in self.nodes and dst in self.nodes:
            self.edges.append((src, dst, rel))
            self._adj.setdefault(src, []).append((rel, dst))

    def neighbors(self, nid: str, hops: int) -> set[str]:
        seen = {nid}
        frontier = {nid}
        for _ in range(hops):
            nxt: set[str] = set()
            for cur in frontier:
                for _rel, dst in self._adj.get(cur, []):
                    if dst not in seen:
                        nxt.add(dst)
            seen |= nxt
            frontier = nxt
        return seen - {nid}


async def _build() -> KgGraph:
    """进程级构建（由 service 缓存好的 schema/tmeta/metrics/terms 填充）。"""
    from .service import SYSTEM_DS, AiQueryService

    kg = KgGraph()
    schema = await AiQueryService._system_schema()
    tmeta = await AiQueryService._asset_tmeta()
    metrics = await AiQueryService.list_metrics(SYSTEM_DS)
    terms = await AiQueryService.list_terms(SYSTEM_DS)
    # 表 + 表级元数据
    for t in schema:
        meta = tmeta.get(t) or {}
        kg.add_node(f"table:{t}", "table", meta.get("alias") or t,
                    {"domain": meta.get("domain"), "desc": meta.get("description"),
                     "scen": meta.get("business_scenarios")})
        if meta.get("domain"):
            kg.add_node(f"domain:{meta['domain']}", "domain", meta["domain"])
            kg.add_edge(f"table:{t}", f"domain:{meta['domain']}", "in_domain")
    # 字段 + 关联边
    rel_re = re.compile(r"【关联:([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)】")
    for t, cols in schema.items():
        for lab in cols:
            col = lab.split("(")[0]
            kg.add_node(f"field:{t}.{col}", "field", col, {"table": t})
            kg.add_edge(f"table:{t}", f"field:{t}.{col}", "has_field")
            m = rel_re.search(lab)
            if m:
                rt, rf = m.group(1), m.group(2)
                if f"field:{rt}.{rf}" in kg.nodes:
                    kg.add_edge(f"field:{t}.{col}", f"field:{rt}.{rf}", "related_to")
    # 指标 -> 表
    for m in metrics:
        kg.add_node(f"metric:{m['key']}", "metric", m.get("name") or m["key"],
                    {"desc": m.get("description")})
        for tb in _tables_in_sql(m.get("sql_template", "")):
            if f"table:{tb}" in kg.nodes:
                kg.add_edge(f"metric:{m['key']}", f"table:{tb}", "uses_table")
    # 术语 -> 指标
    for t in terms:
        tkey = t.get("metric_key")
        kg.add_node(f"term:{t['term']}", "term", t["term"])
        if tkey and f"metric:{tkey}" in kg.nodes:
            kg.add_edge(f"term:{t['term']}", f"metric:{tkey}", "maps_to")
    # 同域表之间加 weak 边，便于同域召回
    doms: dict[str, list[str]] = {}
    for nid, nd in kg.nodes.items():
        if nd["type"] == "table" and nd["extra"].get("domain"):
            doms.setdefault(nd["extra"]["domain"], []).append(nid)
    for _d, tabs in doms.items():
        for a in tabs:
            for b in tabs:
                if a != b:
                    kg.add_edge(a, b, "same_domain")
    return kg


def _tables_in_sql(sql: str) -> set[str]:
    return set(re.findall(r"from\s+([a-zA-Z_][a-zA-Z0-9_]*)", (sql or "").lower()))


async def _ensure() -> KgGraph:
    global _kg_cache
    if _kg_cache is None:
        _kg_cache = await _build()
    return _kg_cache


async def _stats() -> dict:
    kg = await _ensure()
    return {"nodes": len(kg.nodes), "edges": len(kg.edges),
            "tables": sum(1 for n in kg.nodes.values() if n["type"] == "table"),
            "fields": sum(1 for n in kg.nodes.values() if n["type"] == "field")}


async def _reset() -> dict:
    global _kg_cache
    _kg_cache = None
    kg = await _ensure()
    return {"nodes": len(kg.nodes), "edges": len(kg.edges),
            "tables": sum(1 for n in kg.nodes.values() if n["type"] == "table")}


def _score_nodes(q: str, kg: KgGraph) -> list[str]:
    """按关键词/实体命中给节点打分，取种子。"""
    ql = (q or "").lower()
    seeds: dict[str, int] = {}
    for nid, nd in kg.nodes.items():
        label = (nd["label"] or "").lower()
        extra = nd["extra"] or {}
        s = 0
        if label and label in ql:
            s += 8
        if nd["type"] == "table" and extra.get("alias") and extra["alias"].lower() in ql:
            s += 6
        if nd["type"] in ("term", "metric"):
            for kw in (nd["label"], extra.get("desc") or ""):
                if kw and kw.lower() in ql:
                    s += 6
        if nd["type"] == "table" and extra.get("desc") and extra["desc"] in ql:
            s += 3
        if nd["type"] == "table" and extra.get("scen") and any(w in ql for w in re.split(r"[，,、；;]", extra["scen"].lower()) if w):
            s += 2
        if s:
            seeds[nid] = s
    seeds = {n: s for n, s in seeds.items() if s >= 3}
    return [n for n, _ in sorted(seeds.items(), key=lambda kv: -kv[1])][:8]


def kg_tables(question: str) -> set[str]:
    """图遍历召回相关表（含 1-2 跳关联/同域表）。"""
    kg = _kg_cache
    if kg is None:
        return set()
    seeds = _score_nodes(question, kg)
    tables: set[str] = set()
    seen: set[str] = set()
    for nid in seeds:
        if nid in seen:
            continue
        seen.add(nid)
        rg = kg.neighbors(nid, hops=2)
        for mid in rg | {nid}:
            nd = kg.nodes.get(mid)
            if nd and nd["type"] == "table":
                tables.add(mid.split(":", 1)[1])
    return tables


def kg_explore(question: str) -> str:
    """返回知识图谱上下文字符串：相关表/字段/关联/同域/术语。"""
    kg = _kg_cache
    if kg is None:
        return "【知识图谱】尚未构建。"
    seeds = _score_nodes(question, kg)
    if not seeds:
        return "【知识图谱】未命中相关节点。"
    lines = ["【知识图谱】"]
    tabs: dict[str, set[str]] = {}
    for nid in seeds:
        nd = kg.nodes.get(nid)
        if not nd:
            continue
        if nd["type"] == "table":
            tabs.setdefault(nid.split(":", 1)[1], set())
        elif nd["type"] == "field":
            tabs.setdefault(nd["extra"]["table"], set()).add(nd["label"])
        elif nd["type"] in ("term", "metric"):
            lines.append(f"- {nd['type']}:{nd['label']} -> {nd['extra'].get('desc') or ''}")
    # 遍历关联，收集联表路径
    seen: set[str] = set()
    for nid in seeds:
        if nid in seen:
            continue
        seen.add(nid)
        rg = kg.neighbors(nid, hops=2)
        for mid in rg:
            nd = kg.nodes.get(mid)
            if not nd:
                continue
            if nd["type"] == "table":
                tabs.setdefault(mid.split(":", 1)[1], set())
            elif nd["type"] == "field":
                tabs.setdefault(nd["extra"]["table"], set()).add(nd["label"])
    for t, cols in tabs.items():
        meta = kg.nodes.get(f"table:{t}", {}).get("extra", {}) or {}
        extra = f"【{meta.get('domain')}】" if meta.get("domain") else ""
        cols_txt = (", ".join(sorted(cols)) if cols else "") or "（含全部字段，请用 table_metadata 查看）"
        lines.append(f"表 {t}{extra}: {cols_txt}")
    # 输出关联路径
    rels = []
    for src, dst, rel in kg.edges:
        if rel == "related_to":
            st = kg.nodes.get(src, {}).get("extra", {}).get("table")
            dt = kg.nodes.get(dst, {}).get("extra", {}).get("table")
            if st and dt and st != dt:
                rels.append(f"{st}.{src.split('.')[1]} → {dt}.{dst.split('.')[1]}")
    if rels:
        lines.append("联表路径：" + "；".join(rels[:10]))
    return "\n".join(lines)
