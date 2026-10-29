"""AI 集成开放平台 —— 阶段 3a：外部 OAuth 服务与用户授权服务层。

- :class:`OAuthExtService`：外部服务 CRUD + 用户授权（connect/callback/refresh/revoke）
  + 工具调用时的 access token 解析（``resolve_ext_access_token``）。
- 安全：外部 access/refresh 用 Fernet 加密（可还原）；client secret 既存散列也存
  加密明文一次（换取时需用它）。
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiOauthExtServiceModel
from .security import encrypt_secret


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

    # ------------- 用户授权（后续任务实现） -------------
    # connect_redirect / handle_callback / refresh_token / revoke / connection_status /
    # resolve_ext_access_token 在 Task 3/4/5 中实现，这里占位。
