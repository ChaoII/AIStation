"""AI 工具服务：内置工具开关 + 自定义 HTTP 工具执行。"""
import json

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

from .model import AiToolModel

# 请求头/配置脱敏掩码：列表/详情只回显键与掩码，不回传明文密钥
HEADER_MASK = "****"

# 配置中疑似密钥的键名片段（命中即脱敏）
_SECRET_HINTS = ("key", "secret", "token", "password")


def _mask_headers(headers: dict | None) -> dict | None:
    """请求头脱敏：保留键名，值统一替换为掩码。"""
    if not headers:
        return headers
    return {str(k): HEADER_MASK for k in headers}


def _mask_config(config: dict | None) -> dict | None:
    """工具配置脱敏：疑似密钥字段的值替换为掩码，其余原样返回。"""
    if not config:
        return config
    masked: dict = {}
    for key, val in config.items():
        name = str(key).lower()
        if val not in (None, "") and any(h in name for h in _SECRET_HINTS):
            masked[str(key)] = HEADER_MASK
        else:
            masked[str(key)] = val
    return masked


def _mask_config_all(config: dict | None) -> dict | None:
    """运行时私有配置（脚本 TOOL_CONFIG）全量脱敏：所有值统一替换为掩码。

    此类参数多为密钥/敏感值/按用户区分的参数，值一律不对外可见。
    """
    if not config:
        return config
    return {str(k): HEADER_MASK for k in config}


def _merge_config(old: dict | None, new: dict) -> dict:
    """合并更新配置：掩码/空串保留原值，未出现键删除，其余覆盖。"""
    before = old or {}
    merged: dict = {}
    for key, val in (new or {}).items():
        if val == HEADER_MASK or val == "":
            if key in before:
                merged[key] = before[key]
            continue
        merged[key] = val
    return merged


def _merge_headers(old: dict | None, new: dict) -> dict:
    """合并更新请求头：值为掩码/空串时保留原值，未出现键删除，其余覆盖。"""
    before = old or {}
    merged: dict = {}
    for key, val in (new or {}).items():
        if val == HEADER_MASK or val == "":
            if key in before:
                merged[key] = before[key]
            continue
        merged[key] = val
    return merged


def _tool_source(t: AiToolModel) -> str:
    """推导工具来源：显式 source 优先，其次兼容旧 kind 字段。"""
    if t.source:
        return t.source
    return "http" if (t.kind or "") == "http" else "system"


def can_create_script_tool(auth, script_allowed: bool) -> bool:
    """``script_allowed`` 总开关判定：关闭时仅超管可创建/编辑/启用/运行脚本工具。

    - ``script_allowed=True``：任意用户可创建。
    - ``script_allowed=False``：仅超管（``is_superuser``）可创建，普通用户被拒。
    """
    if script_allowed:
        return True
    user = getattr(auth, "user", None)
    return bool(getattr(user, "is_superuser", False))


#: 平台脚本安全配置键（存于 ``sys_param``，启动时载入 Redis ``system_config``）。
_SCRIPT_ALLOWED_KEY = "script_allowed"
_SANDBOX_POLICIES_KEY = "script_sandbox_policies"


def _parse_script_allowed(value: str | None) -> bool:
    """解析 ``script_allowed`` 配置值；缺省视为允许。"""
    if value is None:
        return True
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_sandbox_policies(value: str | None) -> dict:
    """解析 ``script_sandbox_policies`` 配置（JSON）；缺省/非法回退默认安全策略。"""
    from .script_executor import DEFAULT_POLICIES

    policies = dict(DEFAULT_POLICIES)
    if not value:
        return policies
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return policies
    if isinstance(parsed, dict):
        # 默认策略为底，配置里显式传入的逐项覆盖（实现「默认收紧 + 可放宽」）
        return {**DEFAULT_POLICIES, **parsed}
    return policies


async def get_script_safety_config(db=None) -> tuple[bool, dict]:
    """读取平台脚本安全配置，返回 ``(script_allowed, sandbox_policies)``。

    - ``script_allowed``：全局总开关，默认开。
    - ``sandbox_policies``：沙箱强化策略（可逐项放宽），默认用 ``DEFAULT_POLICIES``。
    ``db`` 可传入已有会话（如 create/update 事务内）以复用连接；否则自行开会话。
    """
    from app.api.v1.module_system.params.model import ParamsModel

    async def _read(sess) -> tuple[bool, dict]:
        rows = (
            await sess.execute(
                select(ParamsModel.config_key, ParamsModel.config_value)
                .where(
                    ParamsModel.config_key.in_(
                        [_SCRIPT_ALLOWED_KEY, _SANDBOX_POLICIES_KEY]
                    )
                )
            )
        ).all()
        allowed = True
        policies = _parse_sandbox_policies(None)
        for key, val in rows:
            if key == _SCRIPT_ALLOWED_KEY:
                allowed = _parse_script_allowed(val)
            elif key == _SANDBOX_POLICIES_KEY:
                policies = _parse_sandbox_policies(val)
        return allowed, policies

    if db is not None:
        return await _read(db)
    async with async_db_session() as sess:
        return await _read(sess)


def _assert_script_allowed(auth, script_allowed: bool) -> None:
    """总开关拦截：非超管且开关关闭时，禁止创建/编辑/启用/运行脚本工具。"""
    if not can_create_script_tool(auth, script_allowed):
        raise CustomException(msg="平台已禁用脚本工具，请联系系统管理员")


async def _is_superuser_by_id(user_id: int | None) -> bool:
    """按用户 ID 判超管（运行时 dispatch 仅有 ``user_id``，无完整 auth）。"""
    if not user_id:
        return False
    from app.api.v1.module_system.user.model import UserModel

    async with async_db_session() as db:
        val = await db.scalar(
            select(UserModel.is_superuser).where(
                UserModel.id == user_id,
                UserModel.is_deleted.is_(False),
            )
        )
        return bool(val)


def _validate_script(code: str | None, policies: dict | None = None) -> None:
    """脚本工具创建/更新时的静态校验（AST 白名单，按策略启用）。"""
    from .script_executor import validate as validate_script

    validate_script(code or "", policies)


def _inspect_script(code: str | None, policies: dict | None = None) -> dict:
    """解析脚本 run 签名，提取参数与基础校验结果。"""
    from .script_executor import _extract_run_params
    from .script_executor import validate as validate_script

    code = code or ""
    params = _extract_run_params(code)
    try:
        validate_script(code, policies)
        valid = True
        error = ""
    except CustomException as e:
        valid = False
        error = e.msg
    return {"valid": valid, "error": error, "params": params}


def _format_script(code: str | None) -> str:
    """用 ruff format 格式化 Python 脚本；ruff 不可用时原样返回。"""
    import ast as _ast
    import shutil
    import subprocess

    code = code or ""
    if not code.strip():
        return code
    # 先做语法校验，语法错误不格式化（直接返回原码）
    try:
        _ast.parse(code, mode="exec")
    except SyntaxError:
        return code
    ruff = shutil.which("ruff")
    if not ruff:
        return code
    try:
        proc = subprocess.run(
            [ruff, "format", "-", "--quiet"],
            input=code.encode("utf-8"),
            capture_output=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.decode("utf-8")
    except Exception:  # noqa: BLE001
        pass
    return code


def _readiness_of(t: AiToolModel) -> tuple[bool, str]:
    """按来源判定工具就绪性：agno 走注册表（依赖 + 必填配置 + 高危门禁），其余恒就绪。"""
    if _tool_source(t) == "agno":
        from app.plugin.module_ai.agno_tools import service as agno

        spec = agno.get_spec(t.name)
        if spec:
            return agno.readiness(spec, t.config)
    return True, ""


def _assert_enableable(t: AiToolModel) -> None:
    """启用前校验：未就绪（缺依赖/缺必填配置/高危门禁关闭）一律拒绝，抛 CustomException。"""
    ready, reason = _readiness_of(t)
    if not ready:
        raise CustomException(msg=reason or "工具未就绪，无法启用")


def _agno_meta(t: AiToolModel) -> dict:
    """为 agno 行补充前端所需的注册表元数据：别名/分组/风险/配置字段。"""
    if _tool_source(t) != "agno":
        return {}
    from app.plugin.module_ai.agno_tools import service as agno

    spec = agno.get_spec(t.name)
    if not spec:
        return {}
    return {
        "title": spec.get("title"),
        "group": spec.get("group"),
        "risk": spec.get("risk"),
        "config_fields": spec.get("config_fields") or [],
    }


def _to_dict(t: AiToolModel) -> dict:
    ready, reason = _readiness_of(t)
    meta = _agno_meta(t)
    # 脚本工具：config 是运行时私有参数（密钥/敏感值/按用户区分），全量脱敏，值不可见
    if (t.kind or "") == "script":
        config_out = _mask_config_all(t.config)
    else:
        config_out = _mask_config(t.config)
    return {
        "id": t.id,
        "name": t.name,
        "kind": t.kind or "builtin",
        "source": _tool_source(t),
        "config": config_out,
        "method": t.method or "GET",
        "url": t.url or "",
        "headers": _mask_headers(t.headers),
        "body_type": t.body_type or "json",
        "params_schema": t.params_schema,
        "code": t.code or "",
        "timeout": t.timeout or 10,
        "enabled": t.enabled,
        "ready": ready,
        "reason": reason,
        "description": t.description,
        "title": meta.get("title"),
        "group": meta.get("group"),
        "risk": meta.get("risk"),
        "config_fields": meta.get("config_fields") or [],
    }


def _http_schema(tool: AiToolModel) -> dict:
    """按 params_schema 生成 OpenAI 函数工具 schema。"""
    schema = tool.params_schema or {"type": "object", "properties": {}}
    description = schema.get("description") if isinstance(schema, dict) else None
    kind_label = "脚本" if (tool.kind or "") == "script" else "HTTP"
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description or f"自定义{kind_label}工具：{tool.name}",
            "parameters": schema,
        },
    }


async def execute_script_tool(tool: AiToolModel, args: dict, policies: dict | None = None) -> object:
    """执行自定义脚本工具（沙箱内），并注入工具私有配置为沙箱全局 ``TOOL_CONFIG``。"""
    from .script_executor import run as run_script

    return run_script(
        tool.code or "",
        args or {},
        tool.timeout or 10,
        config=tool.config or {},
        policies=policies,
    )


async def execute_http_tool(tool: AiToolModel, args: dict) -> object:
    """执行自定义 HTTP 工具：URL 路径占位替换 + 剩余参数按方法/请求体类型进入 query/body。

    请求体类型（body_type）：
    - none：剩余入参全部作为 query。
    - json：剩余入参作为 JSON body。
    - form-data：剩余入参作为 application/x-www-form-urlencoded。
    GET/DELETE 无请求体，恒为 none；POST/PUT/PATCH 默认 json。
    """
    import httpx

    url = tool.url or ""
    headers = {str(k): str(v) for k, v in (tool.headers or {}).items()}
    remaining = {k: v for k, v in (args or {}).items() if f"{{{k}}}" in url}
    for k, v in remaining.items():
        url = url.replace(f"{{{k}}}", str(v))
    params = {k: v for k, v in (args or {}).items() if k not in remaining}
    method = (tool.method or "GET").upper()
    body_type = (tool.body_type or "json").lower()
    if method in ("GET", "DELETE"):
        body_type = "none"
    json_body = None
    form_body = None
    if body_type == "json":
        json_body = params
        params = None
    elif body_type == "form-data":
        form_body = params
        params = None
    async with httpx.AsyncClient(timeout=30) as c:
        method_map = {
            "GET": lambda: c.get(url, params=params, headers=headers),
            "POST": lambda: c.post(url, params=params, json=json_body, data=form_body, headers=headers),
            "PUT": lambda: c.put(url, params=params, json=json_body, data=form_body, headers=headers),
            "PATCH": lambda: c.patch(url, params=params, json=json_body, data=form_body, headers=headers),
            "DELETE": lambda: c.delete(url, params=params, headers=headers),
        }
        resp = await method_map.get(method, method_map["GET"])()
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"status": resp.status_code, "text": resp.text[:2000]}


def build_http_tool_fn(tool: AiToolModel):
    """构建可被运行时调用的异步函数（参数即工具入参）。"""

    async def _fn(**kwargs) -> object:
        return await execute_http_tool(tool, kwargs)

    return _fn


def build_http_tool_schema(tool: AiToolModel) -> dict:
    """公开封装：按 params_schema 生成自定义 HTTP 工具的 OpenAI schema。"""
    return _http_schema(tool)


async def get_tool_by_name(name: str) -> AiToolModel | None:
    """按工具名取未删除的工具行（含启停状态），供应用运行时派发。"""
    async with async_db_session() as db:
        return await db.scalar(
            select(AiToolModel).where(
                AiToolModel.name == name,
                AiToolModel.is_deleted.is_(False),
            )
        )


async def get_enabled_tool_schemas() -> list[dict]:
    """返回所有启用工具的 OpenAI 函数 schema，合并 system/agno/http 三类来源。

    - system：取内置注册表静态 schema。
    - agno：实例化 toolkit，展开其全部函数 schema（缺依赖/Key 时自动跳过）。
    - http：按 ``params_schema`` 生成。
    """
    async with async_db_session() as db:
        rows = (
            await db.execute(
                select(AiToolModel)
                .where(
                    AiToolModel.is_deleted.is_(False),
                    AiToolModel.enabled.is_(True),
                )
                .order_by(AiToolModel.id.asc())
            )
        ).scalars().all()

    from app.plugin.module_ai.agno_tools import service as agno

    # 每次重建派发表：只保留当前启用且就绪的工具，避免禁用工具的函数名残留可派发
    agno.reset_registry()

    # 预留系统与 HTTP 工具名，避免 Agno 生成名与它们重名
    reserved: set[str] = set(TOOL_REGISTRY.keys())
    reserved.update(t.name for t in rows if _source_of_row(t) == "http")

    schemas: list[dict] = []
    for tool in rows:
        source = _source_of_row(tool)
        if source == "agno":
            spec = agno.get_spec(tool.name)
            # 显式按 readiness 过滤：缺依赖或缺必填配置的工具不下发 schema
            if spec and agno.readiness(spec, tool.config)[0]:
                schemas.extend(agno.build_openai_schemas(spec, tool.config, reserved))
        elif source == "http":
            schemas.append(_http_schema(tool))
        elif source == "script":
            schemas.append(_http_schema(tool))
        else:
            entry = TOOL_REGISTRY.get(tool.name)
            if entry:
                schemas.append(entry["schema"])
    return schemas


def _source_of_row(tool: AiToolModel) -> str:
    """推导 DB 行来源（兼容无 source 的旧数据）。"""
    if tool.source:
        return tool.source
    return "http" if (tool.kind or "") == "http" else "system"


async def dispatch_tool(
    name: str,
    args: dict | None,
    user_id: int | None,
    db_rows: dict | None = None,
) -> object:
    """按工具名分派执行：Agno -> execute，system -> _call_tool，http -> execute_http_tool。

    ``name`` 为下发给大模型的 OpenAI function name；Agno 工具可能是生成名
    （如 ``add`` / ``calculator_add``），由 ``agno_tools.service.resolve_function`` 解析。
    """
    from app.plugin.module_ai.agno_tools import service as agno

    resolved = agno.resolve_function(name)
    if resolved is not None:
        spec, fn_name = resolved
        # 派发前校验 DB 行启用 + 就绪（含高危门禁），禁用工具绝不可执行
        row = await get_tool_by_name(spec["key"])
        if row is None or not row.enabled or not agno.readiness(spec, row.config)[0]:
            return {"error": "工具未启用"}
        return await agno.execute(spec, fn_name, args, agno.resolve_config(name))

    if name in TOOL_REGISTRY:
        row = await get_tool_by_name(name)
        if row is None or not row.enabled:
            return {"error": "工具未启用"}
        from app.plugin.module_ai.assistant.service import _call_tool

        return await _call_tool(name, args, user_id)

    tool = db_rows.get(name) if isinstance(db_rows, dict) else None
    if tool is None:
        tool = await get_tool_by_name(name)
    if tool is not None and _source_of_row(tool) == "http":
        if not tool.enabled:
            return {"error": "工具未启用"}
        try:
            return await execute_http_tool(tool, args)
        except Exception as e:  # noqa: BLE001  HTTP 工具异常兜底，不中断对话
            return {"error": str(e)}
    if tool is not None and _source_of_row(tool) == "script":
        if not tool.enabled:
            return {"error": "工具未启用"}
        # 运行时同样受平台总开关约束：开关关闭且当前用户非超管时禁止执行
        allowed, policies = await get_script_safety_config()
        if not allowed and not await _is_superuser_by_id(user_id):
            return {"error": "平台已禁用脚本工具"}
        try:
            return await execute_script_tool(tool, args or {}, policies)
        except Exception as e:  # noqa: BLE001  脚本异常兜底，不中断对话
            return {"error": str(e)}
    return {"error": f"未知工具：{name}"}


class AiToolService:

    @classmethod
    async def get_agno_config_map(cls) -> dict[str, dict]:
        """取 Agno 工具行的 ``{工具名: 已存 config}`` 映射，供精选规格就绪判定。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiToolModel.name, AiToolModel.config).where(
                        AiToolModel.is_deleted.is_(False),
                        AiToolModel.source == "agno",
                    )
                )
            ).all()
        return {name: (cfg or {}) for name, cfg in rows}

    @classmethod
    async def list_tools(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiToolModel)
                    .where(AiToolModel.is_deleted.is_(False))
                    .order_by(AiToolModel.kind.asc(), AiToolModel.id.asc())
                )
            ).scalars().all()
            return [_to_dict(t) for t in rows]

    @classmethod
    async def _load(cls, tool_id: int) -> AiToolModel:
        async with async_db_session() as db:
            t = await db.get(AiToolModel, tool_id)
            if not t or t.is_deleted:
                raise CustomException(msg="工具不存在")
            return t

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            exists = await db.scalar(select(AiToolModel).where(AiToolModel.name == data.name))
            if exists:
                raise CustomException(msg=f"工具名已存在：{data.name}")
            kind = data.kind or "http"
            if kind == "script":
                allowed, policies = await get_script_safety_config(db)
                _assert_script_allowed(auth, allowed)
                _validate_script(getattr(data, "code", None), policies)
            source = getattr(data, "source", None) or (
                "http" if kind == "http" else ("script" if kind == "script" else "system")
            )
            t = AiToolModel(
                name=data.name,
                kind=kind,
                source=source,
                config=getattr(data, "config", None),
                method=(data.method or "GET").upper(),
                url=data.url or "",
                headers=data.headers,
                body_type=(data.body_type or "json").lower(),
                params_schema=data.params_schema,
                code=getattr(data, "code", None) or "",
                timeout=int(getattr(data, "timeout", None) or 10),
                enabled=data.enabled,
                description=getattr(data, "description", None),
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(t)
            await db.flush()
            return _to_dict(t)

    @classmethod
    async def update(cls, tool_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            t = await db.get(AiToolModel, tool_id)
            if not t or t.is_deleted:
                return None
            for key in ("name", "params_schema", "enabled", "description"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(t, key, val)
            # 来源：仅在显式传入时更新
            if getattr(data, "source", None):
                t.source = data.source
            # 配置单独合并：掩码/空值保留原密文，未出现键删除，其余覆盖
            if getattr(data, "config", None) is not None:
                t.config = _merge_config(t.config, data.config)
            # 请求头单独合并：掩码/空值保留原密文，未出现键删除，其余覆盖
            if data.headers is not None:
                t.headers = _merge_headers(t.headers, data.headers)
            if data.method is not None:
                t.method = data.method.upper()
            if data.url is not None:
                t.url = data.url
            if data.body_type is not None:
                t.body_type = data.body_type.lower()
            if getattr(data, "code", None) is not None:
                t.code = data.code
            if getattr(data, "timeout", None) is not None:
                t.timeout = data.timeout
            # 脚本工具：更新后仍需通过静态校验（含平台总开关 + 策略）
            if (t.kind or "") == "script":
                allowed, policies = await get_script_safety_config(db)
                _assert_script_allowed(auth, allowed)
                _validate_script(t.code, policies)
            # 启用态一律要求就绪（含高危门禁），避免绕过 toggle 把高危工具打开
            if t.enabled:
                _assert_enableable(t)
            t.updated_id = auth.user.id
            await db.flush()
            return _to_dict(t)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for tid in ids:
                t = await db.get(AiToolModel, tid)
                if t:
                    await db.delete(t)

    @classmethod
    async def toggle(cls, tool_id: int, enabled: bool, auth) -> dict | None:
        async with async_db_session.begin() as db:
            t = await db.get(AiToolModel, tool_id)
            if not t or t.is_deleted:
                return None
            # 启用前必须就绪：缺依赖/缺配置或高危门禁关闭时拒绝，防止一键开启任意代码执行
            if enabled:
                # 脚本工具另受平台总开关约束（开关关闭且非超管时不可启用）
                if (t.kind or "") == "script":
                    allowed, _ = await get_script_safety_config(db)
                    _assert_script_allowed(auth, allowed)
                _assert_enableable(t)
            t.enabled = bool(enabled)
            t.updated_id = auth.user.id
            await db.flush()
            return _to_dict(t)

    @classmethod
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用工具。启用时跳过未就绪(高危/缺配置)的项。"""
        async with async_db_session.begin() as db:
            # 脚本工具批量启用同样受平台总开关约束（开关关闭且非超管时跳过脚本项）
            script_allowed = True
            if enabled:
                script_allowed, _ = await get_script_safety_config(db)
            count = 0
            for tid in ids:
                t = await db.get(AiToolModel, tid)
                if not t or t.is_deleted:
                    continue
                if enabled:
                    try:
                        if (t.kind or "") == "script":
                            _assert_script_allowed(auth, script_allowed)
                        _assert_enableable(t)
                    except CustomException:
                        continue  # 未就绪/受总开关限制的项跳过，不阻断其它
                t.enabled = bool(enabled)
                t.updated_id = getattr(getattr(auth, "user", None), "id", None)
                count += 1
            return count

    @classmethod
    async def test(cls, tool_id: int, auth) -> dict:
        """测试工具：内置工具返回 schema，HTTP 工具发起一次真实请求，脚本工具空参试运行。"""
        t = await cls._load(tool_id)
        if (t.kind or "builtin") == "builtin":
            entry = TOOL_REGISTRY.get(t.name)
            if not entry:
                raise CustomException(msg=f"内置工具未注册：{t.name}")
            return {"kind": "builtin", "message": "内置工具已注册", "schema": entry["schema"]}
        if (t.kind or "") == "script":
            allowed, policies = await get_script_safety_config()
            _assert_script_allowed(auth, allowed)
            return {
                "kind": "script",
                "result": await execute_script_tool(t, {}, policies),
            }
        if not t.url:
            raise CustomException(msg="URL 不能为空")
        return {"kind": "http", "result": await execute_http_tool(t, {})}

    @classmethod
    async def test_script(cls, tool_id: int, args: dict | None, auth) -> dict:
        """试运行脚本工具（可带参数），返回 ``{ok, result|error}``。"""
        t = await cls._load(tool_id)
        if (t.kind or "") != "script":
            raise CustomException(msg="该工具不是脚本工具")
        from .script_executor import validate as validate_script

        allowed, policies = await get_script_safety_config()
        _assert_script_allowed(auth, allowed)
        try:
            validate_script(t.code or "", policies)
            result = await execute_script_tool(t, args or {}, policies)
            return {"ok": True, "result": result}
        except CustomException as e:
            return {"ok": False, "error": e.msg}

    @classmethod
    async def inspect_script(cls, code: str | None) -> dict:
        """解析脚本 run 签名，提取参数供前端自动生成参数表与 schema。"""
        _, policies = await get_script_safety_config()
        return _inspect_script(code, policies)

    @classmethod
    async def format_script(cls, code: str | None) -> str:
        """格式化脚本源码（ruff）。"""
        return _format_script(code)
