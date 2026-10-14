"""问数「对象查询」IR：LLM 只输出**结构化查询**，不写 SQL。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.2–§3.4。

为什么要它：问数的困难题失分来自「LLM 猜 join / 猜口径」。改成由 LLM 只选择
「查哪个对象、怎么过滤、按什么分组、算什么」，由实例层确定性执行，join 与口径
就不再靠猜。

三条硬约束（本模块是它们的落点）：
1. **词汇表收敛**：IR 里的 object/field/link **必须**来自「授权 ∩ 检索命中」的清单，
   越界项直接剔除（对象越界则整条作废）。这同时是反幻觉的架构性保证。
2. **严格降级**：解析失败 / 校验失败 / 形态不支持 → 一律返回 ``None``，由调用方
   回退 NL2SQL。**绝不**因新路径失败而答不出来。
3. **不写 SQL**：本模块是纯逻辑，无 IO，可 ``PYTEST_NO_APP=1`` 快测。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 过滤算子词表 —— **必须与本体筛选器一致**（`object_view.ONT_FILTER_OPS` /
#: `instance_search` 的分支）。两套词表打架会让条件静默落到 eq 分支。
IR_OPS: tuple[str, ...] = (
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "is_empty", "not_empty",
)

#: 聚合算子 —— 与 `instance_aggregate` 支持的集合一致。
IR_AGGS: tuple[str, ...] = ("count", "sum", "avg", "min", "max")

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

#: P0 形状限制：多分组 / 多指标 / 多跳 一律不支持 → 降级（宁可降级，不可答半截）。
MAX_GROUP_BY = 1
MAX_AGGS = 1
MAX_TRAVERSE = 1


@dataclass
class ObjectQueryIR:
    """对象查询中间表示。字段名与 LLM 输出一致，便于排查。"""

    object: str = ""
    filters: list[dict] = field(default_factory=list)
    traverse: list[dict] = field(default_factory=list)
    group_by: list[dict] = field(default_factory=list)
    aggregations: list[dict] = field(default_factory=list)
    order_by: list[dict] = field(default_factory=list)
    limit: int = DEFAULT_LIMIT
    object_key: str = ""
    derived_property: str = ""
    metric: str = ""

    def to_dict(self) -> dict:
        return {
            "object": self.object,
            "filters": self.filters,
            "traverse": self.traverse,
            "group_by": self.group_by,
            "aggregations": self.aggregations,
            "order_by": self.order_by,
            "limit": self.limit,
            "object_key": self.object_key,
            "derived_property": self.derived_property,
            "metric": self.metric,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ObjectQueryIR":
        def _list(v: Any) -> list:
            return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

        def _int(v: Any) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return DEFAULT_LIMIT

        return cls(
            object=str(d.get("object") or "").strip(),
            filters=_list(d.get("filters")),
            traverse=_list(d.get("traverse")),
            group_by=_list(d.get("group_by")),
            aggregations=_list(d.get("aggregations")),
            order_by=_list(d.get("order_by")),
            limit=_int(d.get("limit")),
            object_key=str(d.get("object_key") or "").strip(),
            derived_property=str(d.get("derived_property") or "").strip(),
            metric=str(d.get("metric") or "").strip(),
        )


def parse_ir(text: str) -> ObjectQueryIR | None:
    """从模型输出里取第一个完整 JSON 对象并转成 IR；取不到返回 ``None``。

    复用 ``plan._first_json_object`` 的花括号配平逻辑（容错围栏 / 前后噪声 / 截断），
    不重写一份。
    """
    if not text:
        return None
    try:
        from .plan import _first_json_object
    except Exception:  # noqa: BLE001
        _first_json_object = None  # type: ignore[assignment]
    obj = None
    if _first_json_object is not None:
        try:
            obj = _first_json_object(text)
        except Exception:  # noqa: BLE001
            obj = None
    if obj is None:
        # 兜底：直接尝试 json.loads（模型偶尔只给纯 JSON）
        try:
            raw = json.loads(text)
            obj = raw if isinstance(raw, dict) else None
        except Exception:  # noqa: BLE001
            obj = None
    if not isinstance(obj, dict):
        return None
    return ObjectQueryIR.from_dict(obj)


def _resolve_object(val: str, allowed: dict) -> str | None:
    """把模型给的「编码或中文名」解析成对象编码。

    实测模型经常回填**中文显示名**（如「摄像机表」）而不是编码（`video_cameras`）。
    这里两者都接受——**宁可宽容解析，也不要因为一个字面量就把整条路径判死刑**。
    """
    v = (val or "").strip()
    if not v:
        return None
    if v in (allowed or {}):
        return v
    for code, spec in (allowed or {}).items():
        if str((spec or {}).get("name") or "").strip() == v:
            return code
    return None


def _resolve_field(val: str, fields: dict) -> str | None:
    """把模型给的「字段编码或中文名」解析成字段编码。"""
    v = (val or "").strip()
    if not v:
        return None
    if v in (fields or {}):
        return v
    for code, meta in (fields or {}).items():
        if str((meta or {}).get("name") or "").strip() == v:
            return code
    return None


def validate_ir(ir: ObjectQueryIR | None, allowed: dict,
                max_traverse_depth: int = 1,
                metrics: dict | None = None) -> tuple[ObjectQueryIR | None, list[str]]:
    """按「授权 ∩ 检索命中」清单校验并清洗 IR。

    ``allowed`` 形如::

        {
          "video_cameras": {
            "name": "摄像机表",
            "fields": {"id": {"name": "ID", "type": "string", "options": []}, ...},
            "links":  {"摄像机_告警记录": {"id": 3, "target": "video_alarm_records", ...}},
          }, ...
        }

    返回 ``(清洗后的 IR | None, 提示列表)``。**对象越界 → 整条作废**（None）；
    字段/算子越界 → **剔除该项**（其余保留）。对象与字段都接受「编码或中文名」。
    """
    reasons: list[str] = []
    if ir is None:
        return None, ["没有解析出对象查询结构"]

    raw_object = (ir.object or "").strip()
    if not raw_object:
        return None, ["缺少 object（要查的对象类型）"]
    code = _resolve_object(raw_object, allowed)
    if not code:
        # 对象不在授权/命中范围 → 整条作废（这是 scope 收敛的关键一步）
        return None, [f"对象 {raw_object} 不在可查询范围（未授权或未被检索命中）"]

    spec = allowed[code] or {}
    fields: dict = spec.get("fields") or {}
    links: dict = spec.get("links") or {}

    # ---- metric（绑定指标，可选）：必须在可用指标白名单内，且绑定对象与查询对象一致 ----
    raw_metric = (ir.metric or "").strip()
    if raw_metric:
        m = (metrics or {}).get(raw_metric)
        if not m:
            reasons.append(f"指标 {raw_metric} 不在可用范围，已忽略")
            ir.metric = ""
        else:
            mo = str(m.get("object_code") or "")
            if mo and mo != code:
                reasons.append(f"指标 {raw_metric} 绑定对象 {mo} 与查询对象 {code} 不符，已忽略")
                ir.metric = ""
            else:
                ir.metric = raw_metric

    # ---- filters ----
    keep_f: list[dict] = []
    for f in ir.filters or []:
        raw = str(f.get("field") or "").strip()
        fld = _resolve_field(raw, fields)
        op = str(f.get("op") or "eq").strip().lower()
        if not fld:
            reasons.append(f"过滤字段 {raw or '(空)'} 不属于对象 {code}，已忽略")
            continue
        if op not in IR_OPS:
            reasons.append(f"过滤算子 {op} 不支持，已忽略")
            continue
        keep_f.append({"field": fld, "op": op, "value": f.get("value")})
    ir.filters = keep_f

    # ---- traverse ----
    keep_t: list[dict] = []
    for t in ir.traverse or []:
        raw = str(t.get("link") or "").strip()
        lname = raw if raw in links else next(
            (k for k in links if k == raw), None)
        if not lname:
            reasons.append(f"关系 {raw or '(空)'} 不存在，已忽略")
            continue
        # 目标过滤算子同样走词表（避免把任意 op 传进执行层）
        _tf: list[dict] = []
        for _f in (t.get("filters") or []):
            if not isinstance(_f, dict):
                continue
            _op = str(_f.get("op") or "eq").strip().lower()
            if _op not in IR_OPS:
                reasons.append(f"关系过滤算子 {_op} 不支持，已忽略")
                continue
            _tf.append({"field": str(_f.get("field") or "").strip(),
                        "op": _op, "value": _f.get("value")})
        keep_t.append({
            "link": lname,
            "direction": str(t.get("direction") or "auto").strip().lower(),
            "filters": _tf,
            "as": str(t.get("as") or "").strip(),
        })
    ir.traverse = keep_t

    # ---- group_by ----
    keep_g: list[dict] = []
    for g in ir.group_by or []:
        raw = str(g.get("field") or "").strip()
        fld = _resolve_field(raw, fields)
        if not fld:
            reasons.append(f"分组字段 {raw or '(空)'} 不属于对象 {code}，已忽略")
            continue
        keep_g.append({"field": fld, "alias": str(g.get("alias") or "").strip()})
    ir.group_by = keep_g

    # ---- aggregations ----
    keep_a: list[dict] = []
    for a in ir.aggregations or []:
        fn = str(a.get("fn") or "count").strip().lower()
        if fn not in IR_AGGS:
            reasons.append(f"聚合 {fn} 不支持，已忽略")
            continue
        raw = str(a.get("field") or a.get("prop") or "").strip()
        prop = ""
        if raw not in ("", "*"):
            prop = _resolve_field(raw, fields) or ""
            if not prop:
                reasons.append(f"聚合字段 {raw} 不属于对象 {code}，已忽略")
                continue
        if fn != "count" and not prop:
            reasons.append(f"聚合 {fn} 需要字段，已忽略")
            continue
        keep_a.append({"fn": fn, "field": prop, "alias": str(a.get("alias") or "").strip()})
    ir.aggregations = keep_a

    # ---- order_by ----
    aliases = {g["alias"] for g in keep_g if g.get("alias")} | {
        a["alias"] for a in keep_a if a.get("alias")}
    keep_o: list[dict] = []
    for o in ir.order_by or []:
        raw = str(o.get("field") or "").strip()
        fld = _resolve_field(raw, fields) or (raw if raw in aliases else None)
        if not fld:
            reasons.append(f"排序字段 {raw or '(空)'} 不可用，已忽略")
            continue
        keep_o.append({"field": fld,
                       "dir": "desc" if str(o.get("dir") or "").lower() == "desc" else "asc"})
    ir.order_by = keep_o

    # ---- 形态限制 ----
    if len(ir.group_by) > MAX_GROUP_BY:
        return None, ["暂不支持多字段分组"]
    if len(ir.aggregations) > MAX_AGGS:
        return None, ["暂不支持多个指标同时聚合"]
    # P3：多跳 traverse 按上限**截断**（剔除超出的跳）而非整条作废；上限默认 1，可配 2–3。
    max_depth = max(1, min(int(max_traverse_depth or 1), 3))
    if len(ir.traverse) > max_depth:
        reasons.append(f"多跳关系超过上限 {max_depth} 跳，仅保留前 {max_depth} 跳")
        ir.traverse = ir.traverse[:max_depth]
    # 派生属性暂只支持单个（对齐 compute_derived 的单对象、单属性语义）
    if "," in ir.derived_property:
        reasons.append("派生属性暂只支持单个，仅保留第一个")
        ir.derived_property = (ir.derived_property.split(",")[0] or "").strip()

    if not (ir.filters or ir.group_by or ir.aggregations or ir.traverse
            or ir.object_key or ir.derived_property or ir.metric):
        return None, ["没有可执行的查询条件"]

    # ---- limit ----
    try:
        lim = int(ir.limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        lim = DEFAULT_LIMIT
    ir.limit = max(1, min(lim, MAX_LIMIT))
    ir.object = code
    return ir, reasons


def render_ir_prompt(question: str, allowed: dict, max_objects: int = 8,
                     max_traverse_depth: int = 1, metrics: dict | None = None) -> str:
    """生成"输出对象查询 JSON"的提示词。

    **只注入 allowed 里的对象/属性/关系（+ 绑定指标）**（不是全量 schema）—— 这既是
    scope 收敛，也避免模型编造清单外的对象名（`plan.py` 的教训：编出来的名字会被当命令执行）。
    """
    lines: list[str] = []
    for code, spec in list((allowed or {}).items())[:max_objects]:
        name = spec.get("name") or code
        # **编码在前、中文名在后**：实测把中文名放前面时，模型会直接回填中文名。
        head = f"- {code}（{name}）"
        fnames = []
        for fcode, fmeta in (spec.get("fields") or {}).items():
            fname = (fmeta or {}).get("name") or fcode
            opts = (fmeta or {}).get("options") or []
            tail = f" 取值[{','.join(str(o) for o in opts[:12])}]" if opts else ""
            fnames.append(f"{fcode}({fname}{tail})")
        head += "：字段 " + ", ".join(fnames) if fnames else ""
        lines.append(head)
        lnames = list((spec.get("links") or {}).keys())
        if lnames:
            lines.append("    可用关系：" + "、".join(lnames))
        mspec = spec.get("metrics") or {}
        if mspec:
            mdesc = []
            for mk, m in mspec.items():
                dims = ",".join(m.get("bound_dimensions") or [])
                mdesc.append(
                    f"{mk}({m.get('name') or mk},聚合={m.get('agg_fn') or 'count'}"
                    + (f",维度={dims}" if dims else "") + ")")
            lines.append("    可用指标：" + "、".join(mdesc))

    schema_block = "\n".join(lines) if lines else "（没有可用的对象）"
    return (
        "你是数据查询助手。把用户问题转成**对象查询 JSON**，**不要写 SQL**。\n\n"
        f"# 可用对象（**只能从这里选**，清单外的对象/字段会被直接丢弃）\n{schema_block}\n\n"
        "# 输出格式（严格只返回这一个 JSON，不要解释、不要代码块以外内容）\n"
        "{\n"
        '  "object": "对象编码",\n'
        '  "filters": [{"field": "字段编码", "op": "eq|ne|gt|gte|lt|lte|in|contains|is_empty|not_empty", "value": 值}],\n'
        '  "group_by": [{"field": "字段编码", "alias": "中文列名"}],\n'
        '  "aggregations": [{"fn": "count|sum|avg|min|max", "field": "字段编码(count 可留空)", "alias": "中文列名"}],\n'
        '  "order_by": [{"field": "字段编码或聚合别名", "dir": "asc|desc"}],\n'
        '  "traverse": [{"link": "关系名", "direction": "auto|source|target", "filters": [{"field": "对端字段编码", "op": "eq|...", "value": 值}], "as": "别名"}],\n'
        '  "derived_property": "派生属性编码（可选）",\n'
        '  "metric": "指标key（可选；问题命中「可用指标」时优先填它，不要自己拼聚合）",\n'
        '  "limit": 100\n'
        "}\n\n"
        "# 硬性要求\n"
        "1. `object` 与 `field` 一律填**英文编码**（括号前那个），**不要填中文名**。\n"
        "2. 二者都必须是上面清单里出现过的；清单里没有合适的对象就不要硬凑。\n"
        "3. `group_by` 最多 1 个；`aggregations` 最多 1 个。\n"
        "4. 只筛选、不统计 → 只给 filters。\n"
        "5. 所有聚合/分组列都要给中文 `alias`（用户会直接看到列头）。\n"
        "6. **只要问题里出现**「分布 / 统计 / 数量 / 有多少 / 几个 / 占比 / 各…的… / 每个… / 按…分组」"
        "**就必须同时给 `group_by` 与 `aggregations`**（这是最常见的统计诉求）。\n"
        "7. **禁止**返回「filters/group_by/aggregations 全为空」的结果——那等于没查。\n"
        f"8. 需要「沿关系跳转到另一类对象」时用 `traverse`（可连续多跳，最多 {max_traverse_depth} 跳；"
        "`direction` 默认 auto，`filters` 是对端过滤）。\n"
        "9. 需要「派生属性」（如某对象的告警数/关联计数）时用 `derived_property` 填派生属性编码。\n"
        "10. 若问题正好是某个「可用指标」（如「批次量」），**优先**填 `metric`（填指标 key），"
        "由系统用该指标的权威口径执行——**不要**自己再拼 group_by+aggregations。\n\n"
        "# 示例\n"
        "问：统计每个区域的设备数量\n"
        '答：{"object":"devices","group_by":[{"field":"region","alias":"区域"}],'
        '"aggregations":[{"fn":"count","field":"","alias":"数量"}],"limit":100}\n'
        "问：各状态的设备分别有多少\n"
        '答：{"object":"devices","group_by":[{"field":"status","alias":"状态"}],'
        '"aggregations":[{"fn":"count","field":"","alias":"数量"}],"limit":100}\n'
        "问：查一下区域为华南的设备\n"
        '答：{"object":"devices","filters":[{"field":"region","op":"eq","value":"华南"}],"limit":100}\n\n'
        f"# 用户问题\n{question}\n\n"
        "只返回 JSON。"
    )


def build_allowed(objects: list[dict], props_by_code: dict, links_by_code: dict,
                  metrics_by_object: dict | None = None) -> dict:
    """把「对象 + 属性 + 关系（+ 绑定指标）」组装成 ``allowed`` 结构（纯函数，便于单测）。"""
    out: dict = {}
    for o in objects or []:
        code = str(o.get("code") or "").strip()
        if not code:
            continue
        fields: dict = {}
        for p in (props_by_code or {}).get(code) or []:
            pcode = str(p.get("code") or "").strip()
            if not pcode:
                continue
            fields[pcode] = {
                "name": p.get("name") or pcode,
                "type": p.get("prop_type") or p.get("type") or "",
                "options": list(p.get("options") or []),
            }
        links: dict = {}
        for lk in (links_by_code or {}).get(code) or []:
            lname = str(lk.get("name") or "").strip() or f"link_{lk.get('id')}"
            links[lname] = {
                "id": lk.get("id"),
                "source": lk.get("source_object"),
                "target": lk.get("target_object"),
                "card": lk.get("card"),
            }
        metrics: dict = {}
        for m in (metrics_by_object or {}).get(code) or []:
            mkey = str(m.get("key") or "").strip()
            if mkey:
                metrics[mkey] = m
        out[code] = {"name": o.get("name") or code, "fields": fields,
                     "links": links, "metrics": metrics}
    return out
