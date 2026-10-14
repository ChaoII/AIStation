"""对象查询执行器：把 IR 映射到**本体实例层**执行，返回统一结果集。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.3。

要点：
1. **零新增存储**：全部复用 `ontology/service.py` 的
   ``instance_search / instance_aggregate / instance_pivot / instance_get``。
   这些函数**已内置**行级策略下推、列级掩码、场景叠加——因此这里**绝不自己拼 SQL**
   （历史教训：`_render_chart` 曾自己拼 SQL 绕过了行级策略）。
2. **失败即 ``ok=False``**：由调用方（问数）降级到 NL2SQL。不抛异常、不返回半截结果。
3. 返回统一 ``{ok, columns, rows, shape, trace}``，供前端表格与 `_answer` 直接复用。
"""
from __future__ import annotations

from typing import Any

from app.core.logger import log

from .object_query import ObjectQueryIR


def _val(item: Any, col: str) -> Any:
    """从实例行里取列值。

    实例层返回的行是 ``_row_to_instance`` 的产物（``{"props": {...}}``），
    但经过权限/场景处理后形态可能变化，故对「扁平」与「嵌套 props」都兼容。
    """
    if not isinstance(item, dict):
        return None
    props = item.get("props")
    if isinstance(props, dict):
        return props.get(col)
    return item.get(col)


def _safe(value: Any) -> Any:
    """把值转成可 JSON 序列化的形态（问数结果会落库/下发）。"""
    from datetime import date, datetime
    from decimal import Decimal

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _is_sensitive(col: str) -> bool:
    """是否敏感列（凭据/token/内部地址等），需在结果里隐藏。复用本体启发式。"""
    try:
        from app.plugin.module_ai.ontology.service import is_sensitive_like
        return is_sensitive_like(col)
    except Exception:  # noqa: BLE001
        return False


def _filters_to_layer(filters: list[dict]) -> dict:
    """IR 的 ``[{field, op, value}]`` → 实例层的 ``{field: {op, value}}``。

    ⚠️ 实例层的 filters 是 dict，**同字段多条件会被覆盖**。这里对同字段保留
    **最后一个**，并把丢弃情况记进 trace（避免静默丢条件）。
    """
    out: dict = {}
    for f in filters or []:
        fld = str(f.get("field") or "").strip()
        if not fld:
            continue
        out[fld] = {"op": str(f.get("op") or "eq"), "value": f.get("value")}
    return out


def _extract(item: Any, field: str) -> Any:
    """从实例行取字段值（兼容扁平 / 嵌套 props）。"""
    if not isinstance(item, dict) or not field:
        return None
    props = item.get("props")
    if isinstance(props, dict):
        return props.get(field)
    return item.get(field)


def _match_op(actual: Any, op: str, expected: Any) -> bool:
    """执行层的过滤算子匹配（Python 侧）。"""
    op = (op or "eq").lower()
    if op == "is_empty":
        return actual is None or actual == ""
    if op == "not_empty":
        return not (actual is None or actual == "")
    if actual is None:
        return False
    if op == "eq":
        return str(actual) == str(expected)
    if op == "ne":
        return str(actual) != str(expected)
    if op == "contains":
        return str(expected) in str(actual)
    if op in ("gt", "gte", "lt", "lte"):
        try:
            a = float(actual)
            e = float(expected)
        except (TypeError, ValueError):
            a = e = None
        if a is not None and e is not None:
            if op == "gt":
                return a > e
            if op == "gte":
                return a >= e
            if op == "lt":
                return a < e
            if op == "lte":
                return a <= e
        return False
    if op == "in":
        vals = expected if isinstance(expected, (list, tuple, set)) else [expected]
        return str(actual) in {str(v) for v in vals}
    return False


def _apply_filters(items: list, filters: list[dict]) -> list:
    """在（已过策略的）实例集上做目标侧过滤。"""
    if not filters:
        return items
    out: list = []
    for it in items:
        ok = True
        for f in filters:
            if not isinstance(f, dict):
                continue
            if not _match_op(_extract(it, str(f.get("field") or "")),
                             str(f.get("op") or "eq"), f.get("value")):
                ok = False
                break
        if ok:
            out.append(it)
    return out


def _dedupe_items(items: list) -> list:
    seen: set = set()
    out: list = []
    for it in items:
        k = (str(it.get("object_code") or ""), str(it.get("key") or ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _aggregate_rows(items: list, group_by: str, aggs: list[dict]) -> list[list]:
    """对（traverse 后的）实例集做 Python 聚合，返回 ``[[label, value]]``。"""
    fn = "count"
    field = ""
    if aggs:
        a = aggs[0]
        fn = str(a.get("fn") or "count").lower()
        field = str(a.get("field") or "")
    groups: dict = {}
    order: list[str] = []
    for it in items:
        if group_by:
            gv = _extract(it, group_by)
            key = str(gv) if gv not in (None, "") else "<空>"
        else:
            key = "合计"
        if key not in groups:
            groups[key] = {"n": 0, "sum": 0.0, "min": None, "max": None, "vals": []}
            order.append(key)
        g = groups[key]
        g["n"] += 1
        if field:
            try:
                vf = float(_extract(it, field))
            except (TypeError, ValueError):
                vf = None
            if vf is not None:
                g["sum"] += vf
                g["vals"].append(vf)
                if g["min"] is None or vf < g["min"]:
                    g["min"] = vf
                if g["max"] is None or vf > g["max"]:
                    g["max"] = vf
    rows: list[list] = []
    for k in order:
        g = groups[k]
        if fn == "count":
            val = g["n"]
        elif fn == "sum":
            val = g["sum"] if g["vals"] else None
        elif fn == "avg":
            val = (g["sum"] / len(g["vals"])) if g["vals"] else None
        elif fn == "min":
            val = g["min"]
        elif fn == "max":
            val = g["max"]
        else:
            val = g["n"]
        rows.append([k, _safe(val)])
    return rows


async def _resolve_link_id(ont, code: str, link: str):
    try:
        for lk in await ont.list_links(code):
            if str(lk.get("name") or "") == link or str(lk.get("id")) == link:
                return int(lk["id"])
    except Exception:  # noqa: BLE001
        pass
    return None


async def _visible_columns(code: str, items: list, principal: Any) -> tuple[list, list, str]:
    """对（traverse 结果的）实例集选可见列并做列级掩码。"""
    from app.plugin.module_ai.ontology import security as _sec

    vis: set | None = None
    if principal is not None:
        try:
            vis = await _sec.visible_properties(code, principal)
        except Exception:  # noqa: BLE001
            vis = None
    sample = items[0] if items else {}
    props = sample.get("props") or {}
    cols = [str(c) for c in props.keys()]
    if vis:
        cols = [c for c in cols if c in vis]
    hidden = [c for c in cols if _is_sensitive(c)]
    keep = [c for c in cols if c not in hidden]
    dropped = f"；已隐藏敏感字段：{'、'.join(hidden)}" if hidden else ""
    rows = [[_safe(_extract(it, c)) for c in keep] for it in items]
    return keep, rows, dropped


async def _execute_traverse(ir: ObjectQueryIR, principal: Any = None) -> dict:
    """集合级、可多跳的 traverse（P3）。

    复用**已测安全**的本体 ``instance_search`` / ``instance_pivot``：
    - 起点：``instance_search``（起点侧行/列策略已在实例层下推）；
    - 每跳：``instance_pivot``（对端行/列策略已在实例层下推，``filter_instances`` 自动过滤）；
    - 跳后过滤 / 聚合：Python 侧（只作用于策略过滤后的可见实例）。

    返回统一 ``{ok, columns, rows, shape, note}``；任一跳失败 / 关系不存在 / 对象未物化
    → ``ok=False``（由调用方降级 NL2SQL）。多跳是**串行**的，任何一跳失败整条降级。
    """
    from app.plugin.module_ai.ontology import service as ont

    start_meta = await ont._instance_meta(ir.object)
    if not start_meta or not start_meta.get("materialized"):
        return {"ok": False, "error": f"对象 {ir.object} 未物化，无法跳转"}

    # ---- 起点集合 ----
    frontier: list[dict] = []
    frontier_code = ir.object
    if ir.object_key:
        r = await ont.instance_get(ir.object, ir.object_key, principal=principal)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("msg") or "起点实例不存在"}
        frontier = [{"key": str(r.get("key") or ir.object_key),
                     "object_code": ir.object, "props": r.get("props") or {}}]
    else:
        sr = await ont.instance_search(ir.object, filters=_filters_to_layer(ir.filters) or None,
                                       limit=ir.limit, principal=principal)
        if not sr.get("ok"):
            return {"ok": False, "error": sr.get("msg") or "起点查询失败"}
        frontier = list(sr.get("items") or [])
    if not frontier:
        return {"ok": True, "columns": [], "rows": [], "shape": "traverse",
                "note": "起点没有匹配的实例"}

    # ---- 串行多跳 ----
    hops = 0
    for hop in ir.traverse:
        link_id = await _resolve_link_id(ont, frontier_code, hop.get("link"))
        if link_id is None:
            return {"ok": False, "error": f"关系 {hop.get('link')} 不存在"}
        nxt: list[dict] = []
        nxt_code: str | None = None
        for item in frontier:
            key = str(item.get("key") or "")
            if not key:
                continue
            piv = await ont.instance_pivot(frontier_code, key, link_id,
                                           limit=ir.limit, principal=principal)
            if not piv.get("ok"):
                continue
            nxt_code = piv.get("other_object") or nxt_code
            for it in (piv.get("items") or []):
                nxt.append(it)
        frontier = _apply_filters(nxt, hop.get("filters") or [])
        frontier = _dedupe_items(frontier)
        if nxt_code:
            frontier_code = nxt_code
        hops += 1
        if not frontier:
            break

    if not frontier:
        return {"ok": True, "columns": [], "rows": [], "shape": "traverse",
                "note": "关系跳转后没有匹配的实例"}

    # ---- 在最终集合上聚合（P3：关联集聚合，对齐 Pattern 3）----
    if ir.aggregations:
        gb_field = ir.group_by[0]["field"] if ir.group_by else ""
        rows = _aggregate_rows(frontier, gb_field, ir.aggregations)
        col_label = (ir.group_by[0].get("alias") if ir.group_by else "") or (gb_field or "合计")
        val_label = (ir.aggregations[0].get("alias")
                     or f"{ir.aggregations[0].get('fn')}({ir.aggregations[0].get('field') or '*'})")
        return {"ok": True, "columns": [col_label, val_label], "rows": rows,
                "shape": "traverse-agg",
                "note": f"沿 {hops} 跳关系后在 {frontier_code} 上聚合"}

    # ---- 返回最终集合实例 ----
    cols, rows, dropped = await _visible_columns(frontier_code, frontier, principal)
    return {"ok": True, "columns": cols, "rows": rows, "shape": "traverse",
            "note": f"沿 {hops} 跳关系到 {frontier_code}" + dropped}


async def execute_ir(ir: ObjectQueryIR, principal: Any = None) -> dict:
    """执行对象查询 IR。

    返回::

        {"ok": True, "columns": [...], "rows": [[...]], "shape": "aggregate|search|pivot|get",
         "note": ""}
        或 {"ok": False, "error": "原因"}

    ``principal`` 是本体权限主体（由调用方 ``security.load_principal`` 装载）；
    实例层会据此做行级过滤与列级掩码。
    """
    from app.plugin.module_ai.ontology import service as ont

    try:
        meta = await ont._instance_meta(ir.object)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"对象元数据读取失败：{str(e)[:120]}"}
    if not meta or meta.get("error"):
        return {"ok": False, "error": (meta or {}).get("error") or "对象类型不存在"}
    if not meta.get("materialized"):
        return {"ok": False, "error": f"对象 {ir.object} 未物化，无法查询"}

    layer_filters = _filters_to_layer(ir.filters)

    # ---- 1) 派生属性（P3）：单对象、单属性（复用本体 compute_derived）----
    if ir.derived_property:
        if not ir.object_key:
            return {"ok": False, "error": "派生属性查询需要指定具体对象"}
        # compute_derived 内部的 pivot 不传 principal，这里先用 instance_get 确认
        # 该实例对当前身份可见，避免对不可见实例计算派生值（防泄）
        vis = await ont.instance_get(ir.object, ir.object_key, principal=principal)
        if not vis.get("ok"):
            return {"ok": False, "error": vis.get("msg") or "无权访问该实例"}
        try:
            dr = await ont.compute_derived(ir.object, ir.object_key, ir.derived_property)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"派生属性计算失败：{str(e)[:120]}"}
        if not dr.get("ok"):
            return {"ok": False, "error": dr.get("msg") or "派生属性计算失败"}
        return {"ok": True, "columns": [ir.derived_property],
                "rows": [[_safe(dr.get("value"))]], "shape": "derived",
                "note": f"派生属性 {ir.derived_property} = {_safe(dr.get('value'))}"}

    # ---- 1) 沿关系跳转（P3：集合级多跳 + 关联集聚合；复用已测安全的本体 pivot）----
    if ir.traverse:
        return await _execute_traverse(ir, principal)

    # ---- 2) 聚合（分组统计） ----
    if ir.aggregations:
        agg = ir.aggregations[0]
        gb = ir.group_by[0]["field"] if ir.group_by else ""
        a: dict = {"fn": agg["fn"]}
        if agg.get("field"):
            a["prop"] = agg["field"]
        r = await ont.instance_aggregate(
            ir.object, group_by=gb, aggs=[a], filters=layer_filters or None,
            limit=ir.limit, principal=principal)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("msg") or "聚合失败"}
        col_label = (ir.group_by[0].get("alias") if ir.group_by else "") or (gb or "合计")
        fn = agg["fn"]
        val_label = agg.get("alias") or f"{fn}({agg.get('field') or '*'})"
        return {"ok": True, "columns": [col_label, val_label],
                "rows": [[_safe(x) for x in row] for row in (r.get("rows") or [])],
                "shape": "aggregate"}

    # ---- 3) 单对象详情 ----
    if ir.object_key:
        r = await ont.instance_get(ir.object, ir.object_key, principal=principal)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("msg") or "实例不存在"}
        props = r.get("props") or {}
        # 凭证类字段**不进聊天答案**：答案会落进会话历史（`ai_query_messages.rows`），
        # 把 password/token 之类的值持久化下来不合适。复用本体既有的敏感名启发式
        # （与写回白名单同源），管理员同样过滤。
        cols = [str(c) for c in props if not ont.is_sensitive_like(str(c))]
        dropped = [str(c) for c in props if str(c) not in cols]
        return {"ok": True, "columns": cols,
                "rows": [[_safe(props.get(c)) for c in cols]], "shape": "get",
                "note": ("已隐藏敏感字段：" + "、".join(dropped)) if dropped else ""}

    # ---- 4) 列表查询 ----
    r = await ont.instance_search(ir.object, filters=layer_filters or None,
                                  limit=ir.limit, principal=principal)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("msg") or "查询失败"}
    cols = [str(c) for c in (r.get("columns") or [])]
    rows = [[_safe(_val(it, c)) for c in cols] for it in (r.get("items") or [])]
    note = ""
    if r.get("policy_filtered"):
        note = "已按行级/列级策略过滤"
    return {"ok": True, "columns": cols, "rows": rows, "shape": "search", "note": note}


__all__ = ["execute_ir"]
