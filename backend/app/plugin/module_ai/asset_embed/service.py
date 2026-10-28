"""资产嵌入令牌服务：签发 / 列表 / 吊销 / 更新 / 日志查询（纯业务，不依赖应用）。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import func, select

from app.core.database import async_db_session

from .model import AiAssetAccessTokenModel, AiAssetEmbedLogModel

#: 资产令牌 TTL 缺省/上下限（秒）：缺省 24h，下限 60s，上限 30 天
ASSET_TOKEN_TTL_DEFAULT = 86400
ASSET_TOKEN_TTL_MIN = 60
ASSET_TOKEN_TTL_MAX = 2592000

#: 「永久」令牌的过期时间（远期占位）
ASSET_TOKEN_FOREVER_DATE = datetime(2099, 12, 31, 23, 59, 59)


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


def parse_origin_host(value: str | None) -> str | None:
    """从 ``Origin``/``Referer`` URL 提取 host（去协议/路径/端口）；解析失败返回 ``None``。"""
    if not value:
        return None
    try:
        host = urlparse(value).hostname
    except Exception:  # noqa: BLE001
        return None
    if not host:
        return None
    return host.lower()


def extract_client_ip(request) -> str:
    """归一化客户端来源 IP：优先 ``X-Forwarded-For`` 首段，否则 ``request.client.host``。"""
    fwd = (request.headers.get("x-forwarded-for") or "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return client.host
    return ""


def match_whitelist(
    allow_domains: str | None,
    allow_ips: str | None,
    origin_host: str | None,
    client_ip: str,
) -> bool:
    """白名单判断：域名 + IP 双维度，任一命中放行；两者都空 = 不限。

    - ``allow_domains``/``allow_ips`` 为逗号分隔字符串，大小写/空白不敏感。
    - 域名/IP 均空 → 放行（兼容旧令牌不限制）。
    """
    def _split(v: str | None) -> set[str]:
        return {x.strip().lower() for x in (v or "").split(",") if x.strip()}

    domains = _split(allow_domains)
    ips = _split(allow_ips)
    if not domains and not ips:
        return True
    if origin_host and origin_host.lower() in domains:
        return True
    if client_ip and client_ip.lower() in ips:
        return True
    return False


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
        permanent: bool = False,
        allow_domains: str | None = None,
        allow_ips: str | None = None,
        issued_by: str = "admin",
    ) -> dict:
        """签发资产令牌：返回 ``{"token", "expires_in", "expires_at", "permanent"}``（明文仅此一次）。

        - ``permanent=True`` 时 ``expires_at`` 置为远期占位（2099-12-31），忽略 ``ttl``。
        - 否则 ``expires_in = clamp_asset_ttl(ttl)``（缺省 24h，clamp 上下限不变）。
        """
        if permanent:
            expires_in: int | None = None
            expires_at = ASSET_TOKEN_FOREVER_DATE
        else:
            expires_in = clamp_asset_ttl(ttl)
            expires_at = datetime.now() + timedelta(seconds=expires_in)
        token = generate_asset_token()
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
                    allow_domains=allow_domains,
                    allow_ips=allow_ips,
                )
            )
        return {
            "token": token,
            "expires_in": expires_in,
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "permanent": bool(permanent),
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
                    "allow_domains": r.allow_domains or "",
                    "allow_ips": r.allow_ips or "",
                }
            )
        return items

    @classmethod
    async def update_token(
        cls,
        token_id: int,
        allow_domains: str | None = None,
        allow_ips: str | None = None,
    ) -> bool:
        """更新令牌白名单：字段为 ``None`` 表示不改；传空串表示清空为不限。

        返回 ``False`` 表示令牌不存在（或已逻辑删除）。
        """
        async with async_db_session.begin() as db:
            row = await db.get(AiAssetAccessTokenModel, token_id)
            if row is None or row.is_deleted:
                return False
            if allow_domains is not None:
                row.allow_domains = allow_domains
            if allow_ips is not None:
                row.allow_ips = allow_ips
            return True

    @classmethod
    async def list_token_logs(
        cls, token_id: int, page_no: int = 1, page_size: int = 20
    ) -> dict:
        """分页查询某令牌的使用日志（按 ``created_time`` 倒序）。"""
        page_no = max(1, int(page_no))
        page_size = max(1, min(int(page_size), 100))
        async with async_db_session() as db:
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(AiAssetEmbedLogModel)
                    .where(
                        AiAssetEmbedLogModel.token_id == token_id,
                        AiAssetEmbedLogModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one()
            rows = (
                (
                    await db.execute(
                        select(AiAssetEmbedLogModel)
                        .where(
                            AiAssetEmbedLogModel.token_id == token_id,
                            AiAssetEmbedLogModel.is_deleted.is_(False),
                        )
                        .order_by(AiAssetEmbedLogModel.created_time.desc())
                        .offset((page_no - 1) * page_size)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )
        items = []
        for r in rows:
            items.append(
                {
                    "id": r.id,
                    "created_time": r.created_time.strftime("%Y-%m-%d %H:%M:%S")
                    if r.created_time
                    else None,
                    "client_ip": r.client_ip or "",
                    "result_status": r.result_status or "",
                    "error": r.error,
                    "latency_ms": r.latency_ms or 0,
                    "message": r.message or "",
                    "sid": r.sid or "",
                }
            )
        return {
            "items": items,
            "total": int(total),
            "page_no": page_no,
            "page_size": page_size,
            "has_next": page_no * page_size < int(total),
        }

    @classmethod
    async def revoke_token(cls, token_id: int) -> bool:
        """吊销令牌（置 ``revoked=true``，立即生效；保留审计行不物理删）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiAssetAccessTokenModel, token_id)
            if row is None or row.is_deleted:
                return False
            row.revoked = True
            return True
