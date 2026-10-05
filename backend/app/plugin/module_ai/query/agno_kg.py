"""轻量知识图谱：从数据资产元数据（表/字段/关联/业务域/指标/术语）构建。

主流做法参考 RubikSQL 的图索引：节点 + 关系边（表-字段、字段↔字段关联、
指标-表、术语-指标、表-业务域），用 few-hop 遍历做 schema linking，
能补上「纯向量/关键词检索漏掉的联表路径与同域表」。

外部通过 `kg_explore(question)` 获取文本上下文，`kg_tables(question)` 取表集合。
"""
from __future__ import annotations

import re

from app.core.logger import log

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
    # 本体/概念 -> 指标/表/父概念
    try:
        for c in await AiQueryService.list_concepts():
            kg.add_node(f"concept:{c['name']}", "concept", c["name"],
                        {"desc": c.get("description"), "syn": c.get("synonyms")})
            if c.get("parent_name"):
                kg.add_node(f"concept:{c['parent_name']}", "concept", c["parent_name"])
                kg.add_edge(f"concept:{c['name']}", f"concept:{c['parent_name']}", "subconcept_of")
            if c.get("metric_key") and f"metric:{c['metric_key']}" in kg.nodes:
                kg.add_edge(f"concept:{c['name']}", f"metric:{c['metric_key']}", "defined_as")
            for tb in (c.get("tables") or []):
                if f"table:{tb}" in kg.nodes:
                    kg.add_edge(f"concept:{c['name']}", f"table:{tb}", "about")
    except Exception:  # noqa: BLE001
        pass
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


#: 节点 id 前缀 → 显示名模板
def _node_name(nid: str, nd: dict) -> str:
    t = nd["type"]
    label = nd["label"]
    if t == "table":
        return f"表:{label}"
    if t == "field":
        return f"字段:{nd['extra'].get('table', '')}.{label}"
    if t == "metric":
        return f"指标:{label}"
    if t == "term":
        return f"术语:{label}"
    if t == "domain":
        return f"域:{label}"
    if t == "concept":
        return f"概念:{label}"
    return label


def _canvas_nodes_edges(kg: KgGraph) -> dict:
    """把 schema 图谱转成 GraphCanvas 可渲染的 nodes/edges。"""
    nodes = []
    for nid, nd in kg.nodes.items():
        nodes.append({"name": _node_name(nid, nd), "etype": nd["type"], "weight": 1})
    edges = []
    for src, dst, rel in kg.edges:
        if src in kg.nodes and dst in kg.nodes:
            edges.append({"source": _node_name(src, kg.nodes[src]),
                          "target": _node_name(dst, kg.nodes[dst]),
                          "rtype": rel, "weight": 1})
    return {"nodes": nodes, "edges": edges}


async def unified_graph(kb_id: int | None = None, schema_only: bool = False,
                        knowledge_only: bool = False) -> dict:
    """统一图谱：合并「数据 schema 图谱」与「知识库图谱(可选)」+ 自定义关系/布局。"""
    kg = await _ensure()
    merged = {"nodes": [], "edges": []}
    if not knowledge_only:
        part = _canvas_nodes_edges(kg)
        merged["nodes"] += part["nodes"]
        merged["edges"] += part["edges"]
    if not schema_only and kb_id:
        try:
            from .service import AiQueryService

            kb = await AiQueryService._knowledge_graph(kb_id)
            merged["nodes"] += kb.get("nodes", [])
            merged["edges"] += kb.get("edges", [])
        except Exception:  # noqa: BLE001
            pass
    # 合并自定义关系 + 应用布局
    rels = await _custom_relations()
    if rels:
        merged["edges"] += rels
    layout = await _layout_map()
    if layout:
        for n in merged["nodes"]:
            if n.get("name") in layout:
                n["x"] = layout[n["name"]]["x"]
                n["y"] = layout[n["name"]]["y"]
    return merged


async def _ensure_runtime_tables() -> None:
    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        await db.execute(_t(
            "CREATE TABLE IF NOT EXISTS ai_query_kg_relation ("
            "id BIGSERIAL PRIMARY KEY, source VARCHAR(200), target VARCHAR(200), "
            "rtype VARCHAR(50), weight REAL DEFAULT 1, "
            "created_time TIMESTAMP DEFAULT now())"
        ))
        await db.execute(_t(
            "CREATE TABLE IF NOT EXISTS ai_query_kg_layout ("
            "node_name VARCHAR(200) PRIMARY KEY, x DOUBLE PRECISION, y DOUBLE PRECISION)"
        ))


async def _custom_relations() -> list[dict]:
    """自定义关系：优先从 AGE 图库读，AGE 不可用则回退自有表。"""
    if await _age_available() and await _ensure_schema_age_graph():
        try:
            rows = await _run_cypher(
                "MATCH (a:SNode)-[r:CUSTOM]->(b:SNode) RETURN a.name, b.name, r.rtype", ["a", "b", "rt"])
            return [{"source": _ag(r[0]), "target": _ag(r[1]), "rtype": _ag(r[2]) or "关联", "weight": 1}
                    for r in rows]
        except Exception:  # noqa: BLE001
            pass
    from app.core.database import async_db_session

    await _ensure_runtime_tables()
    async with async_db_session() as db:
        from sqlalchemy import text as _t

        res = await db.execute(_t(
            "SELECT source, target, rtype, weight FROM ai_query_kg_relation ORDER BY id"))
        rows = res.fetchall()
    return [{"source": r[0], "target": r[1], "rtype": r[2] or "关联", "weight": float(r[3] or 1)}
            for r in rows]


async def _layout_map() -> dict:
    """节点布局：优先从 AGE 图库读，AGE 不可用则回退自有表。"""
    if await _age_available() and await _ensure_schema_age_graph():
        try:
            rows = await _run_cypher(
                "MATCH (n:SNode) WHERE exists(n.lx) RETURN n.name, n.lx, n.ly", ["n", "x", "y"])
            return {_ag(r[0]): {"x": float(_ag(r[1])), "y": float(_ag(r[2]))} for r in rows}
        except Exception:  # noqa: BLE001
            pass
    from app.core.database import async_db_session

    await _ensure_runtime_tables()
    async with async_db_session() as db:
        from sqlalchemy import text as _t

        res = await db.execute(_t("SELECT node_name, x, y FROM ai_query_kg_layout"))
        rows = res.fetchall()
    return {r[0]: {"x": float(r[1]), "y": float(r[2])} for r in rows if r[1] is not None}


async def add_relation(source: str, target: str, rtype: str = "关联", weight: int = 1) -> dict:
    """新增自定义关系：优先写入 AGE 图库，AGE 不可用则回退自有表。"""
    s = (source or "").replace("'", "''")
    t = (target or "").replace("'", "''")
    rt = (rtype or "关联").replace("'", "''")
    if await _age_available() and await _ensure_schema_age_graph():
        try:
            await _run_cypher_write(
                f"MERGE (a:SNode {{name:'{s}'}}) MERGE (b:SNode {{name:'{t}'}}) "
                f"MERGE (a)-[r:CUSTOM {{rtype:'{rt}'}}]->(b)")
            return {"source": source, "target": target, "rtype": rtype, "weight": weight}
        except Exception:  # noqa: BLE001
            pass
    from app.core.database import async_db_session

    await _ensure_runtime_tables()
    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        await db.execute(_t(
            "INSERT INTO ai_query_kg_relation(source, target, rtype, weight) "
            "VALUES (:s, :t, :r, :w)"), {"s": source, "t": target, "r": rtype, "w": weight})
    return {"source": source, "target": target, "rtype": rtype, "weight": weight}


async def delete_relation(source: str, target: str) -> int:
    """删除自定义关系：优先 AGE，AGE 不可用回退自有表。"""
    s = (source or "").replace("'", "''")
    t = (target or "").replace("'", "''")
    if await _age_available() and await _ensure_schema_age_graph():
        try:
            await _run_cypher_write(
                f"MATCH (a:SNode {{name:'{s}'}})-[r:CUSTOM]->(b:SNode {{name:'{t}'}}) DELETE r")
            return 1
        except Exception:  # noqa: BLE001
            pass
    from app.core.database import async_db_session

    await _ensure_runtime_tables()
    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        res = await db.execute(_t(
            "DELETE FROM ai_query_kg_relation WHERE source=:s AND target=:t"),
            {"s": source, "t": target})
    return int(res.rowcount or 0)


async def save_layout(items: list[dict]) -> int:
    """保存节点布局：优先写入 AGE 图库，AGE 不可用回退自有表。"""
    saved = 0
    if await _age_available() and await _ensure_schema_age_graph():
        for it in items:
            name = (it.get("name") or "").replace("'", "''")
            if not name:
                continue
            try:
                await _run_cypher_write(
                    f"MERGE (n:SNode {{name:'{name}'}}) SET n.lx={float(it['x'])}, n.ly={float(it['y'])}")
                saved += 1
            except Exception:  # noqa: BLE001
                pass
        if saved:
            return saved
    from app.core.database import async_db_session

    await _ensure_runtime_tables()
    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        for it in items:
            await db.execute(_t(
                "INSERT INTO ai_query_kg_layout(node_name, x, y) VALUES (:n, :x, :y) "
                "ON CONFLICT (node_name) DO UPDATE SET x=EXCLUDED.x, y=EXCLUDED.y"),
                {"n": it["name"], "x": it["x"], "y": it["y"]})
    return len(items)


async def traverse(start: str, hops: int = 2) -> dict:
    """跨域多跳图查询：从某节点出发，经 AGE 图库返回可达节点/路径（schema+知识库统一）。"""
    if not await _age_available() or not await _ensure_schema_age_graph():
        return {"nodes": [], "edges": [], "error": "AGE 不可用"}
    s = (start or "").replace("'", "''")
    try:
        rows = await _run_cypher(
            f"MATCH (a:SNode {{name:'{s}'}})-[*..{int(hops)}]->(b:SNode) "
            f"RETURN DISTINCT b.name, b.etype", ["n", "e"])
        nodes = [{"name": _ag(r[0]), "etype": _ag(r[1])} for r in rows if _ag(r[0])]
        return {"nodes": nodes, "edges": [], "from": start, "hops": hops}
    except Exception as e:  # noqa: BLE001
        return {"nodes": [], "edges": [], "error": str(e)[:120]}


async def age_expand_tables(seed_tables: list[str]) -> set[str]:
    """用 AGE Cypher 从种子表多跳扩展，召回关联表（并入 schema linking）。"""
    if not await _age_available() or not await _ensure_schema_age_graph():
        return set()
    if not seed_tables:
        return set()
    names = [f"表:{t}" for t in seed_tables if t]
    if not names:
        return set()
    in_list = ", ".join(["'" + n.replace("'", "''") + "'" for n in names])
    try:
        rows = await _run_cypher(
            f"MATCH (a:SNode)-[*1..2]->(b:SNode) WHERE a.name IN [{in_list}] "
            f"AND b.etype='table' RETURN DISTINCT b.name", ["n"])
        out: set[str] = set()
        for r in rows:
            nm = _ag(r[0])
            if nm.startswith("表:"):
                out.add(nm[2:])
        return out
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] AGE 扩表失败: {e}")
        return set()


async def auto_link_kb_schema() -> int:
    """把知识库实体名 与 schema 表名/中文名/字段名 匹配打边，返回新增关系数。"""
    kg = await _ensure()
    names: dict[str, str] = {}
    for nid, nd in kg.nodes.items():
        if nd["type"] in ("table", "field", "term", "metric"):
            names[nd["label"]] = _node_name(nid, nd)
    from app.core.database import async_db_session

    async with async_db_session() as db:
        from sqlalchemy import text as _t

        try:
            res = await db.execute(_t(
                "SELECT DISTINCT name FROM ai_knowledge_entity WHERE is_deleted=false"))
            ents = res.scalars().all()
        except Exception:  # noqa: BLE001
            ents = []
    out = 0
    for e in ents:
        e = (e or "").strip()
        if e in names:
            await add_relation(f"实体:{e}", names[e], "关联为", 1)
            out += 1
    return out


# ---------------------------------------------------------------------------
# Apache AGE 同步：把 schema 图谱 + 手工关系镜像进 AGE 图库（全图统一在 AGE）
# ---------------------------------------------------------------------------
_SCHEMA_AGE_GRAPH = "aistation_schema"


async def _age_available() -> bool:
    try:
        from app.plugin.module_ai.knowledge.graphrag import _age_available as _av
        return await _av()
    except Exception:  # noqa: BLE001
        return False


async def _ensure_schema_age_graph() -> bool:
    if not await _age_available():
        return False
    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        await db.execute(_t("LOAD 'age'"))
        await db.execute(_t("SET search_path = public, ag_catalog"))
        row = (await db.execute(_t(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name=:g"),
            {"g": _SCHEMA_AGE_GRAPH})).scalar()
        if not row:
            await db.execute(_t(f"SELECT create_graph('{_SCHEMA_AGE_GRAPH}')"))
    return True


def _ag(v) -> str:
    """把 agtype 返回值转成普通字符串（去引号）。"""
    if v is None:
        return ""
    s = str(v).strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1]
    return s


async def _run_cypher(cy: str, cols: list[str]) -> list[tuple]:
    """在 schema AGE 图执行 Cypher，返回行元组（每列按 agtype 返回）。"""
    from app.core.database import async_db_session

    cols_sql = ", ".join(f"\"{c}\" agtype" for c in cols)
    async with async_db_session() as db:
        from sqlalchemy import text as _t

        await db.execute(_t("LOAD 'age'"))
        await db.execute(_t("SET search_path = public, ag_catalog"))
        res = await db.execute(_t(
            f"SELECT * FROM cypher('{_SCHEMA_AGE_GRAPH}', $${cy}$$) AS ({cols_sql})"))
    return res.fetchall()


async def _run_cypher_write(cy: str) -> None:
    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        await db.execute(_t("LOAD 'age'"))
        await db.execute(_t("SET search_path = public, ag_catalog"))
        await db.execute(_t(
            f"SELECT * FROM cypher('{_SCHEMA_AGE_GRAPH}', $${cy}$$) AS (x agtype)"))


async def age_sync_schema_graph() -> int:
    """把 schema 图谱 + 自定义关系镜像写入 AGE 图库（幂等，MERGE 去重）。"""
    if not await _ensure_schema_age_graph():
        return 0
    kg = await _ensure()
    nodes = _canvas_nodes_edges(kg)["nodes"]
    edges = _canvas_nodes_edges(kg)["edges"]
    rels = await _custom_relations()
    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        from sqlalchemy import text as _t

        await db.execute(_t("LOAD 'age'"))
        await db.execute(_t("SET search_path = public, ag_catalog"))
        for n in nodes:
            name = (n["name"] or "").replace("'", "''")
            await db.execute(_t(
                f"SELECT * FROM cypher('{_SCHEMA_AGE_GRAPH}', $$ "
                f"MERGE (n:SNode {{name:'{name}'}}) SET n.etype='{n['etype']}' RETURN 1 $$) AS (x agtype)"))
        for e in edges:
            s = (e["source"] or "").replace("'", "''")
            t = (e["target"] or "").replace("'", "''")
            rt = (e.get("rtype") or "关联").replace("'", "''")
            await db.execute(_t(
                f"SELECT * FROM cypher('{_SCHEMA_AGE_GRAPH}', $$ "
                f"MERGE (a:SNode {{name:'{s}'}}) MERGE (b:SNode {{name:'{t}'}}) "
                f"MERGE (a)-[r:REL {{rtype:'{rt}'}}]->(b) RETURN 1 $$) AS (x agtype)"))
        for e in rels:
            s = (e["source"] or "").replace("'", "''")
            t = (e["target"] or "").replace("'", "''")
            rt = (e.get("rtype") or "关联").replace("'", "''")
            await db.execute(_t(
                f"SELECT * FROM cypher('{_SCHEMA_AGE_GRAPH}', $$ "
                f"MERGE (a:SNode {{name:'{s}'}}) MERGE (b:SNode {{name:'{t}'}}) "
                f"MERGE (a)-[r:CUSTOM {{rtype:'{rt}'}}]->(b) RETURN 1 $$) AS (x agtype)"))
    return len(nodes) + len(edges) + len(rels)


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
