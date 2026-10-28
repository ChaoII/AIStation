"""资产嵌入鉴权依赖（纯逻辑 + FastAPI 依赖）。

与开放平台「应用」无关：``/ai/embed/*`` 凭**资产令牌**（独立绑定 ``kind + target_id``）
鉴权，不再走 ``appid:appkey`` 换票。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Header
from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .embed import AssetEmbedService
from .model import AiAssetAccessTokenModel
from .service import hash_asset_token


@dataclass
class EmbedContext:
    """资产嵌入令牌鉴权成功后的上下文（单个目标最小权限）。

    Attributes:
        token_id: 令牌行主键。
        kind: 嵌入形态（agent/workflow）。
        target_id: 嵌入目标主键（签发时绑定）。
        expires_at: 令牌过期时间。
        token_hash12: 令牌散列前 12 位（限流键/审计脱敏标识）。
    """

    token_id: int
    kind: str
    target_id: int
    expires_at: datetime
    token_hash12: str


async def get_embed_ctx(authorization: str | None = Header(None)) -> EmbedContext:
    """FastAPI 依赖：解析并校验嵌入 ``Authorization: Bearer <asset_token>``。

    校验链：散列查资产令牌 → 未吊销且未过期 → 目标（agent/workflow）存在且启用。
    任一失败统一抛 401（不区分原因，避免令牌枚举）；
    成功后累加 ``use_count`` 并刷新 ``last_used_at``。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    raw = authorization[7:].strip()
    if not raw:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)

    token_hash = hash_asset_token(raw)
    now = datetime.now()
    async with async_db_session.begin() as db:
        row = (
            await db.execute(
                select(AiAssetAccessTokenModel).where(
                    AiAssetAccessTokenModel.token_hash == token_hash,
                    AiAssetAccessTokenModel.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if row is None or row.revoked or row.expires_at <= now:
            raise CustomException(msg="鉴权失败", code=10401, status_code=401)
        # 目标存在且启用（agent/workflow），否则视为鉴权失败
        target = await AssetEmbedService.get_target(row.kind, row.target_id)
        if target is None or not target.get("enabled"):
            raise CustomException(msg="鉴权失败", code=10401, status_code=401)
        row.use_count = (row.use_count or 0) + 1
        row.last_used_at = now
        return EmbedContext(
            token_id=row.id,
            kind=row.kind,
            target_id=row.target_id,
            expires_at=row.expires_at,
            token_hash12=token_hash[:12],
        )
