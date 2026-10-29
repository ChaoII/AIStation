"""AI 集成开放平台 —— OAuth 2.1（模式 C）数据面鉴权依赖。

数据面仅接受 ``Authorization: Bearer <委托 access_token>``（**纯 token，无冒号**），
区别于应用凭证 ``appid:appkey``（见 :mod:`auth`）。解析失败 / token 无效 / 已撤销 /
已过期，一律抛 401「鉴权失败」，**不区分失败原因**（防枚举）。

- :func:`get_oauth_api_auth`：FastAPI 依赖——解析 Bearer -> 查 access token 行
  （未撤销、未过期）-> 构造带 ``user_id``（= OAuth sub）与 ``oauth_scope`` 的
  :class:`AppContext`，``owner_user_id`` 置为 ``sub`` 以复用现有 visible 过滤。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import Header
from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .auth import AppContext
from .oauth_model import AiIntegrationOauthTokenModel
from .oauth_server import OAuthClientService, _hash
from .registry import resolve_channels


def _parse_oauth_bearer(authorization: str | None) -> str | None:
    """解析 ``Authorization: Bearer <token>``，返回纯 token；无效返回 None。

    OAuth token 由 ``secrets.token_urlsafe`` 生成，**不含冒号**；若含冒号则视为
    非 OAuth 凭证（可能是 ``appid:appkey``），返回 None 交由应用凭证路径处理。
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token or ":" in token:
        return None
    return token


async def _ctx_from_oauth_token(token: str) -> AppContext | None:
    """按散列查 access token 行，构造 :class:`AppContext`；无效返回 None。"""
    token_hash = _hash(token)
    async with async_db_session() as db:
        row = (
            await db.execute(
                select(AiIntegrationOauthTokenModel).where(
                    AiIntegrationOauthTokenModel.token_hash == token_hash,
                    AiIntegrationOauthTokenModel.token_type == "access",
                    AiIntegrationOauthTokenModel.revoked.is_(False),
                )
            )
        ).scalars().first()
        if row is None or row.expires_at < datetime.now():
            return None
        client = await OAuthClientService.get_client(row.client_id)
        if client is None:
            return None
        grants = set(row.scope or [])
        return AppContext(
            app_id=client.id,
            appid=client.client_id,
            grants=grants,
            channels=resolve_channels(None, grants),
            quota=None,
            app={},
            source_type="oauth",
            owner_user_id=row.user_id,  # OAuth sub：复用 B 可见性（owner 换成 token.sub）
            user_id=row.user_id,
            oauth_scope=grants,
        )


async def get_oauth_api_auth(authorization: str | None = Header(None)) -> AppContext:
    """FastAPI 依赖：解析并校验 OAuth 委托 Bearer token，返回 :class:`AppContext`。

    失败（无头 / 非 Bearer / token 无效 / 已撤销 / 已过期 / client 被删）一律抛
    ``CustomException(msg="鉴权失败", code=10401, status_code=401)``。
    """
    token = _parse_oauth_bearer(authorization)
    if token is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    ctx = await _ctx_from_oauth_token(token)
    if ctx is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    return ctx
