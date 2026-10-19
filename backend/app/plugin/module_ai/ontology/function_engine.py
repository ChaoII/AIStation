"""函数引擎：让本体函数从「四则运算」升级为可用的 Logic 资产。

设计取舍（重要）
----------------
官方函数是 TypeScript / Python 函数，能读本体、调模型、调外部服务、写回本体。
我们**不建代码沙箱**（§9 已列为非目标），而是做**声明式函数**：用受控的表达式 +
四种函数形态覆盖同样的用途。

四种形态
--------
1. ``expression`` —— 受控表达式求值。在原四则运算基础上增加**白名单内置函数**
   （abs/min/max/round/len/concat/coalesce/iif/percent/…）与日期运算。
2. ``aggregate``  —— 沿关系链在关联对象上聚合（复用派生属性的引擎，9 种聚合）。
3. ``http``       —— 调外部 REST API，把响应按路径取出作为返回值。
4. ``model``      —— 调本平台已登记的模型（连接「模型配置」），把响应文本取回。

与官方概念的对应
----------------
- ``inputs`` / ``outputs`` → 官方 input-output-types；inputs 也直接生成 Agent 工具的入参 schema
- 输入来源里的 ``object_property`` → 官方 functions-on-objects（以对象实例为上下文）
- ``http`` → 官方 external-sources
- ``model`` → 官方 functions-on-models

本模块**不做数据库访问**：需要读本体或调模型时由调用方注入回调。
"""
from __future__ import annotations

import ast
import json
import math
import operator as op
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ONT_FUNCTION_KINDS = ("expression", "aggregate", "http", "model")
ONT_INPUT_SOURCES = ("parameter", "object_property", "static", "current_user", "current_time")
ONT_VALUE_TYPES = ("string", "number", "integer", "boolean", "date", "datetime", "object_ref", "list")

ONT_AGGREGATIONS = ("count", "sum", "avg", "min", "max", "first", "last",
                    "collect_list", "collect_set")

KIND_LABEL = {
    "expression": "表达式",
    "aggregate": "关联聚合",
    "http": "外部服务",
    "model": "模型调用",
}

_MAX_HTTP_BODY = 20000


# ---------------------------------------------------------------------------
# 受控表达式求值（在原基础上增加白名单内置函数）
# ---------------------------------------------------------------------------
_BINOPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Mod: op.mod, ast.Pow: op.pow, ast.FloorDiv: op.floordiv,
}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg, ast.Not: op.not_}
_CMP = {ast.Eq: op.eq, ast.NotEq: op.ne, ast.Lt: op.lt, ast.LtE: op.le,
        ast.Gt: op.gt, ast.GtE: op.ge}


def _iif(cond: Any, a: Any, b: Any) -> Any:
    return a if cond else b


def _coalesce(*args: Any) -> Any:
    return next((x for x in args if x is not None and x != ""), None)


def _percent(part: Any, total: Any) -> Any:
    try:
        t = float(total)
        return (float(part) / t * 100) if t else None
    except (TypeError, ValueError):
        return None


def _to_ts(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def _days_between(a: Any, b: Any) -> Any:
    ta, tb = _to_ts(a), _to_ts(b)
    if not ta or not tb:
        return None
    return (ta - tb).total_seconds() / 86400


def _concat(*args: Any) -> str:
    return "".join("" if x is None else str(x) for x in args)


#: 白名单内置函数。**只能调这些**，表达式里无法触达任何其它对象。
BUILTINS: dict[str, Any] = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len,
    "sum": sum, "any": any, "all": all, "pow": pow,
    "int": lambda x: int(float(x)), "float": float, "str": str, "bool": bool,
    "floor": math.floor, "ceil": math.ceil, "sqrt": math.sqrt,
    "lower": lambda s: str(s).lower(),
    "upper": lambda s: str(s).upper(),
    "trim": lambda s: str(s).strip(),
    "concat": _concat,
    "coalesce": _coalesce,
    "iif": _iif,
    "percent": _percent,
    "avg": lambda *a: (sum(float(x) for x in a) / len(a)) if a else None,
    "contains": lambda hay, needle: str(needle) in str(hay),
    "startswith": lambda s, p: str(s).startswith(str(p)),
    "endswith": lambda s, p: str(s).endswith(str(p)),
    "days_between": _days_between,
    "now": lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "today": lambda: datetime.now().strftime("%Y-%m-%d"),
    "regex_match": lambda s, p: bool(re.search(str(p), str(s or ""))),
    "regex_extract": lambda s, p: (re.search(str(p), str(s or "")).group(0)
                                   if re.search(str(p), str(s or "")) else None),
    "json_get": lambda s, path: dig(json.loads(s) if isinstance(s, str) else s, str(path)),
}


class ExprError(ValueError):
    """表达式错误（未知变量 / 未知函数 / 不支持的语法）。"""


def safe_eval(expr: str, variables: dict) -> Any:
    """受控表达式求值：算术/比较/布尔 + 白名单内置函数。无属性访问、无任意调用。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"表达式语法错误：{e.msg}") from e

    def _ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            if node.id in BUILTINS:
                raise ExprError(f"{node.id} 是函数，需要写成 {node.id}(...)")
            raise ExprError(f"未知变量：{node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ExprError("只允许调用内置函数")
            fn = BUILTINS.get(node.func.id)
            if fn is None:
                raise ExprError(f"未知函数：{node.func.id}（可用：{'、'.join(sorted(BUILTINS))}）")
            if node.keywords:
                raise ExprError("内置函数不支持关键字参数")
            return fn(*[_ev(a) for a in node.args])
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
        if isinstance(node, ast.IfExp):
            return _ev(node.body) if _ev(node.test) else _ev(node.orelse)
        if isinstance(node, ast.List):
            return [_ev(e) for e in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(_ev(e) for e in node.elts)
        if isinstance(node, ast.Subscript):
            base = _ev(node.value)
            idx = _ev(node.slice)
            try:
                return base[idx]
            except Exception as e:  # noqa: BLE001
                raise ExprError(f"下标取值失败：{e}") from e
        raise ExprError("不支持的表达式")

    return _ev(tree)


def expr_vars(expr: str) -> list[str]:
    """表达式里引用的变量名（排除内置函数名）。"""
    try:
        tree = ast.parse(expr or "", mode="eval")
    except SyntaxError:
        return []
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id not in BUILTINS:
            out.add(n.id)
    return sorted(out)


def expr_calls(expr: str) -> list[str]:
    """表达式里调用的函数名（用于校验）。"""
    try:
        tree = ast.parse(expr or "", mode="eval")
    except SyntaxError:
        return []
    return sorted({n.func.id for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)})


# ---------------------------------------------------------------------------
# 取值路径 / 模板
# ---------------------------------------------------------------------------
_PATH_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def dig(obj: Any, path: str | None, default: Any = None) -> Any:
    """按 ``a.b[0].c`` 形式的路径取值（给 HTTP / 模型响应用）。"""
    if not path:
        return obj
    cur = obj
    for m in _PATH_RE.finditer(path):
        if m.group(1) is not None:
            key = m.group(1)
            if isinstance(cur, dict):
                cur = cur.get(key, default)
            else:
                return default
        else:
            idx = int(m.group(2))
            if isinstance(cur, list) and -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return default
    return cur


def interp(text: str, values: dict, ctx: FunctionContext | None = None) -> str:
    """把 ``{{名字}}`` 替换成实际值（支持 ``{{当前用户}}`` / ``{{当前时间}}``）。"""
    def sub(m: re.Match) -> str:
        key = m.group(1).strip()
        if key in ("当前用户", "current_user"):
            return (ctx.user_name or str(ctx.user_id or "")) if ctx else ""
        if key in ("当前时间", "current_time"):
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        v = values.get(key)
        return "" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", sub, text or "")


# ---------------------------------------------------------------------------
# 输入准备
# ---------------------------------------------------------------------------
@dataclass
class FunctionContext:
    """函数执行上下文。"""

    object_code: str = ""
    object_key: str = ""
    user_id: int = 0
    user_name: str = ""
    object_props: dict = field(default_factory=dict)


def _coerce(value: Any, decl_type: str, forced: bool = False) -> tuple[Any, str]:
    """按声明的类型把取值转成合适的 Python 类型。

    这一步不能省：界面输入框、Agent 工具调用传进来的都是**字符串**，
    不转换的话 ``online / total`` 会变成 ``'8' / '10'`` 直接抛 TypeError。
    返回 ``(值, 错误信息)``；``forced`` 表示调用方显式传了值（转换失败要报错）。

    **未声明 type 时不做任何转换**（原样透传）——老函数只写了 expr、没声明类型，
    若一律按 string 处理会把数字变成字符串，算术直接崩。
    """
    t = (decl_type or "").strip().lower()
    if not t or value is None or value == "":
        return value, ""
    if t == "string":
        return value if isinstance(value, str) else str(value), ""
    if t in ("number", "integer"):
        if isinstance(value, bool):
            return value, ""
        if isinstance(value, (int, float)):
            num: float | int = value
        else:
            s = str(value).strip()
            try:
                f = float(s)
            except ValueError:
                return (None, f"取值 {value!r} 不是合法数字") if forced else (value, "")
            num = int(f) if f.is_integer() else f
        if t == "integer":
            return int(num), ""
        return num, ""
    if t == "boolean":
        if isinstance(value, bool):
            return value, ""
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "y", "是"):
            return True, ""
        if s in ("false", "0", "no", "n", "否"):
            return False, ""
        return (None, f"取值 {value!r} 不是合法布尔值") if forced else (value, "")
    if t in ("list", "object_ref"):
        if isinstance(value, str):
            try:
                return json.loads(value), ""
            except Exception:  # noqa: BLE001
                return (value.split(","), "") if t == "list" else (value, "")
        return value, ""
    if t in ("date", "datetime"):
        return value, ""
    return value, ""


def effective_parameters(fn: dict) -> list[dict]:
    """函数实际生效的入参声明。

    老函数只写了 ``expr``、没声明 ``parameters``。此时按表达式里的变量推断为
    ``number`` —— 这与 Agent 工具 schema 的既有回退（``_expr_vars`` → number）
    保持**一致**：schema 对外宣称是 number，运行时就必须按 number 收值，
    否则 Agent 传字符串进来会算不了数。
    """
    declared = [p for p in (fn.get("parameters") or []) if isinstance(p, dict) and p.get("key")]
    if declared:
        return declared
    if str(fn.get("kind") or "expression") != "expression":
        return []
    return [{"key": v, "name": v, "type": "number", "required": True, "inferred": True}
            for v in expr_vars(fn.get("expr") or "")]


async def prepare_inputs(fn: dict, args: dict, ctx: FunctionContext,
                         object_loader: Callable[[str, str], Awaitable[dict]] | None = None) -> dict:
    """按声明的 inputs 准备实际入参（含**按声明类型转换**）。

    输入来源：
    - ``parameter``（默认）：取调用方传入的同名参数
    - ``object_property``：取对象上下文里该属性的值（自动加载对象）
    - ``static``：固定值
    - ``current_user`` / ``current_time``：上下文值
    """
    args = args or {}
    declared = effective_parameters(fn)
    values: dict[str, Any] = {}
    errors: list[str] = []

    need_props = any(
        isinstance(p, dict) and str(p.get("source") or "parameter") == "object_property"
        for p in declared
    )
    props = dict(ctx.object_props or {})
    if need_props and not props and ctx.object_code and ctx.object_key and object_loader:
        try:
            loaded = await object_loader(ctx.object_code, ctx.object_key)
            if isinstance(loaded, dict):
                props = loaded
        except Exception:  # noqa: BLE001
            props = {}

    for p in declared:
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").strip()
        if not key:
            continue
        src = str(p.get("source") or "parameter")
        dtype = str(p.get("type") or "")
        if src == "object_property":
            raw = props.get(str(p.get("object_property") or key), p.get("default"))
        elif src == "static":
            raw = p.get("default")
        elif src == "current_user":
            raw = ctx.user_name or str(ctx.user_id or "")
        elif src == "current_time":
            raw = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            raw = args.get(key, p.get("default"))
        val, err = _coerce(raw, dtype, forced=(src == "parameter" and key in args))
        if err:
            errors.append(f"入参「{p.get('name') or key}」{err}")
        elif val is not None or raw is None:
            values[key] = val

    # 未声明但调用方传了的参数也带上（兼容老函数：只声明了 expr 变量）
    for k, v in args.items():
        values.setdefault(k, v)
    if errors:
        raise ExprError("；".join(errors))
    return values


def missing_required(fn: dict, values: dict) -> list[str]:
    out = []
    for p in effective_parameters(fn):
        if not isinstance(p, dict):
            continue
        if p.get("required") and str(p.get("source") or "parameter") == "parameter":
            v = values.get(str(p.get("key") or ""))
            if v is None or v == "":
                out.append(str(p.get("label") or p.get("key")))
    return out


def coerce_outputs(fn: dict, value: Any) -> Any:
    """按声明的 outputs 整理返回值。

    声明了多个 output 时，把结果包装成 dict（单个 output 直接返回该值）。
    """
    outs = [o for o in (fn.get("outputs") or []) if isinstance(o, dict) and o.get("key")]
    if not outs:
        return value
    if len(outs) == 1:
        return {outs[0]["key"]: value}
    return {"value": value}


# ---------------------------------------------------------------------------
# 各形态的执行
# ---------------------------------------------------------------------------
async def run_function(
    fn: dict,
    args: dict,
    ctx: FunctionContext | None = None,
    *,
    object_loader: Callable[[str, str], Awaitable[dict]] | None = None,
    aggregate_runner: Callable[[dict, dict], Awaitable[Any]] | None = None,
    model_runner: Callable[[dict, dict], Awaitable[str]] | None = None,
) -> dict:
    """执行一个本体函数，返回 ``{"ok", "value", "kind", ...}``。"""
    ctx = ctx or FunctionContext()
    fn = fn or {}
    kind = str(fn.get("kind") or "expression")
    if kind not in ONT_FUNCTION_KINDS:
        return {"ok": False, "msg": f"未知的函数形态：{kind}"}

    try:
        values = await prepare_inputs(fn, args, ctx, object_loader)
    except ExprError as e:
        return {"ok": False, "msg": str(e)}
    miss = missing_required(fn, values)
    if miss:
        return {"ok": False, "msg": f"缺少必填入参：{'、'.join(miss)}"}

    cfg = fn.get("config") or {}
    try:
        if kind == "expression":
            expr = (fn.get("expr") or "").strip()
            if not expr:
                return {"ok": False, "msg": "函数未定义表达式"}
            val = safe_eval(expr, values)
        elif kind == "aggregate":
            if aggregate_runner is None:
                return {"ok": False, "msg": "当前环境不支持关联聚合"}
            val = await aggregate_runner(cfg, values)
        elif kind == "http":
            r = await _run_http(cfg, values, ctx)
            if not r.get("ok"):
                return r
            val = r["value"]
        else:  # model
            if model_runner is None:
                return {"ok": False, "msg": "当前环境不支持模型调用"}
            val = await model_runner(cfg, values)
    except ExprError as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"{KIND_LABEL.get(kind, kind)}执行失败：{str(e)[:160]}"}

    return {
        "ok": True, "value": val, "kind": kind, "inputs": values,
        "outputs": coerce_outputs(fn, val),
        "msg": f"{KIND_LABEL.get(kind, kind)}执行完成",
    }


#: SSRF 防护：明确禁止的目标类别。
#:
#: 取舍说明：平台自己就连着内网 LLM 网关（172.168.x），http 形态函数与 Webhook
#: 调用内网服务是**合法用法**，因此**放行私有网段**；只拦
#: 环回 / 链路本地(含云元数据 169.254.169.254) / 保留 / 组播 / 未指定 ——
#: 这几类正是"把平台当内网探针、窃取云凭证"的入口，且响应原文会回传给调用方。
_SSRF_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "instance-data"}

#: 测试/本地联调逃生阀：置 1 时放行环回地址。**默认关闭，生产不得设置**。
#: 为什么需要它：`tests/test_function_engine.py` 的 `local_server` 夹具会起一个
#: 真实的 127.0.0.1 HTTPServer 来验证 http 形态函数，那是单元测试的合法用法；
#: 与其削弱生产防护，不如让例外显式且只在测试里生效。
_ALLOW_LOOPBACK_ENV = "AISTATION_ALLOW_LOOPBACK_HTTP"


def is_forbidden_url(url: str) -> str:
    """返回禁止原因；允许访问则返回空串。

    http 形态函数与 Webhook 都由持 edit 权限的用户配置，修前只校验 scheme
    ⇒ 可配 ``http://127.0.0.1:8002/...`` 探测本机端口、配 ``http://169.254.169.254/``
    窃取云元数据凭证，而且**响应原文会回传**（可读回的 SSRF）。

    域名会先解析再判（防 DNS rebinding 指向内网）；解析不了则放行，交给 httpx
    自己失败——不因为一次 DNS 故障就阻断合法调用。
    """
    import os

    import ipaddress
    from urllib.parse import urlparse

    if os.getenv(_ALLOW_LOOPBACK_ENV, "").strip() == "1":
        return ""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return "URL 无法解析"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "URL 缺少主机名"
    if host in _SSRF_BLOCKED_HOSTS:
        return f"禁止访问该地址：{host}"

    def _blocked(a: ipaddress._BaseAddress) -> bool:
        return bool(a.is_loopback or a.is_link_local or a.is_reserved
                    or a.is_multicast or a.is_unspecified)

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return f"禁止访问内网/保留地址：{host}" if _blocked(ip) else ""

    # 域名：解析后逐个地址判断
    try:
        import socket

        infos = socket.getaddrinfo(host, None)
    except Exception:  # noqa: BLE001  解析不了就放行，交给 httpx
        return ""
    for info in infos:
        try:
            a = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if _blocked(a):
            return f"禁止访问内网/保留地址：{host} → {info[4][0]}"
    return ""


async def _run_http(cfg: dict, values: dict, ctx: FunctionContext) -> dict:
    url = interp(str(cfg.get("url") or ""), values, ctx).strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "msg": "外部服务的 URL 必须是 http/https"}
    # SSRF（修）：拦环回/链路本地(含云元数据)/保留地址，防把平台当内网探针
    bad = is_forbidden_url(url)
    if bad:
        return {"ok": False, "msg": bad}
    method = str(cfg.get("method") or "GET").upper()
    if method not in ("GET", "POST", "PUT", "PATCH"):
        return {"ok": False, "msg": f"不支持的方法：{method}"}
    headers = {str(k): interp(str(v), values, ctx) for k, v in (cfg.get("headers") or {}).items()}
    body: Any = None
    if cfg.get("body_template"):
        body = json.loads(interp(str(cfg["body_template"]), values, ctx) or "{}")
    elif method in ("POST", "PUT", "PATCH"):
        body = {"inputs": values}
    if body is not None and len(json.dumps(body, ensure_ascii=False)) > _MAX_HTTP_BODY:
        return {"ok": False, "msg": "请求体过大"}
    timeout = min(max(float(cfg.get("timeout") or 10), 0.5), 60)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body)
        if resp.status_code >= 400:
            return {"ok": False, "msg": f"外部服务返回 {resp.status_code}：{resp.text[:120]}"}
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = resp.text
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"调用外部服务失败：{(str(e) or type(e).__name__)[:140]}"}

    path = str(cfg.get("result_path") or "").strip()
    val = dig(payload, path) if path else payload
    if path and val is None:
        return {"ok": False, "msg": f"响应里找不到路径 {path}"}
    return {"ok": True, "value": val}


# ---------------------------------------------------------------------------
# 校验（编辑期 + 工作副本审核）
# ---------------------------------------------------------------------------
def validate_function(fn: dict, prop_keys: set[str] | None = None) -> list[str]:
    """校验函数定义，返回错误列表。"""
    errs: list[str] = []
    kind = str(fn.get("kind") or "expression")
    if kind not in ONT_FUNCTION_KINDS:
        errs.append(f"函数形态不支持 {kind}（可用：{'、'.join(ONT_FUNCTION_KINDS)}）")
        return errs

    declared: list[str] = []
    for i, p in enumerate(fn.get("parameters") or []):
        if not isinstance(p, dict):
            errs.append(f"入参第 {i + 1} 项不是对象")
            continue
        key = str(p.get("key") or "").strip()
        if not key:
            errs.append(f"入参第 {i + 1} 项缺少 key")
            continue
        declared.append(key)
        src = str(p.get("source") or "parameter")
        if src not in ONT_INPUT_SOURCES:
            errs.append(f"入参 {key} 的来源不支持 {src}")
        t = str(p.get("type") or "string")
        if t not in ONT_VALUE_TYPES:
            errs.append(f"入参 {key} 的类型不支持 {t}")
        if src == "object_property" and not (p.get("object_property") or "").strip():
            errs.append(f"入参 {key} 来源是对象属性，但没填 object_property")

    cfg = fn.get("config") or {}
    if kind == "expression":
        expr = (fn.get("expr") or "").strip()
        if not expr:
            errs.append("表达式为空")
        else:
            for v in expr_vars(expr):
                if v not in declared:
                    errs.append(f"表达式里的变量 {v} 未在入参中声明")
            for c in expr_calls(expr):
                if c not in BUILTINS:
                    errs.append(f"未知函数 {c}（可用：{'、'.join(sorted(BUILTINS))}）")
    elif kind == "aggregate":
        if not (cfg.get("source_object") or "").strip():
            errs.append("关联聚合缺少源对象类型")
        agg = str(cfg.get("aggregation") or "")
        if agg not in ONT_AGGREGATIONS:
            errs.append(f"聚合方式非法：{agg or '(空)'}")
        path = cfg.get("link_path") or []
        if not path:
            errs.append("关联聚合缺少关系链")
        elif len(path) > 3:
            errs.append(f"关系链最多 3 层，当前 {len(path)} 层")
        lim = cfg.get("limit", 10)
        try:
            lim_i = int(lim)
        except (TypeError, ValueError):
            lim_i = 10
        if lim_i < 1 or lim_i > 100:
            errs.append(f"collection limit 必须在 1–100 之间，当前 {lim_i}")
        if agg != "count" and not (cfg.get("property") or "").strip():
            errs.append(f"聚合方式 {agg} 需要指定 property")
    elif kind == "http":
        url = str(cfg.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            errs.append("外部服务的 URL 必须是 http/https")
        # SSRF（修）：保存时就拒绝危险目标，不让它落库（运行时 _run_http 还会再拦一次）
        forbidden = is_forbidden_url(url) if url else ""
        if forbidden:
            errs.append(forbidden)
        m = str(cfg.get("method") or "GET").upper()
        if m not in ("GET", "POST", "PUT", "PATCH"):
            errs.append(f"不支持的 HTTP 方法：{m}")
        bt = cfg.get("body_template")
        if bt:
            try:
                json.loads(str(bt))
            except Exception:  # noqa: BLE001
                errs.append("body_template 不是合法 JSON")
    else:  # model
        # model_id 可留空 —— 留空时按平台默认 chat 模型解析（与其它模块一致）
        mid = cfg.get("model_id")
        if mid not in (None, "", 0):
            try:
                int(mid)
            except (TypeError, ValueError):
                errs.append(f"model_id 必须是整数或留空，当前 {mid}")
        if not (cfg.get("prompt") or "").strip():
            errs.append("模型调用缺少 prompt")
    return errs


def recommend_kind(fn: dict) -> str:
    """给旧数据推断合适的形态（老函数只有 expr）。"""
    k = str(fn.get("kind") or "").strip()
    if k in ONT_FUNCTION_KINDS:
        return k
    return "expression" if (fn.get("expr") or "").strip() else "expression"
