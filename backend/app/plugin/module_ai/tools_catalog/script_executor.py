"""自定义 Python 脚本工具的执行沙箱。

安全策略（三层）：
1. **静态校验**（``validate``）：AST 白名单——仅允许导入白名单模块；禁止
   ``eval/exec/compile/open/__import__/getattr/setattr`` 等危险内建；禁止
   双下划线名称与属性访问；禁止 ``with/async/await/global/nonlocal``。
2. **受限内建**：执行时只注入安全 builtins 白名单（无 ``open``/``__import__``）。
3. **超时**：``sys.settrace`` 行计数（Windows 无 ``signal.alarm``，故不用信号）。

入口约定：脚本必须定义 ``def run(args: dict) -> dict``。
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


def _build_globals() -> dict[str, Any]:
    """构造受限执行全局命名空间（白名单 builtins + 白名单模块）。"""
    import importlib

    ns: dict[str, Any] = {"__builtins__": dict(SAFE_BUILTINS), "__name__": "sandbox_script"}
    for mod_name in ALLOWED_MODULES:
        try:
            ns[mod_name] = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001  个别模块在精简环境可能缺失，忽略
            continue
    return ns


def run(code: str, args: dict | None = None, timeout: int = 10) -> dict:
    """执行脚本并返回结果（dict）。

    参数:
    - code: 脚本源码（须定义 ``run(args)``）。
    - args: 传入 ``run`` 的参数字典。
    - timeout: 超时秒数（换算为行计数上限）。

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

    ns = _build_globals()
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
        result = fn(dict(args or {}))
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
