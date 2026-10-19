"""MCP 服务器服务：配置 CRUD 与连接测试。

说明：MCP 服务器为**个人配置**（按 ``created_id`` 过滤），Agent 通过 ``mcp_ids`` 绑定。
连接测试只做“可达性探测”，不建立真实 MCP 会话（真实会话在 Agent 运行时由 agno 建立）。
"""
import shutil
from datetime import datetime

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.bindings import detach_from_agents

from .model import AiMcpServerModel

TRANSPORTS = ("stdio", "sse", "streamable-http")


def _to_dict(s: AiMcpServerModel) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "transport": s.transport or "streamable-http",
        "command": s.command or "",
        "args": s.args or [],
        "env": s.env or {},
        "url": s.url or "",
        "headers": s.headers or {},
        "auth_type": s.auth_type or "none",
        "enabled": bool(s.enabled),
        "description": s.description or "",
        "created_time": s.created_time,
    }


def _validate(transport: str | None, command: str | None, url: str | None) -> None:
    """按传输方式校验必填项。"""
    transport = transport or "streamable-http"
    if transport not in TRANSPORTS:
        raise CustomException(msg=f"不支持的传输方式：{transport}")
    if transport == "stdio":
        if not (command or "").strip():
            raise CustomException(msg="stdio 方式必须填写启动命令")
    else:
        if not (url or "").strip():
            raise CustomException(msg=f"{transport} 方式必须填写服务地址")


async def test_connection(server: AiMcpServerModel) -> dict:
    """探测 MCP 服务器可达性。

    - stdio：检查命令是否在 PATH 中可执行；
    - sse/streamable-http：GET 地址，状态码 < 500 视为可达（401/403 亦说明服务在线）。
    """
    transport = server.transport or "streamable-http"
    if transport == "stdio":
        command = (server.command or "").strip()
        if not command:
            return {"reachable": False, "detail": "未配置启动命令"}
        found = shutil.which(command)
        if not found:
            return {"reachable": False, "detail": f"命令不存在或不可执行：{command}"}
        return {"reachable": True, "detail": f"命令可用：{found}"}

    url = (server.url or "").strip()
    if not url:
        return {"reachable": False, "detail": "未配置服务地址"}
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as c:
            resp = await c.get(url, headers={str(k): str(v) for k, v in (server.headers or {}).items()})
        if resp.status_code < 500:
            return {"reachable": True, "detail": f"HTTP {resp.status_code}"}
        return {"reachable": False, "detail": f"HTTP {resp.status_code}"}
    except Exception as e:  # noqa: BLE001  探测失败不抛异常，返回不可达
        return {"reachable": False, "detail": f"连接失败：{type(e).__name__}: {e}"}


class McpService:

    @classmethod
    async def list_servers(cls, user_id: int) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiMcpServerModel)
                    .where(
                        AiMcpServerModel.is_deleted.is_(False),
                        AiMcpServerModel.created_id == user_id,
                    )
                    .order_by(AiMcpServerModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(s) for s in rows]

    @classmethod
    async def get(cls, server_id: int, user_id: int) -> dict | None:
        async with async_db_session() as db:
            s = await db.get(AiMcpServerModel, server_id)
            if not s or s.is_deleted or s.created_id != user_id:
                return None
            return _to_dict(s)

    @classmethod
    async def create(cls, data, auth) -> dict:
        _validate(data.transport, data.command, data.url)
        async with async_db_session.begin() as db:
            exists = await db.scalar(
                select(AiMcpServerModel).where(
                    AiMcpServerModel.name == data.name,
                    AiMcpServerModel.is_deleted.is_(False),
                )
            )
            if exists:
                raise CustomException(msg=f"服务器名已存在：{data.name}")
            s = AiMcpServerModel(
                name=data.name,
                transport=data.transport or "streamable-http",
                command=data.command or "",
                args=data.args or [],
                env=data.env,
                url=data.url or "",
                headers=data.headers,
                auth_type=data.auth_type or "none",
                enabled=data.enabled,
                description=data.description or "",
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(s)
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def update(cls, server_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(AiMcpServerModel, server_id)
            if not s or s.is_deleted:
                return None
            if s.created_id != auth.user.id:
                raise CustomException(msg="只能编辑自己的 MCP 服务器")
            merged_transport = data.transport if data.transport is not None else s.transport
            merged_command = data.command if data.command is not None else s.command
            merged_url = data.url if data.url is not None else s.url
            _validate(merged_transport, merged_command, merged_url)
            if data.name is not None and data.name != s.name:
                dup = await db.scalar(
                    select(AiMcpServerModel).where(
                        AiMcpServerModel.name == data.name,
                        AiMcpServerModel.is_deleted.is_(False),
                        AiMcpServerModel.id != server_id,
                    )
                )
                if dup:
                    raise CustomException(msg=f"服务器名已存在：{data.name}")
            for key in ("name", "transport", "command", "args", "env", "url", "headers", "auth_type", "enabled", "description"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(s, key, val)
            s.updated_id = auth.user.id
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def delete(cls, ids: list[int], user_id: int) -> None:
        """软删除本人的 MCP 服务器（他人行静默跳过；列表已按 is_deleted 过滤）。"""
        async with async_db_session.begin() as db:
            now = datetime.now()
            deleted_ids: list[int] = []
            for sid in ids:
                s = await db.get(AiMcpServerModel, sid)
                if s and not s.is_deleted and s.created_id == user_id:
                    deleted_ids.append(s.id)
                    s.is_deleted = True
                    s.deleted_time = now
                    s.deleted_id = user_id
                    s.updated_id = user_id
                    # 释放唯一名：允许重新创建同名 MCP 服务器
                    suffix = f"__deleted_{s.id}_{int(now.timestamp())}"
                    s.name = f"{(s.name or '')[: 128 - len(suffix)]}{suffix}"
            # 智能体按 MCP id 绑定，删除后一并摘除
            await detach_from_agents(db, mcp_ids=deleted_ids)

    @classmethod
    async def toggle(cls, server_id: int, enabled: bool, auth) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(AiMcpServerModel, server_id)
            if not s or s.is_deleted:
                return None
            if s.created_id != auth.user.id:
                raise CustomException(msg="只能操作自己的 MCP 服务器")
            s.enabled = bool(enabled)
            s.updated_id = auth.user.id
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def test(cls, server_id: int, user_id: int) -> dict:
        async with async_db_session() as db:
            s = await db.get(AiMcpServerModel, server_id)
            if not s or s.is_deleted:
                raise CustomException(msg="MCP 服务器不存在")
            if s.created_id != user_id:
                raise CustomException(msg="只能测试自己的 MCP 服务器")
            result = await test_connection(s)
            return {"server_id": server_id, **result}

    @classmethod
    async def enabled_servers(cls, ids: list[int], user_id: int) -> list[dict]:
        """按 id 批量取启用中的 MCP 服务器（供 Agent 运行时装配）。

        仅返回当前用户自己创建的服务器，避免引用他人配置（可能含密钥）。
        """
        if not ids:
            return []
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiMcpServerModel).where(
                        AiMcpServerModel.id.in_(ids),
                        AiMcpServerModel.enabled.is_(True),
                        AiMcpServerModel.is_deleted.is_(False),
                        AiMcpServerModel.created_id == user_id,
                    )
                )
            ).scalars().all()
            return [_to_dict(s) for s in rows]
