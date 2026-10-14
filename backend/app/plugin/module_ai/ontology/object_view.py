"""对象视图（Object View）：对象数据的可复用呈现。

对齐官方 `object-views/*`：

- *"Object Views are **reusable representations of object data** … include key information
  about the object, including property data, object links, and related applications."*
- 两种：**Standard**（自动生成、反映对象类型配置）与 **Configured**（可自定义）。
- 两种形态：**Full**（完整，深入展示全部相关信息）与 **Panel**（面板，只放关键信息，供其它应用嵌入）。
- 配置模型：**tabs → widgets**。
- *"Default configured Object Views are **automatically created** for each object type …
  but once an Object View is edited it becomes **user-managed** and all further updates
  must be made manually."*
- 权限跟随对象类型（我们复用 P4 的资源 ACL：view / edit）。
- 版本管理（`manage-versions`）。

**关键设计**：视图不只是"存一份配置"，`render_view()` 会把配置**真的渲染成数据**
（属性值、关联对象、指标、图表、动作），因此可测、可截图、可被 Agent 复用。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.exceptions import CustomException

from . import service as _svc

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ONT_FORM_FACTORS = ("full", "panel")
ONT_FORM_FACTOR_LABEL = {"full": "完整视图", "panel": "面板视图"}

#: widget 种类（对应官方 widgets-* 文档的几大类）
ONT_WIDGET_TYPES = (
    "properties",   # 属性列表
    "links",        # 关系列表
    "related",      # 沿一条关系的关联对象表
    "metric",       # 指标卡
    "chart",        # 图表（分组统计）
    "filter",       # 筛选器
    "text",         # 富文本说明
    "actions",      # 可执行动作
    "scenario",     # 场景切换器（与 P5 场景联动）
    "table",        # 对象表格（可被筛选器过滤）
)
ONT_WIDGET_LABEL = {
    "properties": "属性列表", "links": "关系列表", "related": "关联对象",
    "metric": "指标卡", "chart": "图表", "filter": "筛选器",
    "text": "富文本", "actions": "动作列表", "scenario": "场景切换器",
    "table": "对象表格",
}
#: 官方把 widget 分成这几类（widgets-properties-links / visualization / filtering / layout / apps-files）
ONT_WIDGET_CATEGORY = {
    "properties": "properties-links", "links": "properties-links",
    "related": "properties-links", "actions": "properties-links",
    "metric": "visualization", "chart": "visualization",
    "filter": "filtering", "scenario": "layout", "text": "layout",
    "table": "properties-links",
}
ONT_WIDGET_CATEGORY_LABEL = {
    "properties-links": "属性与关系", "visualization": "可视化",
    "filtering": "筛选", "layout": "布局", "apps-files": "应用与文件",
}

#: 筛选算子（对齐实例层的 filters 语义）
ONT_FILTER_OPS = ("eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_empty", "not_empty")
ONT_FILTER_OP_LABEL = {
    "eq": "等于", "ne": "不等于", "contains": "包含", "gt": "大于", "gte": "大于等于",
    "lt": "小于", "lte": "小于等于", "is_empty": "为空", "not_empty": "不为空",
}

MAX_TABS = 20
MAX_WIDGETS_PER_TAB = 30


def _j(v: Any) -> str:
    from decimal import Decimal

    def _d(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (bytes, bytearray)):
            return o.decode("utf-8", "replace")
        return str(o)

    return json.dumps(v, ensure_ascii=False, default=_d)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def widget_meta(w: dict) -> dict:
    t = str((w or {}).get("type") or "")
    return {"type": t, "label": ONT_WIDGET_LABEL.get(t, t),
            "category": ONT_WIDGET_CATEGORY.get(t, "layout"),
            "category_label": ONT_WIDGET_CATEGORY_LABEL.get(
                ONT_WIDGET_CATEGORY.get(t, "layout"), "布局")}


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def validate_tabs(tabs: Any) -> list[str]:
    """校验 tabs → widgets 配置，返回错误列表。"""
    errs: list[str] = []
    if not isinstance(tabs, list):
        return ["tabs 必须是数组"]
    if len(tabs) > MAX_TABS:
        errs.append(f"标签页最多 {MAX_TABS} 个（当前 {len(tabs)}）")
    seen_keys: set[str] = set()
    for i, t in enumerate(tabs):
        if not isinstance(t, dict):
            errs.append(f"第 {i + 1} 个标签页不是对象")
            continue
        key = str(t.get("key") or "").strip()
        if not key:
            errs.append(f"第 {i + 1} 个标签页缺少 key")
        elif key in seen_keys:
            errs.append(f"标签页 key 重复：{key}")
        else:
            seen_keys.add(key)
        if not str(t.get("label") or "").strip():
            errs.append(f"标签页 {key or i + 1} 缺少标题")
        ws = t.get("widgets")
        if ws is None:
            continue
        if not isinstance(ws, list):
            errs.append(f"标签页 {key or i + 1} 的 widgets 必须是数组")
            continue
        if len(ws) > MAX_WIDGETS_PER_TAB:
            errs.append(f"标签页 {key or i + 1} 的 widget 最多 {MAX_WIDGETS_PER_TAB} 个")
        for j, w in enumerate(ws):
            if not isinstance(w, dict):
                errs.append(f"{key or i + 1} 的第 {j + 1} 个 widget 不是对象")
                continue
            wt = str(w.get("type") or "")
            if wt not in ONT_WIDGET_TYPES:
                errs.append(f"widget 类型不支持：{wt}（可用：{'、'.join(ONT_WIDGET_TYPES)}）")
    return errs


# ---------------------------------------------------------------------------
# Standard 视图：自动生成，不落库（官方：自动反映对象类型配置）
# ---------------------------------------------------------------------------
async def standard_view(object_code: str, form_factor: str = "full") -> dict:
    """按对象类型配置**即时生成**标准视图。

    官方：*"Standardized, out-of-the-box representations that automatically reflect an
    object type's configuration … available for all object types."*
    """
    ff = form_factor if form_factor in ONT_FORM_FACTORS else "full"
    obj = next((o for o in await _svc.list_objects() if o["code"] == object_code), None)
    if not obj:
        return {"ok": False, "msg": f"对象类型 {object_code} 不存在"}
    props = await _svc.list_properties(object_code)
    visible = [p for p in props if (p.get("visibility") or "normal") == "normal"]
    # 官方：默认视图放「主要属性」；没有主要属性就放全部非隐藏属性
    prominent = [p for p in visible if p.get("title_key")] or visible
    widgets: list[dict] = [
        {"type": "properties", "title": "属性",
         "config": {"props": [p["code"] for p in prominent]}},
    ]
    links = await _svc.list_links(object_code)
    if links:
        widgets.append({"type": "links", "title": "关系",
                        "config": {"link_ids": [x["id"] for x in links]}})
    acts = await _svc.list_actions(object_code)
    if acts:
        widgets.append({"type": "actions", "title": "动作",
                        "config": {"action_codes": [a["code"] for a in acts]}})
    tabs = [{"key": "overview", "label": "概览", "widgets": widgets}]
    if ff == "panel":
        # 面板视图只保留属性（官方：只放关键信息）
        tabs = [{"key": "overview", "label": "概览",
                 "widgets": [widgets[0]]}]
    return {"ok": True, "view_type": "standard", "form_factor": ff,
            "object_code": object_code, "name": f"{obj.get('name') or object_code} 标准视图",
            "tabs": tabs, "is_managed": False,
            "note": "标准视图由对象类型配置自动生成，不落库；编辑它会创建可配置视图"}


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
_V_COLS = ("SELECT id,object_code,code,COALESCE(name,''),COALESCE(description,''),"
           "COALESCE(view_type,'configured'),COALESCE(form_factor,'full'),"
           "is_default,is_managed,tabs,COALESCE(version,1),filters,share_roles,"
           "COALESCE(share_mode,'inherit'),COALESCE(status,'experimental'),"
           "COALESCE(visibility,'normal'),COALESCE(created_by,''),created_time,"
           "updated_time FROM ai_ont_object_view ")
_V_FIELDS = ("id", "object_code", "code", "name", "description", "view_type", "form_factor",
             "is_default", "is_managed", "tabs", "version", "status", "visibility",
             "created_by", "created_time", "updated_time")


def _row_to_view(row) -> dict:
    out: dict[str, Any] = {}
    for i, n in enumerate(_V_FIELDS):
        v = row[i]
        if n == "tabs":
            v = v if isinstance(v, list) else _svc._json_list(v)
        elif isinstance(v, datetime):
            v = v.strftime("%Y-%m-%d %H:%M:%S")
        out[n] = v
    out["form_factor_label"] = ONT_FORM_FACTOR_LABEL.get(out["form_factor"], out["form_factor"])
    out["widget_count"] = sum(len(t.get("widgets") or []) for t in (out["tabs"] or []))
    out["tab_count"] = len(out["tabs"] or [])
    return out


async def list_views(object_code: str | None = None, form_factor: str = "") -> list[dict]:
    sql = _V_COLS + "WHERE is_deleted=false"
    p: dict = {}
    if object_code:
        sql += " AND object_code=:o"
        p["o"] = object_code
    if form_factor:
        sql += " AND form_factor=:f"
        p["f"] = form_factor
    sql += " ORDER BY object_code, form_factor, id"
    return [_row_to_view(r) for r in (await _svc._exec(sql, p)).fetchall()]


async def get_view(code: str) -> dict | None:
    r = await _svc._exec(_V_COLS + "WHERE code=:c AND is_deleted=false", {"c": code})
    row = r.fetchone()
    if not row:
        return None
    v = _row_to_view(row)
    v["versions"] = await list_view_versions(code)
    return v


async def list_view_versions(code: str) -> list[dict]:
    r = await _svc._exec(
        "SELECT id,version,tabs,COALESCE(note,''),COALESCE(created_by,''),created_time "
        "FROM ai_ont_object_view_version WHERE view_code=:c ORDER BY version DESC",
        {"c": code})
    return [{"id": x[0], "version": x[1], "tabs": _svc._json_list(x[2]), "note": x[3],
             "created_by": x[4],
             "created_time": x[5].strftime("%Y-%m-%d %H:%M:%S") if x[5] else ""}
            for x in r.fetchall()]


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
async def ensure_default_view(object_code: str, form_factor: str = "full",
                              actor: str = "system") -> dict:
    """给对象类型自动建默认可配置视图（官方行为）。

    幂等：已有该形态的视图就不再建。
    """
    exist = list(await list_views(object_code, form_factor))
    if exist:
        return {"ok": True, "created": False, "code": exist[0]["code"],
                "msg": "已存在视图，跳过"}
    std = await standard_view(object_code, form_factor)
    if not std.get("ok"):
        return {"ok": False, "msg": std.get("msg")}
    code = f"{object_code}__{form_factor}"
    await create_view({
        "object_code": object_code, "code": code,
        "name": f"{std['name']}（默认）", "form_factor": form_factor,
        "tabs": std["tabs"], "is_default": True, "is_managed": False,
        "created_by": actor,
    })
    return {"ok": True, "created": True, "code": code,
            "msg": f"已为 {object_code} 自动创建默认{ONT_FORM_FACTOR_LABEL[form_factor]}"}


async def create_view(data: dict, actor: str = "") -> dict:
    object_code = str(data.get("object_code") or "").strip()
    if not object_code:
        raise CustomException(msg="必须指定对象类型")
    code = str(data.get("code") or "").strip() or f"{object_code}__{data.get('form_factor') or 'full'}"
    if (await _svc._exec("SELECT 1 FROM ai_ont_object_view WHERE code=:c AND is_deleted=false",
                         {"c": code})).fetchone():
        raise CustomException(msg=f"视图编码 {code} 已存在")
    tabs = data.get("tabs") or []
    errs = validate_tabs(tabs)
    if errs:
        raise CustomException(msg="视图配置有问题：" + "；".join(errs[:5]))
    ff = str(data.get("form_factor") or "full")
    if ff not in ONT_FORM_FACTORS:
        raise CustomException(msg=f"形态不支持 {ff}")
    await _svc._exec_write(
        "INSERT INTO ai_ont_object_view(object_code,code,name,description,view_type,"
        "form_factor,is_default,is_managed,tabs,filters,share_roles,share_mode,"
        "created_by) "
        "VALUES (:o,:c,:n,:d,'configured',:f,:def,:mg,:t,:fl,:sr,:sm,:cb)",
        {"o": object_code, "c": code, "n": data.get("name") or code,
         "d": data.get("description", ""), "f": ff,
         "def": bool(data.get("is_default")), "mg": bool(data.get("is_managed")),
         "t": _j(tabs), "fl": _j(data.get("filters") or []),
         "sr": _j(data.get("share_roles") or []),
         "sm": data.get("share_mode") or "inherit",
         "cb": data.get("created_by") or actor or ""})
    if data.get("is_default"):
        await _set_default(code, object_code, ff)
    await _svc._log_change(object_code, "object_view", "create", f"视图 {code}")
    return {"ok": True, "code": code, "msg": f"视图「{data.get('name') or code}」已创建"}


async def _set_default(code: str, object_code: str, form_factor: str) -> None:
    """同一 (对象类型, 形态) 只能有一个默认视图。"""
    await _svc._exec_write(
        "UPDATE ai_ont_object_view SET is_default=false "
        "WHERE object_code=:o AND form_factor=:f", {"o": object_code, "f": form_factor})
    await _svc._exec_write(
        "UPDATE ai_ont_object_view SET is_default=true WHERE code=:c", {"c": code})


async def update_view(code: str, data: dict, actor: str = "") -> dict:
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    tabs = data.get("tabs", v["tabs"])
    errs = validate_tabs(tabs)
    if errs:
        raise CustomException(msg="视图配置有问题：" + "；".join(errs[:5]))
    # 官方：一旦被编辑就转为 user-managed（不再跟随对象类型自动更新）
    became_managed = not v["is_managed"]
    new_ver = int(v["version"] or 1) + 1
    await _svc._exec_write(
        "UPDATE ai_ont_object_view SET name=:n, description=:d, tabs=:t, version=:ver, "
        "filters=:fl, share_roles=:sr, share_mode=:sm, "
        "is_managed=true, updated_time=now() WHERE code=:c",
        {"n": data.get("name") or v["name"], "d": data.get("description", v["description"]),
         "t": _j(tabs), "ver": new_ver,
         "fl": _j(data.get("filters", v.get("filters") or [])),
         "sr": _j(data.get("share_roles", v.get("share_roles") or [])),
         "sm": data.get("share_mode") or v.get("share_mode") or "inherit",
         "c": code})
    await _svc._exec_write(
        "INSERT INTO ai_ont_object_view_version(view_code,version,tabs,note,created_by) "
        "VALUES (:c,:v,:t,:n,:cb)",
        {"c": code, "v": new_ver, "t": _j(tabs),
         "n": data.get("note") or "编辑", "cb": actor})
    if data.get("is_default"):
        await _set_default(code, v["object_code"], v["form_factor"])
    await _svc._log_change(v["object_code"], "object_view", "update",
                           f"视图 {code} → v{new_ver}")
    return {"ok": True, "version": new_ver, "became_managed": became_managed,
            "msg": f"已保存为 v{new_ver}"
                   + ("（该视图已转为手工维护，不再跟随对象类型自动更新）"
                      if became_managed else "")}


async def restore_view_version(code: str, version: int, actor: str = "") -> dict:
    r = (await _svc._exec(
        "SELECT tabs FROM ai_ont_object_view_version WHERE view_code=:c AND version=:v",
        {"c": code, "v": int(version)})).fetchone()
    if not r:
        raise CustomException(msg=f"视图 {code} 没有 v{version}")
    return await update_view(code, {"tabs": _svc._json_list(r[0]),
                                    "note": f"回滚到 v{version}"}, actor)


async def remove_view(code: str) -> dict:
    await _svc._exec_write(
        "UPDATE ai_ont_object_view SET is_deleted=true WHERE code=:c", {"c": code})
    await _svc._exec_write("DELETE FROM ai_ont_object_view_version WHERE view_code=:c",
                           {"c": code})
    return {"ok": True, "msg": "视图已删除"}


async def set_default_view(code: str) -> dict:
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    await _set_default(code, v["object_code"], v["form_factor"])
    return {"ok": True, "msg": f"「{v['name']}」已设为默认视图"}


async def sync_default_views(actor: str = "system") -> dict:
    """给所有对象类型补齐默认视图（官方：默认视图对每个对象类型自动创建）。"""
    objs = await _svc.list_objects()
    created = 0
    for o in objs:
        for ff in ONT_FORM_FACTORS:
            r = await ensure_default_view(o["code"], ff, actor)
            if r.get("created"):
                created += 1
    return {"ok": True, "created": created,
            "msg": f"已为 {len(objs)} 个对象类型补齐默认视图（新建 {created} 个）"}


# ---------------------------------------------------------------------------
# 渲染：把视图配置变成真实数据
# ---------------------------------------------------------------------------
async def render_view(code: str, object_key: str, principal: Any = None,
                      scenario_code: str = "") -> dict:
    """按视图配置渲染某个对象的视图内容。

    这是"视图"真正有用的地方——把 tabs/widgets 解析成可展示的数据。
    读数据一律经过 P4 的权限与 P5 的场景叠加。
    """
    v = await get_view(code)
    if not v:
        return {"ok": False, "msg": "视图不存在"}
    inst = await _svc.instance_get(v["object_code"], object_key, principal=principal,
                                   scenario_code=scenario_code)
    if not inst.get("ok"):
        return {"ok": False, "msg": inst.get("msg") or "对象不可读",
                "denied": inst.get("denied", False)}
    props = inst.get("props") or {}
    prop_meta = {p["code"]: p for p in (inst.get("properties_meta") or [])}
    rendered: list[dict] = []
    for tab in (v["tabs"] or []):
        # 官方 widgets-filtering：筛选器作用于**同一个标签页**里的数据组件
        tab_filters = _tab_filters(tab)
        out_widgets = []
        for w in (tab.get("widgets") or []):
            out_widgets.append(await _render_widget(w, v["object_code"], object_key, props,
                                                    prop_meta, inst, principal, scenario_code,
                                                    tab_filters))
        rendered.append({"key": tab.get("key"), "label": tab.get("label"),
                         "filters": tab_filters, "widgets": out_widgets})
    return {"ok": True, "view": {"code": v["code"], "name": v["name"],
                                 "form_factor": v["form_factor"],
                                 "form_factor_label": v["form_factor_label"],
                                 "is_default": v["is_default"],
                                 "is_managed": v["is_managed"], "version": v["version"]},
            "object": {"code": v["object_code"], "key": object_key,
                       "label": inst.get("label") or props.get("name") or object_key},
            "tabs": rendered,
            "hidden_columns": inst.get("hidden_columns") or [],
            "scenario": scenario_code or None}


def _tab_filters(tab: dict) -> list[dict]:
    """收集一个标签页里所有筛选器组件定义的筛选条件。

    官方 widgets-filtering：筛选器**作用于同一个标签页**里的数据组件。
    """
    out: list[dict] = []
    for w in (tab.get("widgets") or []):
        if str(w.get("type") or "") != "filter":
            continue
        for f in ((w.get("config") or {}).get("filters") or []):
            if isinstance(f, dict) and f.get("prop"):
                op = str(f.get("op") or "eq")
                out.append({"prop": str(f["prop"]),
                            "op": op if op in ONT_FILTER_OPS else "eq",
                            "value": f.get("value")})
    return out


def _filters_to_search(filters: list[dict]) -> dict:
    """把筛选器转成 instance_search 的 filters 参数。"""
    out: dict = {}
    for f in filters or []:
        prop = str(f.get("prop") or "")
        if not prop:
            continue
        out[prop] = {"op": str(f.get("op") or "eq"), "value": f.get("value")}
    return out


def _apply_filters(rows: list[dict], filters: list[dict]) -> tuple[list[dict], int]:
    """在内存里对一批实例行应用筛选（用于关联对象这类已取回的数据）。"""
    if not filters:
        return rows, 0
    kept: list[dict] = []
    for r in rows:
        props = r.get("props") or {}
        if all(_match(props.get(f["prop"]), f["op"], f.get("value")) for f in filters):
            kept.append(r)
    return kept, len(rows) - len(kept)


def _match(actual: Any, op: str, want: Any) -> bool:
    """单值筛选判定。"""
    a, w = actual, want
    if op == "is_empty":
        return a is None or a == ""
    if op == "not_empty":
        return not (a is None or a == "")
    if op in ("gt", "gte", "lt", "lte"):
        try:
            af, wf = float(a), float(w)
        except (TypeError, ValueError):
            return False
        return {"gt": af > wf, "gte": af >= wf, "lt": af < wf, "lte": af <= wf}[op]
    if op == "contains":
        return str(w or "").lower() in str(a if a is not None else "").lower()
    if op == "ne":
        return str(a) != str(w)
    return str(a) == str(w)


async def _render_widget(w: dict, object_code: str, object_key: str, props: dict,
                         prop_meta: dict, inst: dict, principal: Any,
                         scenario_code: str, tab_filters: list[dict] | None = None) -> dict:
    wt = str(w.get("type") or "")
    cfg = w.get("config") or {}
    base = {"type": wt, "title": w.get("title") or ONT_WIDGET_LABEL.get(wt, wt),
            **widget_meta(w)}
    try:
        if wt == "properties":
            codes = [c for c in (cfg.get("props") or []) if c in prop_meta]
            if not codes:
                codes = list(prop_meta)
            base["items"] = [
                {"code": c, "name": prop_meta[c].get("name") or c,
                 "value": props.get(c), "prop_type": prop_meta[c].get("prop_type"),
                 "sensitive": bool(prop_meta[c].get("sensitive"))}
                for c in codes]
            base["count"] = len(base["items"])
        elif wt == "links":
            want = cfg.get("link_ids") or []
            links = [x for x in (inst.get("links") or [])
                     if not want or x.get("id") in want]
            base["items"] = links
            base["count"] = len(links)
        elif wt == "related":
            lid = cfg.get("link_id")
            if not lid:
                base["error"] = "未指定关系"
            else:
                r = await _svc.instance_pivot(object_code, object_key, int(lid),
                                              int(cfg.get("limit") or 20),
                                              principal=principal)
                rows = r.get("items") or []
                if tab_filters:
                    rows, dropped = _apply_filters(rows, tab_filters)
                    base["filtered_out"] = dropped
                base["rows"] = rows
                base["count"] = len(rows)
                base["policy_filtered"] = r.get("policy_filtered", False)
        elif wt == "table":
            # 对象表格：走 instance_search，因此**筛选器真的生效**（并在库里过滤）
            r = await _svc.instance_search(
                object_code, str(cfg.get("keyword") or ""),
                _filters_to_search(tab_filters or []),
                int(cfg.get("limit") or 20), 0, principal=principal,
                scenario_code=scenario_code)
            base["rows"] = r.get("items") or []
            base["columns"] = (r.get("columns") or [])[:8]
            base["count"] = len(base["rows"])
            base["total"] = r.get("total")
            base["policy_filtered"] = r.get("policy_filtered", False)
        elif wt == "metric":
            base.update(await _render_metric(cfg, object_code, object_key, props))
        elif wt == "chart":
            base.update(await _render_chart(cfg, object_code, props, principal))
        elif wt == "filter":
            base["filters"] = [
                {"prop": f.get("prop"), "op": f.get("op") or "eq",
                 "op_label": ONT_FILTER_OP_LABEL.get(str(f.get("op") or "eq"), "等于"),
                 "value": f.get("value")}
                for f in (cfg.get("filters") or []) if isinstance(f, dict)]
            base["count"] = len(base["filters"])
            base["applies_to"] = "同一标签页的数据组件"
            base["active"] = bool(tab_filters)
        elif wt == "text":
            base["markdown"] = cfg.get("markdown") or ""
        elif wt == "actions":
            want = cfg.get("action_codes") or []
            acts = [a for a in (inst.get("actions") or [])
                    if not want or a.get("code") in want]
            base["items"] = acts
            base["count"] = len(acts)
        elif wt == "scenario":
            from . import scenario as _sc

            base["items"] = await _sc.list_scenarios("active", 50)
            base["current"] = scenario_code or None
        else:
            base["error"] = f"不支持的 widget 类型：{wt}"
    except Exception as e:  # noqa: BLE001
        base["error"] = f"渲染失败：{str(e)[:120]}"
    return base


async def _render_metric(cfg: dict, object_code: str, object_key: str,
                         props: dict) -> dict:
    """指标卡：可直接读某属性，也可调一个本体函数。"""
    fn_code = str(cfg.get("function_code") or "")
    if fn_code:
        fn = next((f for f in await _svc.list_functions(None)
                   if f.get("code") == fn_code), None)
        if not fn:
            return {"error": f"函数 {fn_code} 不存在"}
        r = await _svc.run_ontology_function(fn_code, {"object_key": object_key})
        return {"value": r.get("value"), "label": cfg.get("label") or fn.get("name"),
                "unit": cfg.get("unit", ""), "source": f"function:{fn_code}",
                "ok": r.get("ok", False)}
    prop = str(cfg.get("prop") or "")
    return {"value": props.get(prop), "label": cfg.get("label") or prop,
            "unit": cfg.get("unit", ""), "source": f"property:{prop}"}


async def _render_chart(cfg: dict, object_code: str, props: dict,
                       principal: Any = None) -> dict:
    """图表：对某属性做分组统计（真实查库，不是占位）。

    **必须走带权限的聚合** —— 原先这里直接拼 SQL、签名里连 principal 都没有，
    聚合会把不该看的行也算进去（真实踩过的洞，已由 instance_aggregate 修掉）。
    """
    group_by = str(cfg.get("group_by") or "")
    if not group_by:
        return {"error": "未指定分组字段"}
    limit = max(1, min(int(cfg.get("limit") or 10), 50))
    agg = await _svc.instance_aggregate(object_code, group_by, [{"fn": "count"}],
                                        limit=limit, principal=principal)
    if not agg.get("ok"):
        return {"error": agg.get("msg") or "统计失败",
                "blocked_by": agg.get("blocked_by")}
    return {"group_by": group_by,
            "series": [{"label": s["label"] if s["label"] is not None else "（空）",
                        "value": int(s["value"])} for s in agg["series"]],
            "count": agg["count"],
            "row_policy_applied": agg.get("row_policy_applied"),
            "columns_restricted": agg.get("columns_restricted")}


# ---------------------------------------------------------------------------
# 共享（官方 use-object-views-in-platform / marketplace-object-views）
# ---------------------------------------------------------------------------
async def share_view(code: str, share_mode: str, roles: list[str] | None = None) -> dict:
    """设置视图的共享方式。

    - ``inherit``（默认）：跟随对象类型的权限（官方语义）
    - ``roles``：只给指定角色看

    注意：**只看得到视图 ≠ 看得到数据**——数据仍然走 P4 的对象权限与行/列策略。
    """
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    mode = share_mode if share_mode in ("inherit", "roles") else "inherit"
    rs = [str(x).strip() for x in (roles or []) if str(x).strip()]
    if mode == "roles" and not rs:
        raise CustomException(msg="按角色共享时至少要指定一个角色")
    await _svc._exec_write(
        "UPDATE ai_ont_object_view SET share_mode=:m, share_roles=:r WHERE code=:c",
        {"m": mode, "r": _j(rs), "c": code})
    await _svc._log_change(v["object_code"], "object_view", "share",
                           f"视图 {code} 共享方式 → {mode}")
    return {"ok": True, "share_mode": mode, "share_roles": rs,
            "msg": ("已改为跟随对象类型权限" if mode == "inherit"
                    else f"已共享给角色：{'、'.join(rs)}")}


async def can_view_view(code: str, principal: Any) -> tuple[bool, str]:
    """某个人能不能看这个视图（共享层面）。

    数据能不能看是另一回事，由 P4 的对象权限决定。
    """
    v = await get_view(code)
    if not v:
        return False, "视图不存在"
    if v.get("share_mode") != "roles":
        return True, "跟随对象类型权限"
    if principal is None:
        return True, "未提供身份，跳过共享校验"
    if getattr(principal, "is_superuser", False):
        return True, "超级管理员"
    roles = set(getattr(principal, "role_codes", []) or [])
    want = set(v.get("share_roles") or [])
    if roles & want:
        return True, "角色命中"
    return False, f"该视图只共享给：{'、'.join(sorted(want))}"


async def list_shared_views(principal: Any) -> list[dict]:
    """当前身份可见的视图（按共享设置过滤）。"""
    out = []
    for v in await list_views():
        ok, why = await can_view_view(v["code"], principal)
        if ok:
            v["share_reason"] = why
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# 生成链接（官方 generate-urls）
# ---------------------------------------------------------------------------
def view_url(code: str, object_key: str = "", base: str = "#/ai/ontology") -> str:
    """生成能直接打开某个视图 + 某个对象的深链。

    官方 generate-urls：可以把视图（含当前对象）作为链接分享出去。
    """
    from urllib.parse import quote

    v_code = quote(str(code or ""), safe="")
    q = f"objectview={v_code}"
    if object_key:
        q += f"&objectkey={quote(str(object_key), safe='')}"
    return f"{base}?{q}"


async def view_link(code: str, object_key: str = "") -> dict:
    """返回深链与其含义（界面上「复制链接」用）。"""
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    return {"ok": True, "url": view_url(code, object_key),
            "view_code": code, "object_code": v["object_code"],
            "object_key": object_key or "",
            "form_factor": v["form_factor"],
            "msg": "链接可直接打开该视图" + (f"并定位到对象 {object_key}" if object_key else "")}
