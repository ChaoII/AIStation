"""本体能力 → Agent 工具。

以 OpenAI function schema + 派发器的形式提供，由 agent 运行时直接并入工具集
（``agno_tools.dynamic.build_dynamic_tools`` 消费），因此无需在 ``ai_tools`` 目录另建行。

能力模型见 ``docs/ai-agent-capability-model.md``：
- 本体函数 Function → 可运行的只读计算（表达式求值，入参可由 ``parameters`` 声明）
- 对象动作 Action  → 变更类，仅「提议」，由用户确认后执行
- 对象清单/接地   → 注入 Agent 上下文，供其决定按需调用哪个本体能力

P2 增强：
1. 工具描述优先取官方字段 ``tool_description``，回退到 ``description``
2. 入参 schema 由 ``parameters`` 声明驱动（类型/必填/说明/枚举），回退到表达式变量或 input_schema
3. 动作调用前做**白名单预校验**，把运行期失败提前成可读错误
4. 能力清单按 ``visibility`` / ``status`` 过滤：hidden 与 deprecated 不暴露给 Agent
"""
from __future__ import annotations

import ast
import operator as op
import time
from typing import Any


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


ONTOLOGY_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_ontology",
            "description": "列出本体对象及其可用的函数/动作（Agent 据此决定按需调用哪个本体能力）",
            "parameters": _obj(
                {"object_code": {"type": "string", "description": "可选：只看某个对象"}}
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_ontology_function",
            "description": "运行一个本体函数（按 code），传入字段值，返回计算结果",
            "parameters": _obj(
                {
                    "code": {"type": "string", "description": "本体函数编码"},
                    "args": {"type": "object", "description": "字段名→值"},
                },
                ["code"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_ontology_action",
            "description": "提议执行一个对象动作（按 code）；变更类操作需用户确认后由前端执行",
            "parameters": _obj(
                {
                    "code": {"type": "string", "description": "对象动作编码"},
                    "args": {"type": "object", "description": "动作入参"},
                },
                ["code"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ontology_decisions",
            "description": (
                "查询本体的决策记录（谁在何时、基于什么、做了什么决策、结果如何）。"
                "回答「以前遇到类似情况是怎么处理的」这类问题时用这个。"
            ),
            "parameters": _obj(
                {
                    "object_code": {"type": "string", "description": "可选：只看关于某个对象的决策"},
                    "status": {"type": "string",
                               "description": "可选：proposed/approved/rejected/executed"},
                    "keyword": {"type": "string", "description": "可选：标题/理由关键词"},
                }
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_decision_lineage",
            "description": "查看某条决策的完整谱系：上游依据（用了哪些数据/函数/上游决策）与下游影响",
            "parameters": _obj(
                {"code": {"type": "string", "description": "决策编码"},
                 "depth": {"type": "integer", "description": "递归层数，默认 3"}},
                ["code"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_decision",
            "description": (
                "提出一条决策建议（**只登记为待决，不会直接执行**，需人工拍板）。"
                "务必写清 rationale（为什么这么建议）与 evidence（依据了哪些数据）。"
            ),
            "parameters": _obj(
                {
                    "title": {"type": "string", "description": "决策标题（一句话说清做什么）"},
                    "object_code": {"type": "string", "description": "决策针对的对象类型编码"},
                    "object_key": {"type": "string", "description": "决策针对的对象实例主键"},
                    "action_code": {"type": "string", "description": "建议执行的动作编码（可选）"},
                    "params": {"type": "object", "description": "建议执行动作的参数"},
                    "rationale": {"type": "string", "description": "决策理由"},
                    "evidence": {
                        "type": "array",
                        "description": "决策依据列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string",
                                         "description": "object/function/metric/decision/external/manual"},
                                "ref": {"type": "string", "description": "引用标识"},
                                "label": {"type": "string", "description": "人读说明"},
                            },
                        },
                    },
                },
                ["title"],
            ),
        },
    },
]

ONTOLOGY_TOOL_NAMES: set[str] = {s["function"]["name"] for s in ONTOLOGY_TOOL_SCHEMAS}

_BINOPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.FloorDiv: op.floordiv,
}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg, ast.Not: op.not_}
_CMP = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
}


def _safe_eval(expr: str, variables: dict) -> Any:
    """受限表达式求值：仅算术/比较/布尔，无属性访问与函数调用。"""

    def _ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            raise ValueError(f"未知变量：{node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.BoolOp):
            vals = [_ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Compare):
            left = _ev(node.left)
            for o, c in zip(node.ops, node.comparators, strict=False):
                if type(o) not in _CMP or not _CMP[type(o)](left, _ev(c)):
                    return False
                left = _ev(c)
            return True
        raise ValueError("不支持的表达式")

    return _ev(ast.parse(expr, mode="eval"))


# ---------------------------------------------------------------------------
# 参数声明 → JSON Schema
# ---------------------------------------------------------------------------
_JSON_TYPE = {
    "string": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "date": "string",
    "datetime": "string",
    "object_ref": "string",
}


def _param_props(params: list | None) -> tuple[dict, list[str]]:
    """把 ``parameters`` 声明转成 JSON Schema 的 properties + required。

    声明形如::

        [{"key": "name", "label": "新名称", "type": "string", "required": true,
          "description": "改成什么", "options": ["A", "B"]}]
    """
    props: dict = {}
    required: list[str] = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        key = (p.get("key") or p.get("name") or "").strip()
        if not key:
            continue
        item: dict = {"type": _JSON_TYPE.get(str(p.get("type") or "string"), "string")}
        desc = p.get("description") or ""
        label = p.get("label") or ""
        if label and label != key:
            item["description"] = f"{label}：{desc}" if desc else label
        elif desc:
            item["description"] = desc
        opts = p.get("options")
        if isinstance(opts, list) and opts:
            item["enum"] = opts
        props[key] = item
        if p.get("required"):
            required.append(key)
    return props, required


def _action_props(a: dict) -> tuple[dict, list[str]]:
    """动作入参 schema：优先 parameters，回退 input_schema，再回退白名单。"""
    props, required = _param_props(a.get("parameters"))
    if not props:
        for fld in a.get("input_schema") or []:
            if not isinstance(fld, dict):
                continue
            key = (fld.get("key") or fld.get("name") or "").strip()
            if not key:
                continue
            props[key] = {
                "type": _JSON_TYPE.get(str(fld.get("type") or "string"), "string"),
                "description": fld.get("label") or fld.get("description") or key,
            }
            if fld.get("required"):
                required.append(key)
    if not props:
        for w in a.get("white_fields") or []:
            key = (w if isinstance(w, str) else w.get("key") or "").strip()
            if key:
                props[key] = {"type": "string", "description": key}
    return props, required


def _action_description(a: dict, code: str) -> str:
    """工具描述：tool_description（给 AI 看的）优先，回退 description，再回退结构化摘要。"""
    td = (a.get("tool_description") or "").strip()
    if td:
        return td
    d = (a.get("description") or "").strip()
    if d:
        return d
    return f"对象动作：{a.get('name') or code}（{a.get('target_table') or '—'}.{a.get('method') or 'update'}）"


def _fn_description(f: dict, code: str) -> str:
    """函数工具描述：tool_description 优先，其次描述，再回退到形态说明。"""
    td = (f.get("tool_description") or "").strip()
    if td:
        return td
    d = (f.get("description") or "").strip()
    if d:
        return d
    kind = f.get("kind") or "expression"
    if kind == "expression":
        return f"本体函数：{f.get('name') or code}（{f.get('expr') or ''}）"
    labels = {"aggregate": "关联聚合", "http": "调外部服务", "model": "调用模型"}
    outs = [o.get("name") or o.get("key") for o in (f.get("outputs") or []) if isinstance(o, dict)]
    tail = f"，返回 {'、'.join(outs)}" if outs else ""
    return f"本体函数：{f.get('name') or code}（{labels.get(kind, kind)}{tail}）"


def _visible(item: dict) -> bool:
    """是否可暴露给 Agent：hidden 与 deprecated 不暴露。"""
    if (item.get("visibility") or "normal") == "hidden":
        return False
    return (item.get("status") or "experimental") != "deprecated"


async def _log_tool_call(name: str, latency_ms: int, result: str,
                         error: str | None = None) -> None:
    """把本体工具调用记到**本体自己的留痕表**（``ai_ont_change_log``，kind='tool_call'）。

    为什么记这里而不是 ``ai_call_logs``：那张表属于 AI 调用日志模块，且**没有工具名字段**
    （历史实现查的是不存在的 ``tool_name`` 列 → 被裸 except 吞掉 → 「读数」永远是 0）。
    工具调用是本体自己的用量事实，记在自己表里既内聚、又彻底消除跨模块直读。
    """
    try:
        from app.plugin.module_ai.ontology import service as ont

        detail = f"{name} {latency_ms}ms" + (f" error={error[:120]}" if error else "")
        await ont._log_change("-", "tool_call", result, detail)
    except Exception:  # noqa: BLE001 用量统计失败不影响工具执行
        pass


def _call_result(out: Any) -> tuple[str, str | None]:
    """按返回值判定调用结果：工具实现多以 ``{"error": ...}`` 返回失败而非抛异常。"""
    if isinstance(out, dict):
        err = out.get("error")
        if err:
            return "error", str(err)
    return "success", None


async def run_ontology_tool(name: str, args: dict, user_id: int | None = None) -> Any:
    """本体通用工具入口（计时 + 记用量，供「用量-读数」统计）。"""
    t0 = time.perf_counter()
    try:
        out = await _run_ontology_tool_impl(name, args, user_id)
    except Exception as e:  # noqa: BLE001
        await _log_tool_call(name, int((time.perf_counter() - t0) * 1000), "error", str(e))
        raise
    result, err = _call_result(out)
    await _log_tool_call(name, int((time.perf_counter() - t0) * 1000), result, err)
    return out


async def _run_ontology_tool_impl(name: str, args: dict, user_id: int | None = None) -> Any:
    """本体通用工具派发。

    **P4**：带 ``user_id`` 时会按该用户的本体权限过滤可发现的资源
    （Agent 不能看到、也不能调用调用者本人无权访问的对象/函数/动作）。
    """
    from app.plugin.module_ai.ontology import security as sec
    from app.plugin.module_ai.ontology import service as ont

    args = args or {}
    principal = await sec.load_principal(user_id) if user_id else None

    async def _allowed(kind: str, code: str) -> bool:
        if principal is None:
            return True
        ok, _ = await sec.can_view_resource(kind, code, principal)
        return ok

    if name == "list_ontology":
        obj_code = (args.get("object_code") or "").strip() or None
        objs = await ont.list_objects()
        if obj_code:
            objs = [o for o in objs if o.get("code") == obj_code]
        out = []
        for o in objs[:50]:
            if not _visible(o):
                continue
            if principal is not None and not await _allowed("object", o["code"]):
                continue
            funcs = [f for f in await ont.list_functions(o["code"]) if _visible(f)]
            acts = [a for a in await ont.list_actions(o["code"]) if _visible(a)]
            if principal is not None:
                funcs = [f for f in funcs if await _allowed("function", f["code"])]
                acts = [a for a in acts if await _allowed("action", a["code"])]
            out.append(
                {
                    "object": o.get("code"),
                    "name": o.get("name"),
                    "status": o.get("status"),
                    "visibility": o.get("visibility"),
                    "functions": [
                        {
                            "code": f.get("code"),
                            "name": f.get("name"),
                            "expr": f.get("expr") or "",
                            "description": f.get("tool_description")
                            or f.get("description")
                            or "",
                        }
                        for f in funcs
                    ],
                    "actions": [
                        {
                            "code": a.get("code"),
                            "name": a.get("name"),
                            "approval": a.get("approval"),
                            "description": a.get("tool_description")
                            or a.get("description")
                            or "",
                        }
                        for a in acts
                    ],
                }
            )
        return {"objects": out}

    if name == "run_ontology_function":
        code = (args.get("code") or "").strip()
        if not code:
            return {"error": "缺少函数编码"}
        r = await ont.run_ontology_function(code, args.get("args") or {})
        if not r.get("ok"):
            return {"error": r.get("msg") or "函数执行失败"}
        return {"code": code, "name": r.get("name"), "kind": r.get("kind"),
                "result": r.get("value"), "outputs": r.get("outputs")}
    if name == "list_ontology_decisions":
        from . import decision as dec

        rows = await dec.list_decisions(
            status=(args.get("status") or None),
            object_code=(args.get("object_code") or None),
            keyword=(args.get("keyword") or None), limit=30)
        return {"decisions": [
            {"code": d["code"], "title": d["title"], "status": d["status_label"],
             "object": f"{d['object_code']}#{d['object_key']}" if d["object_code"] else "",
             "action": d["action_code"], "rationale": d["rationale"],
             "made_by": d["made_by"], "made_at": d["made_at"],
             "data_version": d["data_version"], "channel": d["channel_label"],
             "outcome": d["outcome"] or None}
            for d in rows]}
    if name == "get_decision_lineage":
        from . import decision as dec

        code = (args.get("code") or "").strip()
        if not code:
            return {"error": "缺少决策编码"}
        r = await dec.decision_lineage(code, int(args.get("depth") or 3))
        if not r.get("ok"):
            return {"error": r.get("msg") or "查询失败"}

        def _brief(n: dict) -> dict:
            return {"code": n.get("code"), "title": n.get("title"),
                    "status": n.get("status_label"), "made_by": n.get("made_by"),
                    "made_at": n.get("made_at"), "data_version": n.get("data_version"),
                    "evidence": [{"kind": e["kind_label"], "ref": e["ref"],
                                  "label": e["label"]} for e in n.get("evidence") or []],
                    "impacts": [{"kind": i["kind_label"], "ref": i["ref"],
                                 "note": i["note"]} for i in n.get("impacts") or []],
                    "upstream": [_brief(x) for x in n.get("upstream") or []],
                    "downstream": [_brief(x) for x in n.get("downstream") or []]}

        return {"summary": r["summary"], "lineage": _brief(r["lineage"])}
    if name == "propose_decision":
        from . import decision as dec

        title = (args.get("title") or "").strip()
        if not title:
            return {"error": "缺少决策标题"}
        ev = []
        for e in args.get("evidence") or []:
            if isinstance(e, dict):
                ev.append({"kind": e.get("kind") or "manual", "ref": e.get("ref", ""),
                           "label": e.get("label", ""),
                           "value": {"source": "agent"}})
        r = await dec.upsert_decision({
            "title": title, "object_code": args.get("object_code", ""),
            "object_key": args.get("object_key", ""),
            "action_code": args.get("action_code", ""),
            "params": args.get("params") or {},
            "rationale": args.get("rationale", ""),
            "channel": "agent", "made_by": "AI 智能体",
            "status": "proposed", "evidence": ev,
        })
        return {"code": r["code"], "status": "proposed",
                "note": "已登记为待决决策，需人工拍板后才会执行",
                "data_version": r.get("auto_data_version")}

    if name == "propose_ontology_action":
        code = (args.get("code") or "").strip()
        if not code:
            return {"error": "缺少动作编码"}
        acts = await ont.list_actions(None)
        a = next((x for x in acts if x.get("code") == code), None)
        if not a:
            return {"error": f"对象动作 {code} 不存在"}
        # P4：Agent 不能提议它自己（代表的人）无权执行的动作
        if principal is not None:
            ok_a, why_a = await sec.check_action_allowed(a, principal)
            if not ok_a:
                return {"error": f"无权提议动作 {code}：{why_a}"}
        call_args = args.get("args") or {}
        # 白名单预校验：把运行期失败提前成可读错误
        bad = await _check_whitelist(a, call_args)
        if bad:
            return {"error": bad}
        tgt = a.get("target_table") or "—"
        method = a.get("method") or "update"
        return {
            "__action__": {
                "type": "confirm",
                "api": "ontologyAction",
                "label": f"执行对象动作「{a.get('name') or code}」（{tgt}.{method}）",
                "payload": {"code": code, "args": call_args},
            }
        }

    return {"error": f"未知本体工具：{name}"}


async def _key_names(a: dict) -> set[str]:
    """可接受的目标行主键参数名。

    ``object_key`` / ``__k`` 是工具 schema 约定的名字；``id`` 作为通用兜底
    （本项目所有对象类型的主键默认都是 ``id``）；再补上该对象类型自己声明的 key_prop。
    """
    from app.plugin.module_ai.ontology import service as ont

    keys = {"object_key", "__k", "id"}
    try:
        o = next((x for x in await ont.list_objects() if x.get("code") == a.get("object_code")), None)
        if o and o.get("key_prop"):
            keys.add(str(o["key_prop"]))
    except Exception:  # noqa: BLE001
        pass
    return keys


async def _check_whitelist(a: dict, call_args: dict) -> str:
    """动作调用的白名单/必填预校验，返回错误文本（空串表示通过）。"""
    writable = [
        (w if isinstance(w, str) else w.get("key") or "") for w in (a.get("white_fields") or [])
    ]
    writable = [w for w in writable if w]
    key_names = await _key_names(a)
    if writable:
        illegal = [k for k in call_args if k not in writable and k not in key_names]
        if illegal:
            return (
                f"字段 {', '.join(illegal)} 不在动作「{a.get('name') or a.get('code')}」的可写白名单内；"
                f"可写字段：{', '.join(writable)}"
            )
    # 必填参数校验（来自 parameters 声明）
    missing = [
        p.get("key")
        for p in (a.get("parameters") or [])
        if isinstance(p, dict) and p.get("required") and p.get("key") and p.get("key") not in call_args
    ]
    if missing:
        return f"缺少必填参数：{', '.join(missing)}"
    if (a.get("method") or "update") == "update" and not any(k in call_args for k in key_names):
        return f"update 类动作必须提供目标行主键（{' 或 '.join(sorted(key_names))}）"
    return ""


def _expr_vars(expr: str) -> list[str]:
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:  # noqa: BLE001
        return []
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})


def _fn_tool_name(code: str) -> str:
    return "ont_fn__" + code


def _act_tool_name(code: str) -> str:
    return "ont_action__" + code


async def build_selected_ontology_tools(codes: list[str],
                                         user_id: int | None = None) -> tuple[list[dict], set[str]]:
    """为 Agent 选中的本体函数/动作构建具体工具，返回 ``(schemas, 工具名集合)``。

    选择即授予：选中某个本体函数/动作 → 生成对应工具，运行时由 Agent 按需调用。
    hidden / deprecated 的资源不生成工具（即便被选中）。

    **P4**：带 ``user_id`` 时还会按该用户的本体权限过滤——调用者看不到的资源
    不会出现在工具列表里（连"知道它存在"都不应该）。
    """
    from app.plugin.module_ai.ontology import security as sec
    from app.plugin.module_ai.ontology import service as ont

    if not codes:
        return [], set()
    principal = await sec.load_principal(user_id) if user_id else None

    async def _allowed(kind: str, code: str) -> bool:
        if principal is None:
            return True
        ok, _ = await sec.can_view_resource(kind, code, principal)
        return ok

    funcs = {f["code"]: f for f in await ont.list_functions(None)}
    acts = {a["code"]: a for a in await ont.list_actions(None)}
    schemas: list[dict] = []
    names: set[str] = set()
    for c in codes:
        if c in funcs:
            f = funcs[c]
            if not _visible(f):
                continue
            if not await _allowed("function", c):
                continue
            # 入参：优先 parameters 声明，回退表达式变量
            props, required = _param_props(f.get("parameters"))
            if not props:
                vars_ = _expr_vars(f.get("expr") or "")
                props = {v: {"type": "number", "description": v} for v in vars_}
                required = vars_
            # 聚合/HTTP/模型形态需要对象主键作为上下文
            if (f.get("kind") or "expression") != "expression" and "object_key" not in props:
                props = {
                    "object_key": {"type": "string",
                                   "description": "对象实例主键（聚合/上下文用）"},
                    **props,
                }
            name = _fn_tool_name(c)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": _fn_description(f, c),
                        "parameters": _obj(props, required),
                    },
                }
            )
            names.add(name)
        elif c in acts:
            a = acts[c]
            if not _visible(a):
                continue
            if not await _allowed("action", c):
                continue
            props, required = _action_props(a)
            # update 类动作必须有目标行主键
            if (a.get("method") or "update") == "update":
                props = {
                    "object_key": {"type": "string", "description": "目标行的主键值（update 必填）"},
                    **props,
                }
                required = ["object_key", *required]
            name = _act_tool_name(c)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": _action_description(a, c),
                        "parameters": _obj(props, required),
                    },
                }
            )
            names.add(name)
    return schemas, names


async def run_selected_ontology_tool(name: str, args: dict, user_id: int | None = None) -> Any:
    """选定本体工具入口（计时 + 记用量，供「用量-读数」统计）。"""
    t0 = time.perf_counter()
    try:
        out = await _run_selected_ontology_tool_impl(name, args, user_id)
    except Exception as e:  # noqa: BLE001
        await _log_tool_call(name, int((time.perf_counter() - t0) * 1000), "error", str(e))
        raise
    result, err = _call_result(out)
    await _log_tool_call(name, int((time.perf_counter() - t0) * 1000), result, err)
    return out


async def _run_selected_ontology_tool_impl(name: str, args: dict, user_id: int | None = None) -> Any:
    """选中本体工具的派发（函数求值 / 动作提议）。

    **P4**：Agent 代表某个用户行事，因此这里必须按**该用户的权限**门控——
    否则 Agent 会成为绕开数据权限的后门。
    """
    from app.plugin.module_ai.ontology import security as sec
    from app.plugin.module_ai.ontology import service as ont

    args = args or {}
    principal = await sec.load_principal(user_id) if user_id else None
    if name.startswith("ont_fn__"):
        code = name[len("ont_fn__") :]
        funcs = await ont.list_functions(None)
        f = next((x for x in funcs if x.get("code") == code), None)
        if not f:
            return {"error": f"本体函数 {code} 不存在"}
        if not _visible(f):
            return {"error": f"本体函数 {code} 已隐藏或弃用，不可调用"}
        if principal is not None:
            ok_f, why_f = await sec.can_view_resource("function", code, principal)
            if not ok_f:
                return {"error": f"无权调用本体函数 {code}：{why_f}"}
        object_key = str(args.get("object_key") or "")
        call_args = {k: v for k, v in args.items() if k != "object_key"}
        r = await ont.run_ontology_function(code, call_args, object_key)
        if not r.get("ok"):
            return {"error": r.get("msg") or "函数执行失败"}
        return {"code": code, "name": r.get("name"), "kind": r.get("kind"),
                "result": r.get("value"), "outputs": r.get("outputs")}
    if name.startswith("ont_action__"):
        code = name[len("ont_action__") :]
        return await run_ontology_tool("propose_ontology_action",
                                       {"code": code, "args": args}, user_id)
    return {"error": f"未知本体工具：{name}"}


async def ontology_catalog_text(max_objects: int = 20) -> str:
    """本体能力清单文本（对象 → 函数/动作），供注入 Agent 上下文。

    只列可暴露给 Agent 的资源（排除 hidden / deprecated），并使用 tool_description。
    """
    try:
        from app.plugin.module_ai.ontology import service as ont

        objs = await ont.list_objects()
        lines: list[str] = []
        for o in objs[:max_objects]:
            if not _visible(o):
                continue
            funcs = [f for f in await ont.list_functions(o["code"]) if _visible(f)]
            acts = [a for a in await ont.list_actions(o["code"]) if _visible(a)]
            if not funcs and not acts:
                continue
            parts = []
            if funcs:
                parts.append(
                    "函数：" + "、".join(f"{f.get('code')}" for f in funcs[:8])
                )
            if acts:
                parts.append(
                    "动作：" + "、".join(f"{a.get('code')}" for a in acts[:8])
                )
            lines.append(f"- {o.get('name') or o.get('code')}（{o.get('code')}）：{'；'.join(parts)}")
        if not lines:
            return ""
        return (
            "## 可用本体能力（可按需调用）\n"
            "以下为本体对象及其可调用的函数/动作；命中相关问题时用 run_ontology_function / "
            "propose_ontology_action 调用：\n" + "\n".join(lines)
        )
    except Exception:  # noqa: BLE001
        return ""
