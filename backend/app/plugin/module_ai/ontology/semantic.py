"""本体的**统一语义接口** —— 问数等消费方唯一该用的入口。

为什么要它
----------
问数原先有 9 处**直接拼 SQL 读 ``ai_ont_*`` 表**，没有任何契约：
本体表结构一改，问数就可能悄悄坏掉。这正是「看起来接上了，实际靠约定」
的典型形态——和之前「控制器没传 principal」是同一类问题。

这里把**读路径**收敛成几个稳定函数，语义只留一份：

- ``object_table_map()``   真实支撑表名 → 对象 code（白名单/SQL 改写用）
- ``semantic_context()``   对象 / 属性 / 关系 / 函数 / 概念（prompt grounding 用）
- ``sensitive_fields()``   **唯一的**敏感字段来源
- ``sync_sensitive()``     把两套 sensitive 标记对齐（本体为准）

写路径（从数据源反向生成本体）仍留在原处，不在本模块职责内。
"""
from typing import Any

from .service import _exec


# ---------------------------------------------------------------------------
# 对象 → 真实支撑表
# ---------------------------------------------------------------------------
async def object_table_map() -> dict[str, str]:
    """真实支撑表名 → 对象 code。

    **支撑表不一定叫 ``ont_{code}``**：由数据源支撑的对象（``video_cameras`` /
    ``demo_sales``）支撑表就是它自己；而 ``backing_table`` 为空的（``orders``）
    真实表是 ``ont_orders``。两种都收，且与 ``semantic_context`` 用**同一套解析**，
    避免"白名单认一张表、prompt 里写另一张表"。
    """
    out: dict[str, str] = {}
    for o in await _load_objects():
        if o["code"]:
            out[f"ont_{o['code']}"] = o["code"]
        out[o["table"]] = o["code"]
    return out


# ---------------------------------------------------------------------------
# 统一语义上下文
# ---------------------------------------------------------------------------
async def _existing_tables() -> set[str]:
    """库里真实存在的表名集合（一次拿全，用于解析支撑表）。"""
    try:
        rows = (await _exec(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public'", {})).fetchall()
        return {r[0] for r in rows}
    except Exception:  # noqa: BLE001
        return set()


def _resolve_table(code: str, backing_table: str, existing: set[str]) -> str:
    """算出对象类型的**真实支撑表名**。

    约定优先级：显式 ``backing_table`` → ``ont_{code}`` → ``code``。
    踩过的坑：``backing_table`` 为空时旧实现直接回退到 ``code``，
    于是把「订单」指向一张**不存在的表 orders**（真实表叫 ``ont_orders``），
    模型照着写就查不出来；而同一份代码里的 ``object_table_map()``
    却按 ``ont_{code}`` 映射——**两个函数互相矛盾**。
    这里改成**按库里实际存在哪张表来定**，两边就不会再打架。
    """
    if backing_table:
        return backing_table
    cand = f"ont_{code}"
    if not existing or cand in existing:
        return cand
    return code


async def _load_objects() -> list[dict]:
    """只加载对象类型（不递归、不含属性），供 semantic_context 与 concepts 共用。"""
    try:
        # 注意：aliases 是 **JSONB**，不能写 COALESCE(aliases,'')
        # ——Postgres 会报 "COALESCE types jsonb and text cannot be matched"，
        # 整个查询失败、对象列表变空。原样取，Python 侧兜底（跨方言也稳）。
        rows = (await _exec(
            "SELECT code, name, backing_table, description, aliases, domain_code, "
            "key_prop, name_prop "
            "FROM ai_ont_object WHERE is_deleted=false AND enabled=true ORDER BY id", {})).fetchall()
    except Exception:  # noqa: BLE001
        return []
    existing = await _existing_tables()
    return [{
        "code": r[0], "name": r[1] or r[0],
        "table": _resolve_table(r[0], r[2] or "", existing),
        "description": r[3] or "", "aliases": _split_aliases(r[4]),
        "domain": r[5] or "", "key_prop": r[6] or "id", "name_prop": r[7] or "name",
    } for r in rows]


async def semantic_context(include_properties: bool = True) -> dict[str, Any]:
    """一次拿全本体的业务语义，供 prompt grounding / 实体解析使用。

    返回::

        {
          "objects":   [{code, name, table, description, aliases, domain,
                         key_prop, name_prop}],
          "properties":{object_code: [{code, name, prop_type, required,
                                       sensitive, roles, description}]},
          "relations": [{source, target, name, card, source_field,
                         target_field, join_method}],
          "functions": [{object_code, name, code, expr, kind}],
          "concepts":  [{name, description, synonyms, domain, tables, metric_key}],
        }

    ``concepts`` 是**合并后**的概念：本体对象自带的 ``aliases`` / 域，
    再加上问数原有的业务概念表（那部分语义问数确实独有，保留但走同一出口）。
    """
    objects: list[dict] = await _load_objects()

    properties: dict[str, list[dict]] = {}
    if include_properties:
        try:
            # required/sensitive 是 **boolean**、roles 是 **jsonb**：
            # 都不能 COALESCE 成 0 / ''，否则 Postgres 报类型不匹配，
            # 整句失败、属性列表变空。原样取，Python 侧兜底。
            # ⚠️ 必须按 `enabled` 过滤：否则"禁用"是**装饰性的**——
            #    用户/运营把对象关掉了，它仍然出现在问数的本体上下文里（实测 203/416 启用）。
            #    白名单（object_table_map）**不过滤**：禁用只代表"不主动提供"，不代表"禁止查询"。
            rows = (await _exec(
                "SELECT object_code, name, code, prop_type, required, sensitive, "
                "description, roles "
                "FROM ai_ont_property WHERE is_deleted=false "
                "ORDER BY object_code, id", {})).fetchall()
        except Exception:  # noqa: BLE001
            rows = []
        for r in rows:
            properties.setdefault(r[0], []).append({
                "code": r[2], "name": r[1] or r[2], "prop_type": r[3] or "",
                "required": bool(r[4]), "sensitive": bool(r[5]),
                "description": r[6] or "", "roles": _split_aliases(r[7]),
            })

    relations: list[dict] = []
    try:
        rows = (await _exec(
            "SELECT COALESCE(source_object,''), COALESCE(target_object,''), "
            "COALESCE(name,''), COALESCE(card,''), COALESCE(source_field,''), "
            "COALESCE(target_field,''), COALESCE(join_method,'foreign_key') "
            "FROM ai_ont_link WHERE is_deleted=false ORDER BY source_object, id",
            {})).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        relations.append({"source": r[0], "target": r[1], "name": r[2], "card": r[3],
                          "source_field": r[4], "target_field": r[5],
                          "join_method": r[6]})

    functions: list[dict] = []
    try:
        rows = (await _exec(
            "SELECT COALESCE(object_code,''), COALESCE(name,''), COALESCE(code,''), "
            "COALESCE(expr,''), COALESCE(kind,'expression') FROM ai_ont_function "
            "WHERE is_deleted=false ORDER BY object_code, id", {})).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        functions.append({"object_code": r[0], "name": r[1], "code": r[2],
                          "expr": r[3], "kind": r[4]})

    return {"objects": objects, "properties": properties,
            "relations": relations, "functions": functions,
            "concepts": await concepts()}


def _split_aliases(raw: Any) -> list[str]:
    """把 aliases / roles 这类字段解析成字符串列表（兼容 JSON 与逗号分隔）。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if s.startswith("["):
        import json

        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) for x in v if str(x).strip()]
        except Exception:  # noqa: BLE001
            pass
    return [x.strip() for x in s.split(",") if x.strip()]


async def concepts() -> list[dict]:
    """业务概念：**本体对象自带的别名/域** + 问数原有的概念表（合并后一份出口）。

    本体这边本来就是语义源，但历史概念表里有些东西（同义词、映射到指标）
    对象类型上没有对应字段，直接删会丢信息，所以合并而不是替换。
    """
    out: list[dict] = []
    seen: set[str] = set()

    for o in await _load_objects():
        for al in o["aliases"]:
            key = al.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({"name": key, "description": f"{o['name']}的别名",
                        "synonyms": "", "domain": o["domain"],
                        "tables": [o["table"]], "metric_key": "", "source": "ontology"})

    # 问数原有的概念表（独有信息：同义词、指标映射）
    # —— 走**共享目录接口**，本体不直读问数的表
    from .. import catalog as _catalog

    for c in await _catalog.list_concepts():
        key = (c.get("name") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"name": key, "description": c.get("description") or "",
                    "synonyms": c.get("synonyms") or "", "domain": c.get("domain") or "",
                    "metric_key": c.get("metric_key") or "",
                    "tables": c.get("tables") or [], "source": "query_concept"})
    return out


# ---------------------------------------------------------------------------
# 敏感标记：唯一的真相源 + 两套对齐
# ---------------------------------------------------------------------------
async def sensitive_fields() -> dict[str, set[str]]:
    """对象 code → 敏感属性集合。**本体是唯一真相源。**"""
    out: dict[str, set[str]] = {}
    try:
        rows = (await _exec(
            "SELECT object_code, code FROM ai_ont_property "
            "WHERE is_deleted=false AND sensitive=true", {})).fetchall()
    except Exception:  # noqa: BLE001
        return out
    for oc, code in rows:
        out.setdefault(oc, set()).add(code)
    return out


async def sensitive_diff() -> dict:
    """对比两套敏感标记，列出**不一致**的字段。

    历史遗留：本体 ``ai_ont_property.sensitive`` 与问数
    ``ai_query_asset_columns.sensitive`` 是两套并行标记，实测已经不一致
    （本体 11 个 vs 问数 2 个）。同一个字段在一边标敏感、另一边没标，
    是**真实的数据风险**，所以这里把它显式暴露出来。
    """
    ont = await sensitive_fields()
    ont_flat = {(oc, p) for oc, ps in ont.items() for p in ps}

    # 目录侧敏感标记 —— 走共享目录接口（本体不直读问数的表）
    from .. import catalog as _catalog

    q_flat: set[tuple[str, str]] = set(await _catalog.list_sensitive_columns())

    # 把本体的 (object_code, prop_code) 映射到真实表名，才能和问数那边比
    tmap = {}
    for o in await _load_objects():
        tmap[o["code"]] = o["table"]
    ont_by_table = {(tmap.get(oc, oc), p) for oc, p in ont_flat}

    return {
        "ontology_only": sorted(ont_by_table - q_flat),
        "query_only": sorted(q_flat - ont_by_table),
        "both": sorted(ont_by_table & q_flat),
        "ontology_total": len(ont_by_table),
        "query_total": len(q_flat),
    }


async def sync_sensitive(direction: str = "ontology_to_query") -> dict:
    """把敏感标记对齐。

    默认 **本体 → 问数**（本体是真相源）：把本体的敏感标记写回问数资产目录。
    反向（``query_to_ontology``）用于把问数里已标敏感但本体漏标的补上——
    这一向不会清除任何标记，只做"并集"，避免误删。
    """
    from .service import _exec_write

    diff = await sensitive_diff()
    changed: list[str] = []
    tmap = {}
    for o in await _load_objects():
        tmap[o["code"]] = o["table"]

    if direction == "ontology_to_query":
        from .. import catalog as _catalog

        ont = await sensitive_fields()
        pairs: list[tuple[str, str]] = []
        for oc, props in ont.items():
            table = tmap.get(oc, oc)
            for p in props:
                pairs.append((table, p))
                changed.append(f"{table}.{p}")
        # 走共享目录接口（幂等）；本体不直写问数的表
        await _catalog.mark_sensitive(pairs)
        return {"ok": True, "direction": direction, "changed": changed,
                "before": diff, "msg": f"已按本体对齐 {len(changed)} 个敏感字段"}
    if direction == "query_to_ontology":
        for table, col in diff["query_only"]:
            code = None
            for c, t in tmap.items():
                if t == table:
                    code = c
                    break
            if not code:
                continue
            try:
                await _exec_write(
                    "UPDATE ai_ont_property SET sensitive=true "
                    "WHERE object_code=:o AND code=:c", {"o": code, "c": col})
                changed.append(f"{code}.{col}")
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "direction": direction, "changed": changed,
                "before": diff, "msg": f"已从问数补标 {len(changed)} 个敏感字段"}
    return {"ok": False, "msg": f"不认识的方向 {direction}"}


# ---------------------------------------------------------------------------
# 便捷：给 prompt 用的文本块（问数直接用，不用自己拼）
# ---------------------------------------------------------------------------
async def context_block(max_relations: int = 80,
                        only_tables: set[str] | None = None,
                        include_properties: bool = True) -> str:
    """把语义渲染成 prompt 文本块。**问数不再自己拼表名**。

    ``only_tables`` 是**关键的性能开关**：不传就全量倾倒（85 个对象、
    1500+ 属性 → 三万七千字符），LLM 的前缀计算全花在无关对象上。
    问数应当**先用本地检索挑出相关表**，再只把这几张表的语义塞进 prompt。

    另外只带**出现在已选对象之间**的关系 —— 否则 join 提示里会混进一堆
    跟本次问题无关的表，既浪费 token 又干扰模型。
    """
    ctx = await semantic_context(include_properties=include_properties)
    objs = {o["code"]: o for o in ctx["objects"]}
    if only_tables:
        want = {str(t).strip() for t in only_tables if str(t).strip()}
        # 按表名或对象 code 都能匹配（支撑表常与原表名不同）
        objs = {c: o for c, o in objs.items()
                if o["table"] in want or c in want}
    if not objs:
        return ""
    lines = ["【本体对象（业务对象语义，优先理解）】"]
    for code, o in objs.items():
        head = f"- 对象「{o['name']}」→表 {o['table']}"
        ps = ctx["properties"].get(code, [])
        if ps:
            head += "：" + ", ".join(
                f"{p['name']}({p['code']})" + (" 敏感" if p["sensitive"] else "")
                for p in ps)
        if o["description"]:
            head += f"（{o['description']}）"
        lines.append(head)
        for fn in [f for f in ctx["functions"] if f["object_code"] == code]:
            lines.append(f"   · 函数「{fn['name']}」({fn['code']}): {fn['expr']}")
    rels = [r for r in ctx["relations"]
            if r["source"] in objs and r["target"] in objs][:max_relations]
    if rels:
        lines.append("【本体关系（写多表查询时按此 join，不要靠字段名猜）】")
        for r in rels:
            s, t = objs[r["source"]], objs[r["target"]]
            line = f"- 「{s['name']}」{s['table']}"
            if r["source_field"] and r["target_field"]:
                line += f".{r['source_field']} = 「{t['name']}」{t['table']}.{r['target_field']}"
            else:
                line += f" ↔ 「{t['name']}」{t['table']}（{r['join_method']}）"
            if r["name"]:
                line += f"   关系名：{r['name']}"
            if r["card"]:
                line += f"，基数：{r['card']}"
            lines.append(line)
    return "\n".join(lines)
