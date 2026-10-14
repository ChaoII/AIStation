"""大模型自动建模：LLM 调用（agno）+ 容错解析 + 口径验证 + 幂等落库。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md` §3。

要点：
1. **LLM 一律走 agno**（复用 `AiQueryService._ir_runtime` 的模型解析），不新增直连。
2. 解析必须**容错**（围栏/噪声/截断）——模型的 JSON 输出从不保证干净。
3. 生成的一切都**幂等**落库、可反复跑。
"""
from __future__ import annotations

import json
import re

from app.core.logger import log

_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _salvage_objects(raw: str) -> list[dict]:
    """从**被截断**的 JSON 里救回完整对象（花括号配平扫描，跳过字符串内的括号）。"""
    out: list[dict] = []
    stack: list[int] = []
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            try:
                obj = json.loads(raw[start : i + 1])
            except Exception:  # noqa: BLE001
                obj = None
            if isinstance(obj, dict):
                out.append(obj)
    return out


def parse_json_objects(text: str) -> list[dict]:
    """容错解析 LLM 输出里的**对象列表**（围栏/噪声/包裹/截断都兜住）。

    返回 `list[dict]`；解析不出返回 `[]`（**不抛异常**）。
    """
    raw = _JSON_FENCE_RE.sub("", (text or "").strip()).strip()
    if not raw:
        return []

    # 1) 先试数组（若先抽 {...} 只会拿到第一条）
    s, e = raw.find("["), raw.rfind("]")
    if 0 <= s < e:
        try:
            arr = json.loads(raw[s : e + 1])
            if isinstance(arr, list):
                return [x for x in arr if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            pass

    # 2) 再试对象：取任一列表值（metrics/objects/annotations/cases/items），或裸对象
    s2, e2 = raw.find("{"), raw.rfind("}")
    if 0 <= s2 < e2:
        try:
            data = json.loads(raw[s2 : e2 + 1])
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    return v
            return [data]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

    # 3) 兜底：输出被截断 → 花括号配平救回完整对象
    return [x for x in _salvage_objects(raw) if isinstance(x, dict)]


_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")
_AGG_FNS = ("count", "sum", "avg", "min", "max")


def build_metric_prompt(objects: list[dict]) -> str:
    """构造「生成绑定型指标」提示：只给对象与字段，要求可直接执行的口径。"""
    lines = [
        "你是数据指标建模专家。下面是一个业务数据源的对象与字段，",
        "请为它们设计**可复用的绑定型指标**（指标 = 对象 + 聚合 + 可选维度）。",
        "要求：",
        "1) 只使用下面出现的 object_code 与字段 code；",
        "2) key 用英文字母/数字/下划线，风格 `{对象}_{聚合}_{字段}`；",
        "3) agg_fn ∈ count/sum/avg/min/max（count 可不需要字段，其余必须有字段）；",
        "4) bound_dimensions 填适合分组的字段 code（可空）；",
        '5) 严格只返回 JSON：{"metrics":[{"key","name","description","object_code",'
        '"property_code","agg_fn","bound_dimensions"}]}。',
        "【可用对象与字段】",
    ]
    for o in (objects or [])[:20]:
        cols = ", ".join(
            f"{f.get('code')}({f.get('name') or ''})" for f in (o.get("fields") or [])[:14])
        lines.append(
            f"{o.get('code')}（{o.get('name') or ''}，表 {o.get('table') or ''}）：{cols}")
    return "\n".join(lines)


def parse_metrics(text: str, valid_objects: dict) -> list[dict]:
    """容错解析 LLM 产出的指标，清洗为可落库结构。

    过滤：`object_code` 不在 `valid_objects`、`key` 非法字符、非 count 却缺字段。
    """
    out: list[dict] = []
    for it in parse_json_objects(text):
        key = str(it.get("key") or "").strip()
        oc = str(it.get("object_code") or it.get("object") or "").strip()
        if not key or not _KEY_RE.match(key):
            continue
        if oc not in (valid_objects or {}):
            continue
        fn = str(it.get("agg_fn") or it.get("agg") or "count").strip().lower()
        if fn not in _AGG_FNS:
            fn = "count"
        prop = str(it.get("property_code") or it.get("field") or "").strip()
        if fn != "count" and not prop:
            continue
        dims = it.get("bound_dimensions") or []
        dims = [str(d) for d in dims if isinstance(d, (str, int)) and str(d).strip()]
        out.append({
            "key": key, "name": str(it.get("name") or key).strip(),
            "description": str(it.get("description") or "").strip(),
            "object_code": oc, "property_code": prop, "agg_fn": fn,
            "bound_dimensions": dims,
        })
    return out


async def verify_metric(metric: dict) -> dict:
    """**执行验证**绑定型指标口径：能跑通且结果非空/非退化才通过。

    验证用超级用户主体（口径能跑通与否与行策略无关）。
    """
    from app.plugin.module_ai.ontology import security as _sec
    from app.plugin.module_ai.ontology import service as ont

    obj = str(metric.get("object_code") or "")
    if not obj:
        return {"ok": False, "reason": "缺少 object_code"}
    prop = str(metric.get("property_code") or "")
    fn = str(metric.get("agg_fn") or "count")
    dims = metric.get("bound_dimensions") or []
    gb = str(dims[0]) if dims else ""
    a: dict = {"fn": fn}
    if prop:
        a["prop"] = prop
    principal = _sec.Principal(user_id=0, name="建模验证", is_superuser=True)
    try:
        r = await ont.instance_aggregate(obj, group_by=gb, aggs=[a], principal=principal)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:100]}"}
    if not r.get("ok"):
        return {"ok": False, "reason": r.get("msg") or "聚合失败"}
    rows = r.get("rows") or []
    if not rows:
        return {"ok": False, "reason": "空结果"}
    try:
        from .eval_metrics import is_degenerate_result

        if is_degenerate_result(rows):
            return {"ok": False, "reason": "退化结果（无区分度）"}
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "rows": rows}


async def collect_objects(datasource: str, max_objects: int = 12) -> list[dict]:
    """收集某数据源的对象与字段（供建模提示词使用）。"""
    from app.plugin.module_ai.ontology import semantic as _sem
    from app.plugin.module_ai.ontology import service as ont

    ds_id: int | None = None
    if datasource and datasource not in ("system", None):
        try:
            ds_id = int(str(datasource).split(":")[-1])
        except (TypeError, ValueError):
            ds_id = None
    try:
        ctx = await _sem.semantic_context(include_properties=False)
    except Exception:  # noqa: BLE001
        return []
    objs = ctx.get("objects") or []
    if ds_id is not None:
        objs = [o for o in objs if int(o.get("datasource_id") or 0) == ds_id]
    out: list[dict] = []
    for o in objs[:max_objects]:
        code = str(o.get("code") or "")
        if not code:
            continue
        try:
            meta = await ont._instance_meta(code)
        except Exception:  # noqa: BLE001
            meta = {}
        cols = set(meta.get("cols") or [])
        fields = [
            {"code": str(p.get("code")), "name": p.get("name"),
             "type": p.get("prop_type") or p.get("type")}
            for p in (meta.get("props") or []) if p.get("code") in cols
        ]
        out.append({"code": code, "name": o.get("name") or code,
                    "table": o.get("table") or "", "fields": fields})
    return out


async def generate_metrics(datasource: str, auth, max_objects: int = 12,
                           dry: bool = False) -> dict:
    """一轮「生成→验证→落库」绑定型指标。

    ``dry=True`` 只生成+验证、不落库（用于预览）。
    返回 ``{parsed, verified, saved, rejected, reasons}``。
    """
    from types import SimpleNamespace

    from .service import AiQueryService

    objects = await collect_objects(datasource, max_objects)
    if not objects:
        return {"parsed": 0, "verified": 0, "saved": 0, "rejected": 0,
                "reasons": ["无可用对象"]}
    text = await model_llm(build_metric_prompt(objects))
    valid = {o["code"]: o for o in objects}
    metrics = parse_metrics(text, valid)
    saved = rejected = 0
    reasons: list[str] = []
    for m in metrics:
        v = await verify_metric(m)
        if not v.get("ok"):
            rejected += 1
            reasons.append(f"{m['key']} → {v.get('reason')}")
            continue
        if not dry:
            await AiQueryService.upsert_metric(
                SimpleNamespace(
                    datasource=datasource, key=m["key"], name=m["name"],
                    description=m["description"], sql_template="SELECT 1 AS 数值",
                    params=[], dimensions=[], agg=m["agg_fn"], unit="",
                    permission_tag="", enabled=True, sort=0, cache_ttl=0,
                    object_code=m["object_code"], property_code=m["property_code"],
                    agg_fn=m["agg_fn"], bound_dimensions=m["bound_dimensions"]),
                auth)
        saved += 1
    log.info(f"[modeling] 指标生成：解析 {len(metrics)}，通过/落库 {saved}，拒绝 {rejected}")
    return {"parsed": len(metrics), "verified": saved, "saved": saved,
            "rejected": rejected, "reasons": reasons[:10]}


def build_annotate_prompt(objects: list[dict]) -> str:
    """构造「对象/属性标注」提示：补中文名、业务描述、字段枚举。"""
    lines = [
        "你是数据语义标注专家。下面是一个业务数据源的对象与字段，请为它们补**简明中文名**与"
        "**一句话业务描述**；字段若有明确枚举取值请给出 options。",
        "要求：",
        "1) 只标注下面出现的 object_code 与字段 code；",
        "2) 中文名要短、专业、便于业务人员理解；描述一句话说清用途；",
        '3) 严格只返回 JSON：{"annotations":[{"object_code","object_name","description",'
        '"fields":[{"code","name","options"}]}]}。',
        "【可用对象与字段】",
    ]
    for o in (objects or [])[:20]:
        cols = ", ".join(
            f"{f.get('code')}({f.get('name') or ''})" for f in (o.get("fields") or [])[:14])
        lines.append(
            f"{o.get('code')}（表 {o.get('table') or ''}）：{cols}")
    return "\n".join(lines)


def parse_annotations(text: str, valid_objects: dict) -> list[dict]:
    """容错解析标注结果，过滤未知对象/字段。"""
    out: list[dict] = []
    for it in parse_json_objects(text):
        oc = str(it.get("object_code") or "").strip()
        if oc not in (valid_objects or {}):
            continue
        valid_fields = {
            str(f.get("code")) for f in (valid_objects.get(oc, {}).get("fields") or [])
            if f.get("code")
        }
        fields: list[dict] = []
        for f in (it.get("fields") or []):
            if not isinstance(f, dict):
                continue
            fc = str(f.get("code") or "").strip()
            if not fc or (valid_fields and fc not in valid_fields):
                continue
            opts = f.get("options") or []
            opts = ([str(o) for o in opts if isinstance(o, (str, int))]
                    if isinstance(opts, list) else [])
            fields.append({"code": fc, "name": str(f.get("name") or "").strip(),
                           "options": opts})
        out.append({
            "object_code": oc,
            "object_name": str(it.get("object_name") or it.get("name") or "").strip(),
            "description": str(it.get("description") or "").strip(),
            "fields": fields,
        })
    return out


async def _annotate_object(code: str, name: str, description: str) -> None:
    """**定向**更新对象的中文名/描述。

    ⚠️ 不能用 `upsert_object` 做局部更新：它会把 `datasource_id`/`backing_table`/
    `key_prop` 一并写回默认值，把对象的跨库绑定清掉（实测会破坏 ds:4 对象）。
    """
    from sqlalchemy import text

    from app.core.database import async_db_session

    sets, params = [], {"c": code}
    if name:
        sets.append("name=:n")
        params["n"] = name
    if description:
        sets.append("description=:d")
        params["d"] = description
    if not sets:
        return
    async with async_db_session.begin() as db:
        await db.execute(text(
            f"UPDATE ai_ont_object SET {','.join(sets)}, updated_time=now() WHERE code=:c"),
            params)


async def _annotate_property(object_code: str, code: str, name: str,
                             options: list | None = None) -> None:
    """**定向**更新属性的中文名/枚举（同样不能用 upsert_property 做局部更新）。"""
    import json as _json

    from sqlalchemy import text

    from app.core.database import async_db_session

    sets, params = [], {"oc": object_code, "c": code}
    if name:
        sets.append("name=:n")
        params["n"] = name
    if options:
        sets.append("options=CAST(:o AS jsonb)")
        params["o"] = _json.dumps(options, ensure_ascii=False)
    if not sets:
        return
    async with async_db_session.begin() as db:
        await db.execute(text(
            f"UPDATE ai_ont_property SET {','.join(sets)} WHERE object_code=:oc AND code=:c"),
            params)


async def generate_annotations(datasource: str, auth, max_objects: int = 12) -> dict:
    """一轮「生成→落库」对象/属性标注。返回 ``{parsed, saved}``。"""
    objects = await collect_objects(datasource, max_objects)
    if not objects:
        return {"parsed": 0, "saved": 0, "reasons": ["无可用对象"]}
    text = await model_llm(build_annotate_prompt(objects))
    valid = {o["code"]: o for o in objects}
    anns = parse_annotations(text, valid)
    saved = 0
    for a in anns:
        await _annotate_object(a["object_code"], a["object_name"], a["description"])
        for f in a["fields"]:
            await _annotate_property(a["object_code"], f["code"], f["name"], f["options"])
        saved += 1
    log.info(f"[modeling] 标注生成：解析 {len(anns)}，落库 {saved}")
    return {"parsed": len(anns), "saved": saved}


async def model_llm(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str:
    """一次建模 LLM 调用（**走 agno**，与问数同源模型）。

    失败一律 `log.warning` + 返回 `""`（不抛）——调用方按"无产出"处理。
    """
    try:
        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        from .service import AiQueryService

        runtime = await AiQueryService._ir_runtime()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=0.0, max_tokens=max_tokens, timeout=timeout,
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-modeling"),
        )
        agent = Agent(model=model, telemetry=False)
        resp = await agent.arun(prompt)
        content = getattr(resp, "content", "") or ""
        if not content.strip():
            log.warning("[modeling] LLM 返回空正文")
        return content
    except Exception as e:  # noqa: BLE001
        log.warning(f"[modeling] LLM 调用失败 [{type(e).__name__}]: {str(e)[:120]}")
        return ""
