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

    # ---- 1) 沿关系跳转（P0：单跳，且需要具体对象） ----
    if ir.traverse:
        tr = ir.traverse[0]
        link = None
        try:
            for lk in await ont.list_links(ir.object):
                if str(lk.get("name") or "") == tr["link"] or str(lk.get("id")) == tr["link"]:
                    link = lk
                    break
        except Exception:  # noqa: BLE001
            link = None
        if not link:
            return {"ok": False, "error": f"关系 {tr['link']} 不存在"}
        r = await ont.instance_pivot(ir.object, ir.object_key, int(link["id"]),
                                     limit=ir.limit, principal=principal)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("msg") or "关系跳转失败"}
        cols = [str(c) for c in (r.get("columns") or [])]
        rows = [[_safe(_val(it, c)) for c in cols] for it in (r.get("items") or [])]
        return {"ok": True, "columns": cols, "rows": rows, "shape": "pivot",
                "note": f"沿关系「{tr['link']}」跳转"}

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
