"""自定义 Python 脚本工具的执行沙箱。

安全策略（三层）：
1. **静态校验**（``validate``）：AST 白名单——仅允许导入白名单模块；禁止
   ``eval/exec/compile/open/__import__/getattr/setattr`` 等危险内建；禁止
   双下划线名称与属性访问；禁止 ``with/async/await/global/nonlocal``。
2. **受限内建**：执行时只注入安全 builtins 白名单（无 ``open``/``__import__``）。
3. **超时**：``sys.settrace`` 行计数（Windows 无 ``signal.alarm``，故不用信号）。

入口约定：脚本必须定义 ``def run(...) -> dict``。支持两种形态：
1. 带类型注解的多参数：``def run(name: str = "x", age: int = 3) -> dict`` ——
   调用时按参数名传值，可自动提取参数名/类型/默认值/必填。
2. 兼容旧脚本：``def run(args: dict) -> dict`` —— 整个入参 dict 传入。
"""
from __future__ import annotations

import ast
import json
import sys
from typing import Any

from app.core.exceptions import CustomException

#: 允许导入的模块（纯计算/数据处理，无文件与网络能力）
ALLOWED_MODULES = {
    "json",
    "math",
    "re",
    "datetime",
    "random",
    "statistics",
    "collections",
    "itertools",
    "functools",
    "typing",
    "string",
    "decimal",
    "fractions",
    "hashlib",
    "base64",
    "uuid",
    "csv",
}

#: 禁止出现的内建名（直接调用或引用）
FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "breakpoint",
    "exit",
    "quit",
    "help",
    "memoryview",
    "super",
    "type",
    "object",
    "classmethod",
    "staticmethod",
    "property",
}

#: 允许的内建函数/常量/异常
SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "ascii": ascii,
    "bin": bin,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "callable": callable,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    # 异常类（供 try/except 使用）
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "ArithmeticError": ArithmeticError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "AssertionError": AssertionError,
}

#: 每“超时秒”允许执行的行数上限（行计数近似指令计数）
_OPS_PER_SECOND = 200_000


def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001, A002
    """受限 import：只允许白名单模块（供脚本内 ``import xxx`` 使用）。"""
    import importlib

    top = (name or "").split(".")[0]
    if top not in ALLOWED_MODULES:
        raise ImportError(f"不允许导入模块：{name}")
    return importlib.import_module(name)


#: 注入受限 builtins 的 ``__import__``（脚本内 import 语句需要）
SAFE_BUILTINS["__import__"] = _safe_import


class _ScriptTimeout(Exception):
    """脚本执行超时（内部信号，转换为 CustomException）。"""


def _check_node(node: ast.AST) -> None:
    """逐节点静态校验，非法即抛 CustomException。"""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        for name in names:
            top = (name or "").split(".")[0]
            if top not in ALLOWED_MODULES:
                raise CustomException(msg=f"不允许导入模块：{name}")
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("__"):
            raise CustomException(msg=f"不允许访问双下划线属性：{node.attr}")
    if isinstance(node, ast.Name):
        if node.id.startswith("__"):
            raise CustomException(msg=f"不允许使用双下划线名称：{node.id}")
        if node.id in FORBIDDEN_NAMES:
            raise CustomException(msg=f"不允许使用：{node.id}")
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.name.startswith("__"):
            raise CustomException(msg=f"不允许定义双下划线名称：{node.name}")
    if isinstance(
        node,
        (
            ast.With,
            ast.AsyncWith,
            ast.AsyncFunctionDef,
            ast.AsyncFor,
            ast.Await,
            ast.Global,
            ast.Nonlocal,
        ),
    ):
        raise CustomException(msg=f"不允许的语法：{type(node).__name__}")


def validate(code: str) -> None:
    """静态校验脚本源码，非法抛 CustomException。"""
    if not (code or "").strip():
        raise CustomException(msg="脚本内容不能为空")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise CustomException(msg=f"脚本语法错误：{e.msg}（第 {e.lineno} 行）") from e
    for node in ast.walk(tree):
        _check_node(node)
    # 必须定义 run 函数
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if "run" not in funcs:
        raise CustomException(msg="脚本必须定义 run(args) 函数")


#: 类型注解（ast 节点）→ JSON Schema type 的映射
_ANNOTATION_TYPE_MAP: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "tuple": "array",
    "set": "array",
    "bytes": "string",
    "Any": "",
}


def _annotation_to_type(node: ast.AST | None) -> str:
    """把类型注解 AST 节点转成 JSON Schema type（尽力而为，失败返回空串）。"""
    if node is None:
        return ""
    # 形如 list[str]、dict[str, int]
    if isinstance(node, ast.Subscript):
        base = node.value
        if isinstance(base, ast.Name):
            return _ANNOTATION_TYPE_MAP.get(base.id, base.id.lower())
        return ""
    if isinstance(node, ast.Name):
        return _ANNOTATION_TYPE_MAP.get(node.id, node.id.lower())
    # 形如 str | None（Union）
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _annotation_to_type(node.left)
        return left
    if isinstance(node, ast.Constant):
        return _ANNOTATION_TYPE_MAP.get(str(node.value), "string")
    return ""


def _literal_default(node: ast.AST | None) -> Any:
    """把默认值 AST 节点求值为 Python 字面量；无法求值返回 None。"""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:  # noqa: BLE001
        # 无法求值（如可变默认 list/dict），用 ast.unparse 还原为文本代表
        try:
            return ast.unparse(node)
        except Exception:  # noqa: BLE001
            return None


def _extract_run_params(code: str) -> list[dict]:
    """从 run 函数签名提取参数（名/类型/默认/必填）。无 run 或非多参形态返回 []。"""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return []
    run_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run"),
        None,
    )
    if run_node is None:
        return []
    args = run_node.args
    # 仅一个参数（且通常名为 args）→ 旧形态 dict 入参，无可提取的多参
    if len(args.args) == 1 and not args.vararg and not args.kwarg:
        return []
    positional = args.args
    defaults = list(args.defaults)
    # 默认值与位置参数从后往前对齐
    default_map: dict[str, ast.AST | None] = {}
    if defaults:
        for arg_node, default_node in zip(
            positional[-len(defaults):], defaults, strict=False
        ):
            default_map[arg_node.arg] = default_node
    params: list[dict] = []
    for i, arg_node in enumerate(positional):
        name = arg_node.arg
        if name == "self":
            continue
        if i > 0 and args.posonlyargs and arg_node in args.posonlyargs:
            pass
        type_name = _annotation_to_type(arg_node.annotation)
        has_default = name in default_map
        params.append(
            {
                "name": name,
                "type": type_name,
                "default": _literal_default(default_map.get(name)) if has_default else None,
                "required": not has_default,
            }
        )
    return params


def _call_run(fn: Any, args: dict, code: str) -> Any:
    """按 run 签名调用：多参形态按名传值，单参形态兼容传入整个 dict。"""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return fn(dict(args or {}))
    run_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run"),
        None,
    )
    if run_node is None:
        return fn(dict(args or {}))
    if len(run_node.args.args) == 1 and not run_node.args.vararg and not run_node.args.kwarg:
        return fn(dict(args or {}))
    # 多参形态：只传签名里出现的键，保证带默认值的参数可省略
    keys = {a.arg for a in run_node.args.args}
    kwargs = {k: v for k, v in (args or {}).items() if k in keys}
    return fn(**kwargs)


def _build_globals(config: dict | None = None) -> dict[str, Any]:
    """构造受限执行全局命名空间（白名单 builtins + 白名单模块 + 工具配置）。

    注入 ``TOOL_CONFIG``（工具私有配置，如密钥/敏感值/按用户区分的参数），
    脚本内以 ``TOOL_CONFIG["api_key"]`` 读取；值不可见、不与源码明文混存。
    """
    import importlib

    ns: dict[str, Any] = {"__builtins__": dict(SAFE_BUILTINS), "__name__": "sandbox_script"}
    for mod_name in ALLOWED_MODULES:
        try:
            ns[mod_name] = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001  个别模块在精简环境可能缺失，忽略
            continue
    ns["TOOL_CONFIG"] = dict(config or {})
    return ns


def run(code: str, args: dict | None = None, timeout: int = 10, config: dict | None = None) -> dict:
    """执行脚本并返回结果（dict）。

    参数:
    - code: 脚本源码（须定义 ``run(args)``）。
    - args: 传入 ``run`` 的参数字典。
    - timeout: 超时秒数（换算为行计数上限）。
    - config: 工具私有配置，注入为沙箱全局 ``TOOL_CONFIG``，供脚本读取。

    返回:
    - dict: ``run`` 的返回值；非 dict 结果包成 ``{"result": ...}``。
    """
    validate(code)
    max_ops = max(int(timeout or 10), 1) * _OPS_PER_SECOND
    counter = {"n": 0}

    def _tracer(frame, event, arg):  # noqa: ANN001
        if event == "line":
            counter["n"] += 1
            if counter["n"] > max_ops:
                raise _ScriptTimeout()
        return _tracer

    ns = _build_globals(config)
    try:
        compiled = compile(code, "<ai_script_tool>", "exec")
    except SyntaxError as e:  # pragma: no cover - validate 已拦截
        raise CustomException(msg=f"脚本语法错误：{e.msg}") from e

    sys.settrace(_tracer)
    try:
        exec(compiled, ns)  # noqa: S102  沙箱内执行，已做静态校验与受限内建
        fn = ns.get("run")
        if not callable(fn):
            raise CustomException(msg="脚本必须定义 run(args) 函数")
        result = _call_run(fn, dict(args or {}), code)
    except _ScriptTimeout as e:
        raise CustomException(msg=f"脚本执行超时（>{timeout}s）") from e
    except CustomException:
        raise
    except Exception as e:  # noqa: BLE001  脚本自身异常统一转为业务错误
        raise CustomException(msg=f"脚本执行失败：{type(e).__name__}: {e}") from e
    finally:
        sys.settrace(None)

    if isinstance(result, dict):
        payload = result
    else:
        payload = {"result": result}
    # 确保结果可 JSON 序列化，否则降级为字符串
    try:
        json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return {"result": str(payload)}
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
