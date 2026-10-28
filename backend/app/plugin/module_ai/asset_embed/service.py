"""资产嵌入令牌服务：签发 / 列表 / 吊销（纯业务，不依赖应用）。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiAssetAccessTokenModel

#: 资产令牌 TTL 缺省/上下限（秒）：缺省 24h，下限 60s，上限 30 天
ASSET_TOKEN_TTL_DEFAULT = 86400
ASSET_TOKEN_TTL_MIN = 60
ASSET_TOKEN_TTL_MAX = 2592000


def generate_asset_token() -> str:
    """生成资产嵌入 access_token 明文（URL 安全、不含冒号）。"""
    return secrets.token_urlsafe(32)


def hash_asset_token(token: str) -> str:
    """计算资产 token 的 sha256 散列（库内只存散列，明文仅签发时返回一次）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clamp_asset_ttl(ttl: int | None) -> int:
    """夹紧签发 TTL：缺省 86400s，下限 60s，上限 2592000s（30 天）。"""
    if ttl is None:
        return ASSET_TOKEN_TTL_DEFAULT
    return max(ASSET_TOKEN_TTL_MIN, min(int(ttl), ASSET_TOKEN_TTL_MAX))


class AssetTokenService:
    """资产嵌入令牌治理（工作台侧）。

    - 令牌独立绑定 ``kind + target_id``，不涉及（也不依赖）开放平台应用。
    - 明文仅签发响应返回一次，库内只存散列。
    """

    @classmethod
    async def issue_token(
        cls,
        kind: str,
        target_id: int,
        ttl: int | None = None,
        issued_by: str = "admin",
    ) -> dict:
        """签发资产令牌：返回 ``{"token", "expires_in", "expires_at"}``（明文仅此一次）。"""
        expires_in = clamp_asset_ttl(ttl)
        token = generate_asset_token()
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        async with async_db_session.begin() as db:
            db.add(
                AiAssetAccessTokenModel(
                    kind=kind,
                    target_id=target_id,
                    token_hash=hash_asset_token(token),
                    expires_at=expires_at,
                    revoked=False,
                    issued_by=issued_by,
                    use_count=0,
                )
            )
        return {
            "token": token,
            "expires_in": expires_in,
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    async def list_tokens(cls, kind: str, target_id: int) -> list[dict]:
        """列出某资产的嵌入令牌（只读元信息，不含明文/散列）。"""
        async with async_db_session() as db:
            rows = (
                (
                    await db.execute(
                        select(AiAssetAccessTokenModel)
                        .where(
                            AiAssetAccessTokenModel.kind == kind,
                            AiAssetAccessTokenModel.target_id == target_id,
                            AiAssetAccessTokenModel.is_deleted.is_(False),
                        )
                        .order_by(AiAssetAccessTokenModel.id.desc())
                    )
                )
                .scalars()
                .all()
            )
        items: list[dict] = []
        for r in rows:
            items.append(
                {
                    "id": r.id,
                    "kind": r.kind,
                    "target_id": r.target_id,
                    "issued_by": r.issued_by,
                    "expires_at": r.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "revoked": bool(r.revoked),
                    "use_count": r.use_count or 0,
                    "last_used_at": r.last_used_at.strftime("%Y-%m-%d %H:%M:%S")
                    if r.last_used_at
                    else None,
                    "created_time": r.created_time.strftime("%Y-%m-%d %H:%M:%S")
                    if r.created_time
                    else None,
                }
            )
        return items

    @classmethod
    async def revoke_token(cls, token_id: int) -> bool:
        """吊销令牌（置 ``revoked=true``，立即生效；保留审计行不物理删）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiAssetAccessTokenModel, token_id)
            if row is None or row.is_deleted:
                return False
            row.revoked = True
            return True
