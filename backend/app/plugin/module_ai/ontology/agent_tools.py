"""本体能力 → Agent 工具（阶段1：把本体函数/动作变成 Agent 可按需调用的工具）。

以 OpenAI function schema + 派发器的形式提供，由 agent 运行时直接并入工具集
（``agno_tools.dynamic.build_dynamic_tools`` 消费），因此无需在 ``ai_tools`` 目录另建行。

能力模型见 ``docs/ai-agent-capability-model.md``：
- 本体函数 Function → 可运行的只读计算（表达式求值）
- 对象动作 Action  → 变更类，仅「提议」，由用户确认后执行
- 对象清单/接地   → 注入 Agent 上下文，供其决定按需调用哪个本体能力
"""
from __future__ import annotations

import ast
import operator as op
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


async def run_ontology_tool(name: str, args: dict, user_id: int | None = None) -> Any:
    """本体工具派发。"""
    from app.plugin.module_ai.ontology import service as ont

    args = args or {}
    if name == "list_ontology":
        obj_code = (args.get("object_code") or "").strip() or None
        objs = await ont.list_objects()
        if obj_code:
            objs = [o for o in objs if o.get("code") == obj_code]
        out = []
        for o in objs[:50]:
            funcs = await ont.list_functions(o["code"])
            acts = await ont.list_actions(o["code"])
            out.append(
                {
                    "object": o.get("code"),
                    "name": o.get("name"),
                    "functions": [
                        {
                            "code": f.get("code"),
                            "name": f.get("name"),
                            "expr": f.get("expr") or "",
                            "description": f.get("description") or "",
                        }
                        for f in funcs
                    ],
                    "actions": [
                        {
                            "code": a.get("code"),
                            "name": a.get("name"),
                            "approval": a.get("approval"),
                            "description": a.get("description") or "",
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
        funcs = await ont.list_functions(None)
        f = next((x for x in funcs if x.get("code") == code), None)
        if not f:
            return {"error": f"本体函数 {code} 不存在"}
        expr = (f.get("expr") or "").strip()
        if not expr:
            return {"error": f"本体函数 {code} 未定义表达式"}
        try:
            val = _safe_eval(expr, args.get("args") or {})
        except Exception as e:  # noqa: BLE001
            return {"error": f"函数求值失败：{e}"}
        return {"code": code, "name": f.get("name"), "expr": expr, "result": val}

    if name == "propose_ontology_action":
        code = (args.get("code") or "").strip()
        if not code:
            return {"error": "缺少动作编码"}
        acts = await ont.list_actions(None)
        a = next((x for x in acts if x.get("code") == code), None)
        if not a:
            return {"error": f"对象动作 {code} 不存在"}
        tgt = a.get("target_table") or "—"
        method = a.get("method") or "update"
        return {
            "__action__": {
                "type": "confirm",
                "api": "ontologyAction",
                "label": f"执行对象动作「{a.get('name') or code}」（{tgt}.{method}）",
                "payload": {"code": code, "args": args.get("args") or {}},
            }
        }

    return {"error": f"未知本体工具：{name}"}


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


async def build_selected_ontology_tools(codes: list[str]) -> tuple[list[dict], set[str]]:
    """为 Agent 选中的本体函数/动作构建具体工具，返回 ``(schemas, 工具名集合)``。

    选择即授予：选中某个本体函数/动作 → 生成对应工具，运行时由 Agent 按需调用。
    """
    from app.plugin.module_ai.ontology import service as ont

    if not codes:
        return [], set()
    funcs = {f["code"]: f for f in await ont.list_functions(None)}
    acts = {a["code"]: a for a in await ont.list_actions(None)}
    schemas: list[dict] = []
    names: set[str] = set()
    for c in codes:
        if c in funcs:
            f = funcs[c]
            vars_ = _expr_vars(f.get("expr") or "")
            props = {v: {"type": "number", "description": v} for v in vars_}
            name = _fn_tool_name(c)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": f"本体函数：{f.get('name') or c}（{f.get('expr')}）",
                        "parameters": _obj(props, vars_),
                    },
                }
            )
            names.add(name)
        elif c in acts:
            a = acts[c]
            props: dict = {}
            for fld in a.get("input_schema") or []:
                if isinstance(fld, dict) and fld.get("name"):
                    props[fld["name"]] = {"type": fld.get("type") or "string"}
            name = _act_tool_name(c)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": (
                            f"对象动作：{a.get('name') or c}"
                            f"（{a.get('target_table') or '—'}.{a.get('method') or 'update'}）"
                        ),
                        "parameters": _obj(props),
                    },
                }
            )
            names.add(name)
    return schemas, names


async def run_selected_ontology_tool(name: str, args: dict, user_id: int | None = None) -> Any:
    """选中本体工具的派发（函数求值 / 动作提议）。"""
    from app.plugin.module_ai.ontology import service as ont

    args = args or {}
    if name.startswith("ont_fn__"):
        code = name[len("ont_fn__") :]
        funcs = await ont.list_functions(None)
        f = next((x for x in funcs if x.get("code") == code), None)
        if not f:
            return {"error": f"本体函数 {code} 不存在"}
        try:
            return {"code": code, "result": _safe_eval(f.get("expr") or "", args)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"函数求值失败：{e}"}
    if name.startswith("ont_action__"):
        code = name[len("ont_action__") :]
        return await run_ontology_tool("propose_ontology_action", {"code": code, "args": args})
    return {"error": f"未知本体工具：{name}"}


async def ontology_catalog_text(max_objects: int = 20) -> str:
    """本体能力清单文本（对象 → 函数/动作），供注入 Agent 上下文。"""
    try:
        from app.plugin.module_ai.ontology import service as ont

        objs = await ont.list_objects()
        lines: list[str] = []
        for o in objs[:max_objects]:
            funcs = await ont.list_functions(o["code"])
            acts = await ont.list_actions(o["code"])
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
