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
import typing
from collections.abc import Sequence as ABCSequence

from app.config.setting import settings

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

# 数组注解的 origin（typing.List / list / Sequence / tuple）
_ARRAY_ORIGINS = (list, tuple, ABCSequence)


def reset_registry() -> None:
    """清空进程级派发表/配置表，避免已禁用工具的函数名残留可派发。"""
    _DISPATCH.clear()
    _CONFIG_BY_NAME.clear()


def get_spec(key: str) -> dict | None:
    """按 key 取注册表条目。"""
    return AGNO_BY_KEY.get(key)


def _probe(spec: dict) -> tuple[bool, str]:
    """探测依赖与类是否可用：返回 ``(ready, reason)``。

    ``requires`` 为**导入模块名**（find_spec 需要），提示文案优先用 ``pip_name``
    （pip 分发名，可与导入名不同），便于用户按正确包名安装。
    """
    req = spec.get("requires")
    if req:
        try:
            found = importlib.util.find_spec(req) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            found = False
        if not found:
            return False, f"缺少依赖：{spec.get('pip_name') or req}"
    try:
        mod = importlib.import_module(spec["module"])
        getattr(mod, spec["class_name"])
        return True, ""
    except Exception as e:  # noqa: BLE001 探测期间任何异常都视为未就绪
        return False, str(e)


def readiness(spec: dict, config: dict | None) -> tuple[bool, str]:
    """综合判定工具是否就绪：依赖探测 + 必填配置项检查。

    - 依赖缺失/类不可用 → ``_probe`` 的 ``(False, reason)``。
    - ``config_fields`` 中 ``required: True`` 的字段在已存 ``config`` 中缺失或为空
      → ``(False, "缺少配置：<字段名>")``。
    - ``risk == "high"`` 且未开启 ``AI_ENABLE_DANGEROUS_TOOLS`` → 直接判未就绪，
      使其既不能启用、也不会进入 ``get_enabled_tool_schemas``（永不可派发）。
    """
    if spec.get("risk") == "high" and not settings.AI_ENABLE_DANGEROUS_TOOLS:
        return False, "高危工具默认禁用（需开启 AI_ENABLE_DANGEROUS_TOOLS）"
    ready, reason = _probe(spec)
    if not ready:
        return ready, reason
    cfg = config or {}
    for field in spec.get("config_fields") or []:
        if not field.get("required"):
            continue
        key = field["key"]
        value = cfg.get(key)
        if value is None or value == "":
            label = field.get("label") or key
            return False, f"缺少配置：{label}（{key}）"
    return True, ""


def get_tool_specs(config_by_key: dict | None = None) -> list[dict]:
    """返回精选工具规格（含 ``ready`` / ``reason`` / ``config_fields`` 等）。

    ``config_by_key``：``{tool_key: 已存 config}`` 映射；据此判定必填配置是否满足。
    """
    cfg_map = config_by_key or {}
    out: list[dict] = []
    for spec in AGNO_CATALOG:
        ready, reason = readiness(spec, cfg_map.get(spec["key"]))
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
    """由单个参数推导 JSON Schema 片段。

    - ``List[str]`` / ``Sequence[str]`` / ``list[str]`` / ``tuple[...]`` → 字符串数组，
      避免把 shell 的 ``args`` 之类命令参数误判为单个字符串（否则工具无法调用）。
    - 其余已声明基础类型用 ``_TYPE_MAP``，未知注解退化为 ``string``。
    """
    if typing.get_origin(p.annotation) in _ARRAY_ORIGINS:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": _TYPE_MAP.get(p.annotation, "string")}


def _build_parameters(fn) -> dict:
    """由 Agno 函数 entrypoint 签名生成 OpenAI parameters（object schema）。"""
    try:
        sig = inspect.signature(fn.entrypoint)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": []}
    props: dict = {}
    required: list[str] = []
    for pname, p in sig.parameters.items():
        # 仅按 kind 过滤 *args/**kwargs；不再按名称跳过 args/self
        # （ShellTools.run_shell_command 的命令参数就叫 args，跳过会导致工具无法调用）
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
