"""AI 工具服务：内置工具开关 + 自定义 HTTP 工具执行。"""
from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

from .model import AiToolModel


def _to_dict(t: AiToolModel) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "kind": t.kind or "builtin",
        "method": t.method or "GET",
        "url": t.url or "",
        "headers": t.headers,
        "params_schema": t.params_schema,
        "enabled": t.enabled,
        "description": t.description,
    }


def _http_schema(tool: AiToolModel) -> dict:
    """按 params_schema 生成 OpenAI 函数工具 schema。"""
    schema = tool.params_schema or {"type": "object", "properties": {}}
    description = schema.get("description") if isinstance(schema, dict) else None
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": description or f"自定义 HTTP 工具：{tool.name}",
            "parameters": schema,
        },
    }


async def execute_http_tool(tool: AiToolModel, args: dict) -> object:
    """执行自定义 HTTP 工具：URL 路径占位替换 + 剩余参数作为 query/body。"""
    import httpx

    url = tool.url or ""
    headers = {str(k): str(v) for k, v in (tool.headers or {}).items()}
    remaining = {k: v for k, v in (args or {}).items() if f"{{{k}}}" in url}
    for k, v in remaining.items():
        url = url.replace(f"{{{k}}}", str(v))
    query = {k: v for k, v in (args or {}).items() if k not in remaining}
    async with httpx.AsyncClient(timeout=30) as c:
        if (tool.method or "GET").upper() == "POST":
            resp = await c.post(url, json=query, headers=headers)
        else:
            resp = await c.get(url, params=query, headers=headers)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"status": resp.status_code, "text": resp.text[:2000]}


def build_http_tool_fn(tool: AiToolModel):
    """构建可被运行时调用的异步函数（参数即工具入参）。"""

    async def _fn(**kwargs) -> object:
        return await execute_http_tool(tool, kwargs)

    return _fn


async def get_enabled_tool_schemas() -> list[dict]:
    """返回所有启用工具的 OpenAI 函数 schema（内置取注册表，HTTP 按 params_schema）。"""
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

    schemas: list[dict] = []
    for tool in rows:
        if (tool.kind or "builtin") == "builtin":
            entry = TOOL_REGISTRY.get(tool.name)
            if entry:
                schemas.append(entry["schema"])
        else:
            schemas.append(_http_schema(tool))
    return schemas


class AiToolService:

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
            t = AiToolModel(
                name=data.name,
                kind=data.kind or "http",
                method=(data.method or "GET").upper(),
                url=data.url or "",
                headers=data.headers,
                params_schema=data.params_schema,
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
            for key in ("name", "headers", "params_schema", "enabled", "description"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(t, key, val)
            if data.method is not None:
                t.method = data.method.upper()
            if data.url is not None:
                t.url = data.url
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
            t.enabled = bool(enabled)
            t.updated_id = auth.user.id
            await db.flush()
            return _to_dict(t)

    @classmethod
    async def test(cls, tool_id: int) -> dict:
        """测试工具：内置工具返回 schema，HTTP 工具发起一次真实请求。"""
        t = await cls._load(tool_id)
        if (t.kind or "builtin") == "builtin":
            entry = TOOL_REGISTRY.get(t.name)
            if not entry:
                raise CustomException(msg=f"内置工具未注册：{t.name}")
            return {"kind": "builtin", "message": "内置工具已注册", "schema": entry["schema"]}
        if not t.url:
            raise CustomException(msg="URL 不能为空")
        return {"kind": "http", "result": await execute_http_tool(t, {})}
