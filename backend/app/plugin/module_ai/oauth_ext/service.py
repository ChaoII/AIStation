"""AI 集成开放平台 —— 阶段 3a：外部 OAuth 服务与用户授权服务层。

- :class:`OAuthExtService`：外部服务 CRUD + 用户授权（connect/callback/refresh/revoke）
  + 工具调用时的 access token 解析（``resolve_ext_access_token``）。
- 安全：外部 access/refresh 用 Fernet 加密（可还原）；client secret 既存散列也存
  加密明文一次（换取时需用它）。
"""
from __future__ import annotations

import hashlib
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiOauthExtServiceModel, AiOauthExtTokenModel
from .security import decrypt_secret, encrypt_secret


def _hash_secret(secret: str) -> str:
    """sha256 hex，用于 client secret 散列（不存明文）。"""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _service_to_dict(svc: AiOauthExtServiceModel, *, secret: str | None = None) -> dict:
    """服务转对外 dict，**不含** ``client_secret_hash``/``client_secret_enc``。"""
    data = {
        "id": svc.id,
        "name": svc.name,
        "authorize_url": svc.authorize_url,
        "token_url": svc.token_url,
        "client_id": svc.client_id,
        "redirect_uri": svc.redirect_uri,
        "default_scopes": svc.default_scopes or [],
        "userinfo_url": svc.userinfo_url,
        "enabled": svc.enabled,
        "created_time": svc.created_time,
    }
    if secret is not None:
        data["client_secret"] = secret  # 仅创建时返回一次明文
    return data


class OAuthExtService:
    """外部 OAuth 服务连接 + 用户授权 token 管理。"""

    # ---------------- 外部服务 CRUD（管理面） ----------------
    @classmethod
    async def create_service(cls, data, auth) -> dict:
        """创建外部服务：返回一次性明文 client_secret；存散列 + 加密一次（换取用）。"""
        secret = data.client_secret
        async with async_db_session.begin() as db:
            dup = await db.scalar(
                select(AiOauthExtServiceModel).where(
                    AiOauthExtServiceModel.name == data.name,
                    AiOauthExtServiceModel.is_deleted.is_(False),
                )
            )
            if dup:
                raise CustomException(msg=f"服务名称已存在：{data.name}", code=10400, status_code=400)
            row = AiOauthExtServiceModel(
                name=data.name,
                authorize_url=data.authorize_url,
                token_url=data.token_url,
                client_id=data.client_id,
                client_secret_enc=encrypt_secret(settings.SECRET_KEY, data.client_secret),
                client_secret_hash=_hash_secret(data.client_secret),
                redirect_uri=data.redirect_uri,
                default_scopes=list(dict.fromkeys(data.default_scopes or [])),
                userinfo_url=data.userinfo_url,
                enabled=bool(data.enabled),
                created_id=getattr(getattr(auth, "user", None), "id", None),
                updated_id=getattr(getattr(auth, "user", None), "id", None),
            )
            db.add(row)
            await db.flush()
            return _service_to_dict(row, secret=secret)

    @classmethod
    async def list_services(cls) -> list[dict]:
        """列出全部未删除的外部服务（不含 secret）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiOauthExtServiceModel)
                    .where(AiOauthExtServiceModel.is_deleted.is_(False))
                    .order_by(AiOauthExtServiceModel.id.desc())
                )
            ).scalars().all()
            return [_service_to_dict(r) for r in rows]

    @classmethod
    async def get_service(cls, service_id: int) -> AiOauthExtServiceModel | None:
        """按主键取外部服务 ORM 行（未删除）。"""
        async with async_db_session() as db:
            return (
                await db.execute(
                    select(AiOauthExtServiceModel).where(
                        AiOauthExtServiceModel.id == service_id,
                        AiOauthExtServiceModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()

    @classmethod
    async def update_service(cls, service_id: int, data, auth) -> dict:
        """更新外部服务（仅更新显式传入字段；改 client_secret 则重算散列+加密）。"""
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiOauthExtServiceModel).where(
                        AiOauthExtServiceModel.id == service_id,
                        AiOauthExtServiceModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if row is None:
                raise CustomException(msg="服务不存在", code=10404, status_code=404)
            if data.name is not None and data.name != row.name:
                dup = await db.scalar(
                    select(AiOauthExtServiceModel).where(
                        AiOauthExtServiceModel.name == data.name,
                        AiOauthExtServiceModel.is_deleted.is_(False),
                        AiOauthExtServiceModel.id != row.id,
                    )
                )
                if dup:
                    raise CustomException(msg=f"服务名称已存在：{data.name}", code=10400, status_code=400)
                row.name = data.name
            if data.authorize_url is not None:
                row.authorize_url = data.authorize_url
            if data.token_url is not None:
                row.token_url = data.token_url
            if data.client_id is not None:
                row.client_id = data.client_id
            if data.client_secret is not None:
                row.client_secret_enc = encrypt_secret(settings.SECRET_KEY, data.client_secret)
                row.client_secret_hash = _hash_secret(data.client_secret)
            if data.redirect_uri is not None:
                row.redirect_uri = data.redirect_uri
            if data.default_scopes is not None:
                row.default_scopes = list(dict.fromkeys(data.default_scopes))
            if data.userinfo_url is not None:
                row.userinfo_url = data.userinfo_url or None
            if data.enabled is not None:
                row.enabled = bool(data.enabled)
            row.updated_time = datetime.now()
            updater_id = getattr(getattr(auth, "user", None), "id", None)
            if updater_id:
                row.updated_id = updater_id
            await db.flush()
            return _service_to_dict(row)

    @classmethod
    async def delete_service(cls, service_id: int) -> None:
        """软删外部服务。"""
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiOauthExtServiceModel).where(
                        AiOauthExtServiceModel.id == service_id,
                        AiOauthExtServiceModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if row is None:
                raise CustomException(msg="服务不存在", code=10404, status_code=404)
            row.is_deleted = True
            row.deleted_time = datetime.now()

    # ------------- 用户授权 -------------
    # 进程内 state 存储（TTL 600s）。OAuth state 短生命周期、临时性，用内存即可；
    # 与平台现有 state 机制一致的 TTL 语义。
    _STATE_TTL = 600
    _states: dict[str, tuple[int, float]] = {}  # state -> (service_id, expire_ts)

    @classmethod
    def _purge_states(cls) -> None:
        now = time.time()
        cls._states = {k: v for k, v in cls._states.items() if v[1] > now}

    @classmethod
    def _save_state(cls, state: str, service_id: int) -> None:
        cls._purge_states()
        cls._states[state] = (service_id, time.time() + cls._STATE_TTL)

    @classmethod
    def _consume_state(cls, service_id: int, state: str) -> bool:
        """校验并消费 state（一次性）；不匹配/过期返回 False。"""
        cls._purge_states()
        item = cls._states.pop(state, None)
        if item is None:
            return False
        return item[0] == service_id

    @classmethod
    def decrypt_client_secret(cls, service: AiOauthExtServiceModel) -> str:
        """解密 client secret 明文（仅换取时用，不回读）。"""
        if not service.client_secret_enc:
            raise CustomException(msg="服务未配置 client secret", code=10400, status_code=400)
        return decrypt_secret(settings.SECRET_KEY, service.client_secret_enc)

    @classmethod
    async def connect_redirect(cls, service_id: int, user_id: int | None) -> dict:
        """生成一次性 state 并构造外部授权 URL（返回给前端跳转）。"""
        service = await cls.get_service(service_id)
        if service is None or not service.enabled:
            raise CustomException(msg="服务不存在或已停用", code=10400, status_code=400)
        state = f"st_{secrets.token_urlsafe(24)}"
        cls._save_state(state, service_id)
        scopes = " ".join(service.default_scopes or [])
        query = urllib.parse.urlencode({
            "client_id": service.client_id,
            "redirect_uri": service.redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state,
        })
        separator = "&" if "?" in service.authorize_url else "?"
        authorize_url = f"{service.authorize_url}{separator}{query}"
        return {"authorize_url": authorize_url, "state": state}

    @classmethod
    async def _token_request(cls, service: AiOauthExtServiceModel, payload: dict) -> dict:
        """POST 外部 token 端点（可被测试 monkeypatch）。"""
        client_secret = cls.decrypt_client_secret(service)
        data = {
            "grant_type": payload.get("grant_type", "authorization_code"),
            "client_id": service.client_id,
            "client_secret": client_secret,
            **{k: v for k, v in payload.items() if k not in ("grant_type",)},
        }
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(service.token_url, data=data)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    async def get_or_create_token_row(
        cls, service_id: int, user_id: int,
        access: str, refresh: str | None, scope: list, provider_user_id: str | None = None,
        expires_in: int | None = None, db=None,
    ) -> AiOauthExtTokenModel:
        """upsert 用户×服务 的 token 行（access/refresh 加密存储）。"""
        expires_at = None
        if expires_in is not None:
            expires_at = datetime.now() + timedelta(seconds=expires_in)

        async def _with(db_session):
            row = (
                await db_session.execute(
                    select(AiOauthExtTokenModel).where(
                        AiOauthExtTokenModel.service_id == service_id,
                        AiOauthExtTokenModel.user_id == user_id,
                    )
                )
            ).scalars().first()
            if row is None:
                row = AiOauthExtTokenModel(
                    service_id=service_id, user_id=user_id,
                    access_token_enc=encrypt_secret(settings.SECRET_KEY, access),
                    refresh_token_enc=(encrypt_secret(settings.SECRET_KEY, refresh) if refresh else None),
                    access_expires_at=expires_at,
                    scope=scope or [],
                    provider_user_id=provider_user_id,
                    revoked=False,
                )
                db_session.add(row)
            else:
                row.access_token_enc = encrypt_secret(settings.SECRET_KEY, access)
                if refresh:
                    row.refresh_token_enc = encrypt_secret(settings.SECRET_KEY, refresh)
                row.access_expires_at = expires_at
                row.scope = scope or []
                if provider_user_id:
                    row.provider_user_id = provider_user_id
                row.revoked = False
                row.revoked_at = None
                row.updated_time = datetime.now()
            await db_session.flush()
            return row

        if db is not None:
            return await _with(db)
        async with async_db_session.begin() as dbs:
            return await _with(dbs)

    @classmethod
    async def handle_callback(
        cls, service_id: int, user_id: int, code: str, state: str, redirect_uri: str | None = None,
    ) -> dict:
        """校验 state -> 用 code 换 access/refresh -> 加密落库 -> 返回连接成功信息。"""
        if not cls._consume_state(service_id, state):
            raise CustomException(msg="state 校验失败", code=10400, status_code=400)
        service = await cls.get_service(service_id)
        if service is None:
            raise CustomException(msg="服务不存在", code=10404, status_code=404)
        if redirect_uri is not None and redirect_uri != service.redirect_uri:
            raise CustomException(msg="回调地址不匹配", code=10400, status_code=400)
        payload = {"grant_type": "authorization_code", "code": code, "redirect_uri": service.redirect_uri}
        tok = await cls._token_request(service, payload)
        access = tok.get("access_token")
        if not access:
            raise CustomException(msg="换取 access token 失败", code=10400, status_code=400)
        await cls.get_or_create_token_row(
            service_id, user_id,
            access=access,
            refresh=tok.get("refresh_token"),
            scope=tok.get("scope", "").split() if tok.get("scope") else [],
            expires_in=tok.get("expires_in"),
        )
        return {"connected": True, "service_id": service_id}
