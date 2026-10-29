"""AI 集成开放平台 —— OAuth 2.1（模式 C）服务层。

- :class:`OAuthClientService`：OAuth 客户端 CRUD + 凭证校验 + 授权码签发。
- :class:`OAuthTokenService`：授权码换 token / refresh 续期 / 撤销（Task 3-5 补充）。

设计见 ``docs/superpowers/specs/2026-10-29-develop-oauth-server-design.md``。
token / client secret / 授权码**只存 sha256 散列**，明文仅在签发响应返回一次。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .oauth_model import AiIntegrationOauthClientModel, AiIntegrationOauthTokenModel
from .registry import is_valid_capability_code

#: client_id 随机字符表：去掉易混淆的 0/O/1/l/I。
_CLIENT_ID_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")

#: OAuth 委托 token 有效期（秒）。
OAUTH_ACCESS_TOKEN_TTL = 60 * 60  # access：1 小时
OAUTH_REFRESH_TOKEN_TTL = 60 * 60 * 24 * 30  # refresh：30 天
#: 授权码有效期（秒）。
OAUTH_AUTH_CODE_TTL = 60 * 10  # 授权码：10 分钟


def _generate_client_id() -> str:
    """生成 OAuth client_id：``oc_`` + 12 位去易混淆字符随机串（不含冒号）。"""
    return "oc_" + "".join(secrets.choice(_CLIENT_ID_ALPHABET) for _ in range(12))


def _generate_client_secret() -> str:
    """生成明文 client secret（调用方只能拿到这一次，库中仅存散列）。"""
    return secrets.token_urlsafe(32)


def _generate_token() -> str:
    """生成 access / refresh / 授权码明文（URL 安全，不含冒号）。"""
    return secrets.token_urlsafe(32)


def _hash(value: str) -> str:
    """对凭证/授权码做 sha256 散列（存库用，不存明文）。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_to_dict(client: AiIntegrationOauthClientModel, *, secret: str | None = None) -> dict:
    """把 OAuth 客户端转成对外 dict（**绝不包含** ``client_secret_hash``）。"""
    data = {
        "id": client.id,
        "uuid": client.uuid,
        "client_id": client.client_id,
        "name": client.name,
        "description": client.description or "",
        "enabled": bool(client.enabled),
        "redirect_uris": client.redirect_uris or [],
        "allow_pkce": bool(client.allow_pkce),
        "requires_approval": bool(client.requires_approval),
        "max_scope": client.max_scope,
        "expire_at": client.expire_at,
        "created_time": client.created_time,
        "updated_time": client.updated_time,
    }
    if secret is not None:
        data["client_secret"] = secret
    return data


def _validate_scope(scope: list[str] | None, client: AiIntegrationOauthClientModel) -> list[str]:
    """校验并归一 scope：全部能力码须在注册表中，且 ⊆ client.max_scope（非空时）。"""
    scope = scope or []
    for code in scope:
        if not is_valid_capability_code(code):
            raise CustomException(msg=f"能力码不合法：{code}", code=10400, status_code=400)
    if client.max_scope:
        allowed = set(client.max_scope)
        for code in scope:
            if code not in allowed:
                raise CustomException(
                    msg=f"超出客户端可授权范围：{code}", code=10400, status_code=400
                )
    return sorted(set(scope))


class OAuthClientService:
    """OAuth 客户端：CRUD + 凭证校验 + 授权码签发。"""

    # ---------------- CRUD ----------------
    @classmethod
    async def create_client(cls, data, auth) -> dict:
        """创建 OAuth 客户端：校验 name 唯一、生成 client_id/secret、存散列、返回一次性明文。"""
        client_id = _generate_client_id()
        secret = _generate_client_secret()
        redirect_uris = list(dict.fromkeys(data.redirect_uris or []))
        async with async_db_session.begin() as db:
            dup = await db.scalar(
                select(AiIntegrationOauthClientModel).where(
                    AiIntegrationOauthClientModel.name == data.name,
                    AiIntegrationOauthClientModel.is_deleted.is_(False),
                )
            )
            if dup:
                raise CustomException(msg=f"客户端名称已存在：{data.name}", code=10400, status_code=400)
            row = AiIntegrationOauthClientModel(
                client_id=client_id,
                client_secret_hash=_hash(secret),
                name=data.name,
                description=data.description,
                enabled=True,
                redirect_uris=redirect_uris,
                allow_pkce=True if data.allow_pkce is None else bool(data.allow_pkce),
                requires_approval=True if data.requires_approval is None else bool(data.requires_approval),
                max_scope=data.max_scope,
                expire_at=data.expire_at,
                created_id=auth.user.id if auth and getattr(auth, "user", None) else None,
                updated_id=auth.user.id if auth and getattr(auth, "user", None) else None,
            )
            db.add(row)
            await db.flush()
            return _client_to_dict(row, secret=secret)

    @classmethod
    async def list_clients(cls) -> list[dict]:
        """列出全部 OAuth 客户端（不含 secret 散列/明文）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiIntegrationOauthClientModel)
                    .where(AiIntegrationOauthClientModel.is_deleted.is_(False))
                    .order_by(AiIntegrationOauthClientModel.id.desc())
                )
            ).scalars().all()
            return [_client_to_dict(c) for c in rows]

    @classmethod
    async def get_client(cls, client_id: str) -> AiIntegrationOauthClientModel | None:
        """按 ``client_id`` 取 OAuth 客户端 ORM 行（未删除）。"""
        async with async_db_session() as db:
            return (
                await db.execute(
                    select(AiIntegrationOauthClientModel).where(
                        AiIntegrationOauthClientModel.client_id == client_id,
                        AiIntegrationOauthClientModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()

    @classmethod
    async def update_client(cls, client_id: str, data, auth) -> dict:
        """更新 OAuth 客户端（仅更新显式传入字段，name 唯一校验收紧）。"""
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiIntegrationOauthClientModel).where(
                        AiIntegrationOauthClientModel.client_id == client_id,
                        AiIntegrationOauthClientModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if row is None:
                raise CustomException(msg="客户端不存在", code=10404, status_code=404)
            if data.name is not None and data.name != row.name:
                dup = await db.scalar(
                    select(AiIntegrationOauthClientModel).where(
                        AiIntegrationOauthClientModel.name == data.name,
                        AiIntegrationOauthClientModel.is_deleted.is_(False),
                        AiIntegrationOauthClientModel.id != row.id,
                    )
                )
                if dup:
                    raise CustomException(msg=f"客户端名称已存在：{data.name}", code=10400, status_code=400)
                row.name = data.name
            if data.description is not None:
                row.description = data.description
            if data.redirect_uris is not None:
                row.redirect_uris = list(dict.fromkeys(data.redirect_uris))
            if data.allow_pkce is not None:
                row.allow_pkce = bool(data.allow_pkce)
            if data.requires_approval is not None:
                row.requires_approval = bool(data.requires_approval)
            if data.max_scope is not None:
                row.max_scope = data.max_scope
            if data.expire_at is not None:
                row.expire_at = data.expire_at
            if data.enabled is not None:
                row.enabled = bool(data.enabled)
            row.updated_time = datetime.now()
            updater_id = getattr(getattr(auth, "user", None), "id", None)
            if updater_id:
                row.updated_id = updater_id
            await db.flush()
            return _client_to_dict(row)

    @classmethod
    async def verify_client_credentials(cls, client_id: str, client_secret: str) -> AiIntegrationOauthClientModel | None:
        """校验 client 凭证：按 client_id 查，校验 enabled / expire_at / 散列比对，任一失败返回 None。"""
        row = await cls.get_client(client_id)
        if row is None:
            return None
        if not row.enabled:
            return None
        now = datetime.now()
        if row.expire_at is not None and row.expire_at < now:
            return None
        if not hmac.compare_digest(_hash(client_secret), row.client_secret_hash):
            return None
        return row

    # ---------------- 授权码签发 ----------------
    @classmethod
    async def issue_authorization_code(
        cls, client: AiIntegrationOauthClientModel, user_id: int, *, scope: list[str], redirect_uri: str | None,
        code_challenge: str | None, code_challenge_method: str | None,
    ) -> dict:
        """校验并签发一次性授权码，落一行 ``token_type='auth'``。

        Args:
            client: 已校验的 OAuth 客户端 ORM 行。
            user_id: 被委托用户 id（``sub``）。
            scope: 用户请求的能力码集合（须 ⊆ client.max_scope）。
            redirect_uri: 授权回调（须在白名单）。
            code_challenge / code_challenge_method: PKCE 参数（client 允许时）。

        Returns:
            ``{"code": ..., "state": ...}``（``state`` 由调用方传入并回传，此处不生成）。
        """
        # redirect_uri 白名单
        if redirect_uri not in (client.redirect_uris or []):
            raise CustomException(msg="回调地址不在白名单内", code=10400, status_code=400)
        # scope 校验
        scope = _validate_scope(scope, client)
        # PKCE：允许时才接受 challenge；S256 优先
        if code_challenge:
            if not client.allow_pkce:
                raise CustomException(msg="该客户端不支持 PKCE", code=10400, status_code=400)
            if code_challenge_method not in ("plain", "S256"):
                raise CustomException(msg="PKCE 方法不合法", code=10400, status_code=400)

        code = _generate_token()
        now = datetime.now()
        async with async_db_session.begin() as db:
            row = AiIntegrationOauthTokenModel(
                client_id=client.client_id,
                oauth_client_id=client.id,
                user_id=user_id,
                token_type="auth",
                token_hash=_hash(code),
                scope=scope,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                auth_code=code,
                auth_code_hash=_hash(code),
                expires_at=now + timedelta(seconds=OAUTH_AUTH_CODE_TTL),
                revoked=False,
            )
            db.add(row)
            await db.flush()
            return {"code": code}


class OAuthTokenService:
    """OAuth 委托 token：授权码换 token / refresh 续期 / 撤销。"""

    # ------------- 授权码 → token 换取 -------------
    @classmethod
    async def exchange_code(
        cls, *, client_id: str, client_secret: str | None, code: str,
        redirect_uri: str | None, code_verifier: str | None,
    ) -> dict:
        """用一次性授权码换取 access + refresh 对（授权码换后失效）。

        校验：client 凭证、授权码存在且未消费、redirect_uri 匹配、PKCE verifier。
        成功后置空 ``auth_code``/``auth_code_hash``（一次性），生成 access/refresh 两行。
        """
        client = await OAuthClientService.verify_client_credentials(client_id, client_secret or "")
        if client is None:
            raise CustomException(msg="鉴权失败", code=10401, status_code=401)

        code_hash = _hash(code)
        async with async_db_session.begin() as db:
            auth_row = (
                await db.execute(
                    select(AiIntegrationOauthTokenModel).where(
                        AiIntegrationOauthTokenModel.client_id == client_id,
                        AiIntegrationOauthTokenModel.token_type == "auth",
                        AiIntegrationOauthTokenModel.auth_code_hash == code_hash,
                        AiIntegrationOauthTokenModel.revoked.is_(False),
                    )
                )
            ).scalars().first()
            if auth_row is None or not auth_row.auth_code:
                raise CustomException(msg="授权码已失效", code=10400, status_code=400)
            # redirect_uri 校验（授权码签发时的必须匹配）
            if redirect_uri != auth_row.redirect_uri:
                raise CustomException(msg="回调地址不匹配", code=10400, status_code=400)
            # 过期校验
            if auth_row.expires_at < datetime.now():
                raise CustomException(msg="授权码已失效", code=10400, status_code=400)
            # PKCE verifier 校验
            if auth_row.code_challenge:
                if not code_verifier:
                    raise CustomException(msg="缺少 PKCE verifier", code=10400, status_code=400)
                if auth_row.code_challenge_method == "S256":
                    if _hash(code_verifier) != auth_row.code_challenge:
                        raise CustomException(msg="PKCE 校验失败", code=10400, status_code=400)
                elif code_verifier != auth_row.code_challenge:  # plain
                    raise CustomException(msg="PKCE 校验失败", code=10400, status_code=400)

            # 一次性：清空授权码
            auth_row.auth_code = None
            auth_row.auth_code_hash = None

            grant_scope = auth_row.scope
            user_id = auth_row.user_id
            redirect = auth_row.redirect_uri
            code_challenge = auth_row.code_challenge

        # 生成 access + refresh（新会话）
        return await cls._issue_access_and_refresh(
            client, user_id, grant_scope, redirect, code_challenge
        )

    @classmethod
    async def _issue_access_and_refresh(
        cls, client: AiIntegrationOauthClientModel, user_id: int,
        scope: list[str], redirect_uri: str | None, code_challenge: str | None,
    ) -> dict:
        """签发 access + refresh 两行（只存散列），返回明文一次。"""
        access_token = _generate_token()
        refresh_token = _generate_token()
        now = datetime.now()
        access_expires = now + timedelta(seconds=OAUTH_ACCESS_TOKEN_TTL)
        refresh_expires = now + timedelta(seconds=OAUTH_REFRESH_TOKEN_TTL)

        async with async_db_session.begin() as db:
            db.add(AiIntegrationOauthTokenModel(
                client_id=client.client_id,
                oauth_client_id=client.id,
                user_id=user_id,
                token_type="access",
                token_hash=_hash(access_token),
                scope=scope,
                redirect_uri=redirect_uri,
                expires_at=access_expires,
                revoked=False,
            ))
            db.add(AiIntegrationOauthTokenModel(
                client_id=client.client_id,
                oauth_client_id=client.id,
                user_id=user_id,
                token_type="refresh",
                token_hash=_hash(refresh_token),
                scope=scope,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                expires_at=refresh_expires,
                revoked=False,
            ))
            await db.flush()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": OAUTH_ACCESS_TOKEN_TTL,
            "scope": sorted(scope),
        }

    # ------------- refresh 续期 -------------
    @classmethod
    async def refresh(
        cls, *, client_id: str, client_secret: str | None, refresh_token: str,
    ) -> dict:
        """用 refresh token 换新 access + refresh 对（旧 refresh 作废，防重放）。"""
        client = await OAuthClientService.verify_client_credentials(client_id, client_secret or "")
        if client is None:
            raise CustomException(msg="鉴权失败", code=10401, status_code=401)

        token_hash = _hash(refresh_token)
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiIntegrationOauthTokenModel).where(
                        AiIntegrationOauthTokenModel.client_id == client_id,
                        AiIntegrationOauthTokenModel.token_type == "refresh",
                        AiIntegrationOauthTokenModel.token_hash == token_hash,
                        AiIntegrationOauthTokenModel.revoked.is_(False),
                    )
                )
            ).scalars().first()
            if row is None or row.expires_at < datetime.now():
                raise CustomException(msg="令牌已失效", code=10401, status_code=401)

            # 旧 refresh 作废
            row.revoked = True
            row.revoked_at = datetime.now()
            row.last_used_at = datetime.now()

            grant_scope = row.scope
            user_id = row.user_id
            redirect = row.redirect_uri
            code_challenge = row.code_challenge

        return await cls._issue_access_and_refresh(
            client, user_id, grant_scope, redirect, code_challenge
        )

    # ------------- 撤销 -------------
    @classmethod
    async def revoke(cls, token: str) -> None:
        """撤销某个 access / refresh token（置 ``revoked``，供用户随时收回委托）。"""
        token_hash = _hash(token)
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiIntegrationOauthTokenModel).where(
                        AiIntegrationOauthTokenModel.token_hash == token_hash,
                        AiIntegrationOauthTokenModel.revoked.is_(False),
                    )
                )
            ).scalars().first()
            if row is None:
                # 幂等：未知/已撤销 token 不报错（RFC 7009 允许）
                return
            row.revoked = True
            row.revoked_at = datetime.now()
