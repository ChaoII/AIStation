"""Agno 精选工具服务：就绪探测、OpenAI schema 生成、执行与名称派发。

设计要点：
- 一个 ``ai_tools`` 行对应一个 toolkit（``key``），启用后贡献其**全部**函数 schema。
- 生成名优先取 Agno 函数名（如 ``add``）；与其它启用工具重名时退化为
  ``f"{key}_{fn_name}"``（如 ``calculator_add``），保证全局唯一。
- 维护 ``生成名 -> (spec, agno 函数名)`` 的派发表，运行循环据此执行正确函数。
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect

from .registry import AGNO_BY_KEY, AGNO_CATALOG

# 生成名 -> (spec, agno 函数名)，供运行循环按 OpenAI function name 派发
_DISPATCH: dict[str, tuple[dict, str]] = {}
# 生成名 -> 该 toolkit 的运行配置（如 api_key），执行时透传
_CONFIG_BY_NAME: dict[str, dict | None] = {}

# Python 注释类型 -> JSON Schema 类型
_TYPE_MAP: dict[object, str] = {
    int: "number",
    float: "number",
    str: "string",
    bool: "boolean",
}

# 生成 schema 时忽略的特殊参数名
_SKIP_PARAMS = {"self", "args", "kwargs"}


def get_spec(key: str) -> dict | None:
    """按 key 取注册表条目。"""
    return AGNO_BY_KEY.get(key)


def _probe(spec: dict) -> tuple[bool, str]:
    """探测依赖与类是否可用：返回 ``(ready, reason)``。"""
    req = spec.get("requires")
    if req:
        try:
            found = importlib.util.find_spec(req) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            found = False
        if not found:
            return False, f"缺少依赖：{req}"
    try:
        mod = importlib.import_module(spec["module"])
        getattr(mod, spec["class_name"])
        return True, ""
    except Exception as e:  # noqa: BLE001 探测期间任何异常都视为未就绪
        return False, str(e)


def get_tool_specs() -> list[dict]:
    """返回精选工具规格（含 ``ready`` / ``reason`` / ``config_fields`` 等）。"""
    out: list[dict] = []
    for spec in AGNO_CATALOG:
        ready, reason = _probe(spec)
        out.append({**spec, "ready": ready, "reason": reason, "source": "agno"})
    return out


def _instantiate(spec: dict, config: dict | None = None):
    """惰性 import 并实例化 Agno toolkit。

    仅透传「注册表声明字段」或「构造函数显式形参」的配置键：
    部分 toolkit 的 ``__init__`` 是 ``**kwargs``，直接传入自定义参数会报
    unexpected keyword 导致整个工具集不可用。
    """
    from .registry import AGNO_BY_KEY

    mod = importlib.import_module(spec["module"])
    cls = getattr(mod, spec["class_name"])
    raw: dict = dict(config or {})
    declared = {f["key"] for f in (spec.get("config_fields") or [])}
    # 兼容调用方传入不带 config_fields 的裸 spec
    if spec.get("key") in AGNO_BY_KEY:
        declared |= {f["key"] for f in (AGNO_BY_KEY[spec["key"]].get("config_fields") or [])}

    try:
        params = inspect.signature(cls.__init__).parameters
        has_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        params, has_var_kw = {}, False

    if has_var_kw:
        kwargs = {k: v for k, v in raw.items() if k in declared}
    else:
        explicit = {k for k in params if k != "self"}
        kwargs = {k: v for k, v in raw.items() if k in declared or k in explicit}
    return cls(**kwargs)


def _param_schema(p: inspect.Parameter) -> dict:
    """由单个参数推导 JSON Schema 片段。"""
    schema: dict = {"type": _TYPE_MAP.get(p.annotation, "string")}
    return schema


def _build_parameters(fn) -> dict:
    """由 Agno 函数 entrypoint 签名生成 OpenAI parameters（object schema）。"""
    try:
        sig = inspect.signature(fn.entrypoint)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": []}
    props: dict = {}
    required: list[str] = []
    for pname, p in sig.parameters.items():
        if pname in _SKIP_PARAMS:
            continue
        if p.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        props[pname] = _param_schema(p)
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    return {"type": "object", "properties": props, "required": required}


def build_openai_schemas(
    spec: dict,
    config: dict | None = None,
    used_names: set[str] | None = None,
) -> list[dict]:
    """实例化 toolkit，为其中每个 Agno 函数生成一个 OpenAI function schema。

    - ``used_names``：已占用（系统/HTTP/其它 toolkit）的生成名集合，用于去重；
      缺省时仅在该 toolkit 内部去重。
    - 实例化失败（如缺少必需 Key）返回空列表，不抛异常。
    """
    try:
        inst = _instantiate(spec, config)
    except Exception:  # noqa: BLE001
        return []

    used = used_names if used_names is not None else set()
    schemas: list[dict] = []
    for fn_name, fn in (inst.functions or {}).items():
        openai_name = fn_name
        if openai_name in used:
            openai_name = f"{spec['key']}_{fn_name}"
        used.add(openai_name)
        _DISPATCH[openai_name] = (spec, fn_name)
        _CONFIG_BY_NAME[openai_name] = config
        description = inspect.getdoc(fn.entrypoint) or spec.get("description") or spec["title"]
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": openai_name,
                    "description": description,
                    "parameters": _build_parameters(fn),
                },
            }
        )
    return schemas


def resolve_function(tool_name: str) -> tuple[dict, str] | None:
    """按生成的 OpenAI 函数名解析出 ``(spec, agno 函数名)``；未命中返回 None。"""
    return _DISPATCH.get(tool_name)


def resolve_config(tool_name: str) -> dict | None:
    """按生成的 OpenAI 函数名取对应 toolkit 的运行配置。"""
    return _CONFIG_BY_NAME.get(tool_name)


def build_openai_schema(
    spec: dict, config: dict | None = None, used_names: set[str] | None = None
) -> dict:
    """便捷方法：返回该 toolkit 的首个函数 schema（无可用函数时返回空 dict）。"""
    schemas = build_openai_schemas(spec, config, used_names)
    return schemas[0] if schemas else {}


async def execute(spec: dict, fn_name: str, args: dict | None, config: dict | None = None) -> object:
    """执行 toolkit 中指定函数：同步/异步均支持；异常统一返回 ``{"error": ...}``。"""
    try:
        inst = _instantiate(spec, config)
    except Exception as e:  # noqa: BLE001
        return {"error": f"初始化失败：{e}"}
    fn = (inst.functions or {}).get(fn_name)
    if fn is None:
        return {"error": f"工具函数不存在：{fn_name}"}
    try:
        result = fn.entrypoint(**(args or {}))
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
