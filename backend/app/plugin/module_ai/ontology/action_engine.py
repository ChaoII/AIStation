"""动作引擎：让「提交条件 / 编辑规则 / 副作用」真正生效。

对齐官方 `action-types` 文档：

- **Submission criteria（提交条件）**：决定动作能否被提交。支持三类条件模板
  （当前用户 / 参数 / 执行上下文）、单值与多值算子，以及可嵌套的 AND/OR/NOT；
  根级条件各自带**失败信息**，未通过时把该信息返回给调用方。
- **Rules（规则）**：把参数转换成对 Ontology 的编辑。赋值来源可为
  参数 / 静态值 / 当前用户 / 当前时间 / 对象参数的属性。
- **Side effects（副作用）**：通知与 Webhook。

本模块是**纯函数**（不做 I/O、不连库）：需要读对象参数属性时由调用方注入 ``resolver``，
执行编辑与发副作用由 ``service`` 负责。这样便于单测，也避免与 service 形成循环依赖。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 常量：与官方文档逐条对齐
# ---------------------------------------------------------------------------
SINGLE_OPS = ("is", "is_not", "matches", "lt", "lte", "gt", "gte", "is_empty", "is_not_empty")
MULTI_OPS = ("includes", "includes_any", "is_included_in", "each_is", "each_is_not")
LOGIC_OPS = ("and", "or", "not")
ALL_OPS = SINGLE_OPS + MULTI_OPS + LOGIC_OPS

# 条件模板（官方三类）
LEFT_KINDS = ("parameter", "current_user", "current_user_group", "execution_context", "static")
RIGHT_KINDS = ("static", "parameter", "current_user", "current_user_group", "none")

# 赋值来源（官方四种 + 对象参数属性）
ASSIGN_SOURCES = ("parameter", "static", "current_user", "current_time",
                  "object_parameter_property")

# 规则类型（官方本体规则里我们支持的部分）
RULE_TYPES = ("modify_object", "create_object", "delete_object")

# 副作用类型
SIDE_EFFECT_TYPES = ("notification", "webhook")

_MAX_WEBHOOK_BODY = 20000


@dataclass
class ActorContext:
    """动作的提交者上下文。"""

    user_id: int = 0
    user_name: str = ""
    role_ids: list[int] = field(default_factory=list)
    role_codes: list[str] = field(default_factory=list)
    is_scenario: bool = False

    def groups(self) -> list[str]:
        """用户所属组/角色（官方：group IDs，含直接与继承成员）。"""
        return [str(x) for x in (list(self.role_codes) + list(self.role_ids))]


# ---------------------------------------------------------------------------
# 取值
# ---------------------------------------------------------------------------
def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def _as_num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) == 0
    return False


def resolve_value(
    spec: Any,
    ctx: ActorContext,
    params: dict,
    resolver: Callable[[str, str], Any] | None = None,
) -> Any:
    """解析一个取值描述。

    ``spec`` 支持三种写法：
    - 字面量（字符串/数字/布尔/列表）→ 直接当静态值
    - ``{"kind": "static", "value": x}`` → 静态值
    - ``{"kind": "parameter"|"current_user"|"current_user_group"|"execution_context",
        "value": "<参数名>", "property": "<属性名>"}``
    """
    if spec is None:
        return None
    if not isinstance(spec, dict):
        return spec
    kind = str(spec.get("kind") or "static")
    if kind == "static":
        return spec.get("value")
    if kind == "none":
        return None
    if kind == "current_user":
        return str(ctx.user_id) if ctx.user_id else ""
    if kind == "current_user_group":
        return ctx.groups()
    if kind == "execution_context":
        # 官方：判断动作是否在 Ontology Scenario 中被评估。
        # value 可指定具体字段（如 is_scenario），不指定则返回整个上下文。
        name = str(spec.get("value") or "").strip()
        ctxmap = {"is_scenario": bool(ctx.is_scenario)}
        return ctxmap[name] if name in ctxmap else ctxmap
    if kind == "parameter":
        name = str(spec.get("value") or "")
        raw = params.get(name)
        prop = spec.get("property")
        if prop and resolver is not None:
            # 对象参数取属性：交给调用方去实例层解析
            return resolver(name, str(prop))
        return raw
    return None


# ---------------------------------------------------------------------------
# 条件与算子
# ---------------------------------------------------------------------------
def _apply_operator(op: str, left: Any, right: Any) -> bool:
    if op == "is":
        return str(left) == str(right) if left is not None and right is not None else left == right
    if op == "is_not":
        return not (str(left) == str(right) if left is not None and right is not None else left == right)
    if op == "matches":
        try:
            return re.search(str(right), "" if left is None else str(left)) is not None
        except re.error:
            return False
    if op in ("lt", "lte", "gt", "gte"):
        a, b = _as_num(left), _as_num(right)
        if a is None or b is None:
            return False
        return {"lt": a < b, "lte": a <= b, "gt": a > b, "gte": a >= b}[op]
    if op == "is_empty":
        return _is_empty(left)
    if op == "is_not_empty":
        return not _is_empty(left)
    if op in ("includes", "each_is", "each_is_not"):
        vals = _as_list(left)
        rights = _as_list(right)
        if op == "includes":
            return any(str(v) == str(right) or str(v) in [str(x) for x in rights] for v in vals)
        if op == "each_is":
            return all(str(v) == str(right) for v in vals) if vals else False
        return all(str(v) != str(right) for v in vals) if vals else False
    if op == "includes_any":
        lv = {str(x) for x in _as_list(left)}
        rv = {str(x) for x in _as_list(right)}
        return bool(lv & rv)
    if op == "is_included_in":
        return str(left) in {str(x) for x in _as_list(right)}
    return False


def evaluate_node(
    node: dict,
    ctx: ActorContext,
    params: dict,
    resolver: Callable[[str, str], Any] | None = None,
    trace: list | None = None,
) -> bool:
    """递归评估一个条件或逻辑组。"""
    if not isinstance(node, dict):
        return True
    op = str(node.get("operator") or "").strip()
    msg = str(node.get("failure_message") or node.get("message") or "")

    # 逻辑组
    if op in LOGIC_OPS or "children" in node or "conditions" in node:
        children = node.get("children") or node.get("conditions") or []
        results = [evaluate_node(c, ctx, params, resolver, trace) for c in children]
        if op == "or":
            ok = any(results) if results else False
        elif op == "not":
            ok = not (results[0] if results else False)
        else:  # and（默认）
            ok = all(results) if results else False
        if trace is not None:
            trace.append({"kind": "group", "operator": op or "and", "ok": ok,
                          "failure_message": msg, "children": len(children)})
        return ok

    # 单条件
    left = resolve_value(node.get("left"), ctx, params, resolver)
    right = resolve_value(node.get("right"), ctx, params, resolver)
    ok = _apply_operator(op, left, right)
    if trace is not None:
        trace.append({
            "kind": "condition", "operator": op, "ok": ok,
            "left": _preview(left), "right": _preview(right),
            "failure_message": msg,
        })
    return ok


def _preview(v: Any) -> Any:
    """给试运行展示用：截断长值。"""
    if isinstance(v, (list, tuple)):
        return [_preview(x) for x in list(v)[:10]]
    s = "" if v is None else str(v)
    return s if len(s) <= 60 else s[:57] + "…"


def evaluate_criteria(
    criteria: list | None,
    ctx: ActorContext,
    params: dict,
    resolver: Callable[[str, str], Any] | None = None,
    with_trace: bool = False,
) -> dict:
    """评估提交条件。

    返回 ``{"ok": bool, "failures": [失败信息], "trace": [...]}``。
    根级每个条件/逻辑组各自带 failure_message，未通过时收集起来。
    """
    items = criteria or []
    failures: list[str] = []
    trace: list = []
    for i, node in enumerate(items):
        per: list = []
        ok = evaluate_node(node, ctx, params, resolver, per)
        if with_trace:
            trace.append({"index": i, "ok": ok, "nodes": per})
        if not ok:
            msg = ""
            if isinstance(node, dict):
                msg = str(node.get("failure_message") or node.get("message") or "")
            failures.append(msg or f"第 {i + 1} 条提交条件未满足")
    return {"ok": not failures, "failures": failures, "trace": trace}


# ---------------------------------------------------------------------------
# 规则 → 编辑计划
# ---------------------------------------------------------------------------
def plan_rules(rules: list | None, ctx: ActorContext, params: dict,
               resolver: Callable[[str, str], Any] | None = None) -> dict:
    """把规则解析成具体的编辑计划（不执行）。

    返回 ``{"edits": [...], "errors": [...], "warnings": [...]}``；
    每个 edit 形如 ``{"rule": "modify_object", "assignments": {列: 值}}``。
    """
    edits: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    for i, r in enumerate(rules or []):
        if not isinstance(r, dict):
            errors.append(f"第 {i + 1} 条规则不是对象")
            continue
        rtype = str(r.get("type") or "").strip()
        if rtype not in RULE_TYPES:
            errors.append(f"第 {i + 1} 条规则类型不支持：{rtype or '(空)'}")
            continue
        assigns: dict[str, Any] = {}
        for a in r.get("assignments") or []:
            if not isinstance(a, dict):
                continue
            prop = str(a.get("property") or a.get("column") or "").strip()
            if not prop:
                warnings.append(f"第 {i + 1} 条规则有一项缺少 property，已跳过")
                continue
            src = str(a.get("source") or "parameter").strip()
            if src not in ASSIGN_SOURCES:
                errors.append(f"第 {i + 1} 条规则的赋值来源不支持：{src}")
                continue
            if src == "parameter":
                pname = str(a.get("value") or a.get("parameter") or prop)
                if pname not in params:
                    warnings.append(f"参数 {pname} 未提供，属性 {prop} 不参与本次编辑")
                    continue
                assigns[prop] = params[pname]
            elif src == "static":
                assigns[prop] = a.get("value")
            elif src == "current_user":
                assigns[prop] = ctx.user_name or str(ctx.user_id or "")
            elif src == "current_time":
                assigns[prop] = _now_str()
            elif src == "object_parameter_property":
                ref = str(a.get("parameter") or a.get("value") or "")
                sub = str(a.get("object_property") or a.get("property_of") or "").strip()
                if not ref or not sub:
                    errors.append(f"第 {i + 1} 条规则的对象参数属性赋值缺少 parameter/object_property")
                    continue
                if resolver is None:
                    warnings.append(f"无法解析对象参数 {ref} 的属性 {sub}")
                    continue
                val = resolver(ref, sub)
                if val is None:
                    warnings.append(f"对象参数 {ref} 的属性 {sub} 取不到值，已跳过")
                    continue
                assigns[prop] = val
        edits.append({"rule": rtype, "index": i, "assignments": assigns,
                      "object_key": r.get("object_key") or r.get("object_parameter")})
    return {"edits": edits, "errors": errors, "warnings": warnings}


def _now_str() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 副作用 → 执行计划
# ---------------------------------------------------------------------------
def plan_side_effects(effects: list | None, ctx: ActorContext, params: dict,
                      resolver: Callable[[str, str], Any] | None = None) -> dict:
    """解析副作用计划（不发送）。"""
    out: list[dict] = []
    errors: list[str] = []
    for i, e in enumerate(effects or []):
        if not isinstance(e, dict):
            errors.append(f"第 {i + 1} 条副作用不是对象")
            continue
        etype = str(e.get("type") or "").strip()
        if etype not in SIDE_EFFECT_TYPES:
            errors.append(f"第 {i + 1} 条副作用类型不支持：{etype or '(空)'}")
            continue
        timing = str(e.get("timing") or "after").strip()
        if timing not in ("before", "after"):
            timing = "after"
        if etype == "notification":
            recipients = [int(x) for x in _as_list(e.get("recipients")) if str(x).isdigit()]
            out.append({
                "type": "notification", "timing": timing,
                "title": _interp(str(e.get("title") or "本体动作通知"), params, ctx),
                "content": _interp(str(e.get("content") or ""), params, ctx),
                "recipients": recipients,
                "module": str(e.get("module") or "ai"),
                "module_id": e.get("module_id"),
            })
        else:
            url = str(e.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                errors.append(f"第 {i + 1} 条 Webhook 的 URL 必须是 http/https")
                continue
            method = str(e.get("method") or "POST").upper()
            if method not in ("POST", "PUT", "PATCH", "GET"):
                errors.append(f"第 {i + 1} 条 Webhook 的方法不支持：{method}")
                continue
            body = e.get("body")
            if isinstance(body, dict):
                body = {k: _interp(str(v), params, ctx) for k, v in body.items()}
            out.append({
                "type": "webhook", "timing": timing, "url": url, "method": method,
                "headers": e.get("headers") or {},
                "body": body or {"params": params},
                "timeout": min(max(float(e.get("timeout") or 5), 0.5), 30),
                "blocking": bool(e.get("blocking", False)),
            })
    return {"effects": out, "errors": errors}


def _interp(text: str, params: dict, ctx: ActorContext) -> str:
    """把 ``{{参数名}}`` / ``{{当前用户}}`` 替换成实际值。"""
    def sub(m: re.Match) -> str:
        key = m.group(1).strip()
        if key in ("当前用户", "current_user"):
            return ctx.user_name or str(ctx.user_id or "")
        if key in ("当前时间", "current_time"):
            return _now_str()
        v = params.get(key)
        return "" if v is None else str(v)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", sub, text or "")


# ---------------------------------------------------------------------------
# 校验（供编辑期与工作副本审核使用）
# ---------------------------------------------------------------------------
def validate_criteria(criteria: list | None, param_keys: set[str]) -> list[str]:
    errors: list[str] = []
    for i, node in enumerate(criteria or []):
        errors += _validate_node(node, param_keys, f"提交条件第 {i + 1} 条")
    return errors


def _validate_node(node: Any, param_keys: set[str], where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(node, dict):
        return [f"{where}：不是对象"]
    op = str(node.get("operator") or "").strip()
    if op in LOGIC_OPS or "children" in node or "conditions" in node:
        if op and op not in LOGIC_OPS:
            errs.append(f"{where}：逻辑运算符不支持 {op}")
        children = node.get("children") or node.get("conditions") or []
        if not isinstance(children, list) or not children:
            errs.append(f"{where}：逻辑组没有子条件")
        for j, c in enumerate(children or []):
            errs += _validate_node(c, param_keys, f"{where} > 子条件 {j + 1}")
        return errs
    if op not in ALL_OPS:
        errs.append(f"{where}：运算符不支持 {op or '(空)'}")
    left = node.get("left")
    if not isinstance(left, dict) or not str(left.get("kind") or ""):
        errs.append(f"{where}：缺少 left.kind")
    elif str(left.get("kind")) not in LEFT_KINDS:
        errs.append(f"{where}：left.kind 不支持 {left.get('kind')}")
    elif str(left.get("kind")) == "parameter":
        name = str(left.get("value") or "")
        if not name:
            errs.append(f"{where}：left 引用了空参数名")
        elif param_keys and name not in param_keys:
            errs.append(f"{where}：left 引用了未定义的参数 {name}")
    right = node.get("right")
    if isinstance(right, dict):
        rk = str(right.get("kind") or "")
        if rk and rk not in RIGHT_KINDS:
            errs.append(f"{where}：right.kind 不支持 {rk}")
        if rk == "parameter":
            name = str(right.get("value") or "")
            if param_keys and name and name not in param_keys:
                errs.append(f"{where}：right 引用了未定义的参数 {name}")
    return errs


def validate_rules(rules: list | None, param_keys: set[str]) -> list[str]:
    errors: list[str] = []
    seen_types: list[str] = []
    for i, r in enumerate(rules or []):
        where = f"规则第 {i + 1} 条"
        if not isinstance(r, dict):
            errors.append(f"{where}：不是对象")
            continue
        rtype = str(r.get("type") or "")
        if rtype not in RULE_TYPES:
            errors.append(f"{where}：类型不支持 {rtype or '(空)'}（可用：{'、'.join(RULE_TYPES)}）")
            continue
        seen_types.append(rtype)
        for j, a in enumerate(r.get("assignments") or []):
            if not isinstance(a, dict):
                errors.append(f"{where} 赋值 {j + 1}：不是对象")
                continue
            if not str(a.get("property") or a.get("column") or "").strip():
                errors.append(f"{where} 赋值 {j + 1}：缺少 property")
            src = str(a.get("source") or "parameter")
            if src not in ASSIGN_SOURCES:
                errors.append(f"{where} 赋值 {j + 1}：来源不支持 {src}")
            elif src == "parameter":
                pname = str(a.get("value") or a.get("parameter") or "")
                if param_keys and pname and pname not in param_keys:
                    errors.append(f"{where} 赋值 {j + 1}：引用了未定义的参数 {pname}")
    # 官方限制：同一次提交里对象不能创建两次
    if seen_types.count("create_object") > 1:
        errors.append("同一次提交里不允许创建两次对象（官方限制）")
    return errors


def validate_side_effects(effects: list | None) -> list[str]:
    errors: list[str] = []
    for i, e in enumerate(effects or []):
        where = f"副作用第 {i + 1} 条"
        if not isinstance(e, dict):
            errors.append(f"{where}：不是对象")
            continue
        etype = str(e.get("type") or "")
        if etype not in SIDE_EFFECT_TYPES:
            errors.append(f"{where}：类型不支持 {etype or '(空)'}（可用：notification、webhook）")
            continue
        if etype == "notification":
            if not _as_list(e.get("recipients")):
                errors.append(f"{where}：通知未指定收件人（recipients）")
        else:
            url = str(e.get("url") or "")
            if not url.lower().startswith(("http://", "https://")):
                errors.append(f"{where}：Webhook 的 URL 必须是 http/https")
    return errors
