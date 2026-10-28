"""AI 集成开放平台 —— 应用服务层（CRUD / 凭证 / 校验 / 调用日志）。

- appid/appkey 生成与重置：appkey **只存 sha256 散列**（``_hash_appkey``），
  明文仅在 ``create_app`` / ``reset_appkey`` 返回一次；列表/详情绝不泄出
  ``appkey_hash`` 或明文。
- ``verify_appkey``：供后续鉴权/开放 API 复用——按 ``appid`` 查，
  依次校验 ``enabled``、``expire_at``（非空且 < now 视为过期）、
  ``hmac.compare_digest``，任一失败返回 ``None``。
- ``log_call``：写入调用日志，并顺手更新应用的 ``last_call_at`` / ``call_count``。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime

from sqlalchemy import func, or_, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiIntegrationAppModel, AiIntegrationCallLogModel
from .registry import normalize_channels, resolve_capability_grants

#: appid 随机字符表：去掉易混淆的 0/O/1/l/I。
_APPID_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


def _generate_appid() -> str:
    """生成应用标识：``ai_`` + 8 位去易混淆字符随机串。"""
    return "ai_" + "".join(secrets.choice(_APPID_ALPHABET) for _ in range(8))


def _generate_appkey() -> str:
    """生成明文 AppKey（调用方**只能**拿到这一次，库中仅存散列）。"""
    return secrets.token_urlsafe(32)


def _hash_appkey(appkey: str) -> str:
    """对 AppKey 做 sha256 散列（存库用，不存明文）。"""
    return hashlib.sha256(appkey.encode("utf-8")).hexdigest()


def _mask_appid(appid: str) -> str:
    """打码 appid，如 ``ai_ab4**...**``（保留前缀，方便识别但不利于窃取）。"""
    if len(appid) > 7:
        return f"{appid[:5]}**...**"
    return appid


def _app_to_dict(app: AiIntegrationAppModel, *, appkey: str | None = None) -> dict:
    """把应用模型转成对外 dict。

    **绝不包含** ``appkey_hash``；仅当 ``appkey`` 参数（一次性明文）传入时
    才附带 ``appkey`` 字段。

    ``capabilities`` 输出为**解析后的授权能力码**（旧 ``integration:*`` 权限点
    已展开为能力码），``channels`` 输出为 ``{能力码: [rest,mcp]}``。
    """
    grants = resolve_capability_grants(app.capabilities)
    data = {
        "id": app.id,
        "uuid": app.uuid,
        "appid": app.appid,
        "appid_masked": _mask_appid(app.appid),
        "name": app.name,
        "description": app.description or "",
        "enabled": bool(app.enabled),
        "expire_at": app.expire_at,
        "capabilities": sorted(grants),
        "channels": normalize_channels(app.channels, grants),
        "quota": app.quota,
        "requires_approval": bool(app.requires_approval),
        "source_type": app.source_type,
        "last_call_at": app.last_call_at,
        "call_count": app.call_count or 0,
        "created_time": app.created_time,
        "updated_time": app.updated_time,
    }
    if appkey is not None:
        data["appkey"] = appkey
    return data


class DevelopService:
    """AI 集成应用服务：CRUD、appid/appkey 生成与重置、鉴权与调用日志。"""

    @classmethod
    async def list_apps(
        cls,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页列出应用（按名称/appid 模糊搜索），item 不含 ``appkey_hash``，含 ``appid_masked``。"""
        page = max(int(page or 1), 1)
        page_size = max(int(page_size or 20), 1)
        wheres = [AiIntegrationAppModel.is_deleted.is_(False)]
        if keyword:
            like = f"%{keyword}%"
            wheres.append(or_(AiIntegrationAppModel.name.like(like), AiIntegrationAppModel.appid.like(like)))

        async with async_db_session() as db:
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(select(AiIntegrationAppModel.id).where(*wheres).subquery())
                )
            ).scalar() or 0
            rows = (
                await db.execute(
                    select(AiIntegrationAppModel)
                    .where(*wheres)
                    .order_by(AiIntegrationAppModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            items = [_app_to_dict(r) for r in rows]
            return {
                "page_no": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
                "items": items,
            }

    @classmethod
    async def get_app(cls, app_id: int) -> dict | None:
        """获取单个应用详情；不存在或已软删返回 ``None``。"""
        async with async_db_session() as db:
            row = await db.get(AiIntegrationAppModel, app_id)
            if not row or row.is_deleted:
                return None
            return _app_to_dict(row)

    @classmethod
    async def create_app(cls, data, auth) -> dict:
        """创建应用：校验 name 唯一、归一 capabilities，生成 appid/appkey，存哈希，返回一次性明文。"""
        appid = _generate_appid()
        appkey = _generate_appkey()
        caps = sorted(resolve_capability_grants(data.capabilities))
        channels = normalize_channels(data.channels, set(caps)) if data.channels is not None else None
        async with async_db_session.begin() as db:
            dup = await db.scalar(
                select(AiIntegrationAppModel).where(
                    AiIntegrationAppModel.name == data.name,
                    AiIntegrationAppModel.is_deleted.is_(False),
                )
            )
            if dup:
                raise CustomException(msg=f"应用名称已存在：{data.name}")
            row = AiIntegrationAppModel(
                name=data.name,
                appid=appid,
                appkey_hash=_hash_appkey(appkey),
                description=data.description,
                enabled=data.enabled if data.enabled is not None else True,
                expire_at=data.expire_at,
                capabilities=caps or [],
                channels=channels,
                quota=data.quota,
                requires_approval=True if data.requires_approval is None else bool(data.requires_approval),
                source_type="admin",
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(row)
            await db.flush()
            return _app_to_dict(row, appkey=appkey)

    @classmethod
    async def update_app(cls, app_id: int, data, auth) -> dict | None:
        """更新应用：仅更新显式传入的字段，name 变更需查重。"""
        payload = data.model_dump(exclude_unset=True)
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppModel, app_id)
            if not row or row.is_deleted:
                return None
            if "name" in payload and payload["name"] and payload["name"] != row.name:
                dup = await db.scalar(
                    select(AiIntegrationAppModel).where(
                        AiIntegrationAppModel.name == payload["name"],
                        AiIntegrationAppModel.is_deleted.is_(False),
                        AiIntegrationAppModel.id != app_id,
                    )
                )
                if dup:
                    raise CustomException(msg=f"应用名称已存在：{payload['name']}")
                row.name = payload["name"]
            if "capabilities" in payload:
                row.capabilities = sorted(resolve_capability_grants(payload["capabilities"])) or []
            if "channels" in payload:
                # 出口按「更新后的授权能力码」归一；只保留已授权能力的出口
                grants = resolve_capability_grants(row.capabilities)
                row.channels = normalize_channels(payload["channels"], grants) or None
            for key in ("description", "expire_at", "quota"):
                if key in payload:
                    setattr(row, key, payload[key])
            if "requires_approval" in payload:
                # 允许显式传 None 还原为默认 True（模型列非空）
                row.requires_approval = True if payload["requires_approval"] is None else bool(payload["requires_approval"])
            if "enabled" in payload:
                row.enabled = bool(payload["enabled"])
            row.updated_id = auth.user.id
            await db.flush()
            return _app_to_dict(row)

    @classmethod
    async def delete_app(cls, ids: int | list[int], auth) -> None:
        """软删应用：置 ``is_deleted``，并释放唯一 ``name``/``appid``（加 ``__deleted_{id}_{ts}`` 后缀）。"""
        if isinstance(ids, int):
            ids = [ids]
        now = datetime.now()
        async with async_db_session.begin() as db:
            for app_id in ids:
                row = await db.get(AiIntegrationAppModel, app_id)
                if not row or row.is_deleted:
                    continue
                row.is_deleted = True
                row.deleted_time = now
                row.deleted_id = auth.user.id
                row.updated_id = auth.user.id
                suffix = f"__deleted_{row.id}_{int(now.timestamp())}"
                row.name = f"{(row.name or '')[: 128 - len(suffix)]}{suffix}"
                row.appid = f"{(row.appid or '')[: 64 - len(suffix)]}{suffix}"

    @classmethod
    async def toggle_app(cls, app_id: int, enabled: bool, auth) -> dict | None:
        """启停应用；不存在或已软删返回 ``None``。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppModel, app_id)
            if not row or row.is_deleted:
                return None
            row.enabled = bool(enabled)
            row.updated_id = auth.user.id
            await db.flush()
            return _app_to_dict(row)

    @classmethod
    async def reset_appkey(cls, app_id: int, auth) -> dict:
        """重置 AppKey：覆盖哈希，返回 ``{appid, appkey}`` 明文一次。"""
        new_appkey = _generate_appkey()
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppModel, app_id)
            if not row or row.is_deleted:
                raise CustomException(msg="应用不存在")
            row.appkey_hash = _hash_appkey(new_appkey)
            row.updated_id = auth.user.id
            await db.flush()
            return {"appid": row.appid, "appkey": new_appkey}

    @classmethod
    async def verify_appkey(cls, appid: str, appkey: str) -> AiIntegrationAppModel | None:
        """校验 AppKey：按 ``appid`` 查，依次校验 enabled / expire_at / 散列比对，任一失败返回 ``None``。"""
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiIntegrationAppModel).where(
                        AiIntegrationAppModel.appid == appid,
                        AiIntegrationAppModel.is_deleted.is_(False),
                    )
                )
            ).scalars().first()
            if not row:
                return None
            if not row.enabled:
                return None
            now = datetime.now()
            if row.expire_at is not None and row.expire_at < now:
                return None
            if not hmac.compare_digest(_hash_appkey(appkey), row.appkey_hash):
                return None
            return row

    @classmethod
    async def log_call(
        cls,
        app: AiIntegrationAppModel,
        *,
        category: str,
        capability: str,
        log_type: str = "invoke",
        method: str = "REST",
        transport: str | None = None,
        session_id: str | None = None,
        client_info: str | None = None,
        request_path: str | None = None,
        request_body: dict | None = None,
        status: str,
        error: str | None = None,
        latency_ms: int = 0,
        cost_tokens: int = 0,
        result_summary: str | None = None,
    ) -> None:
        """写一条调用日志，并顺手更新应用的 ``last_call_at`` / ``call_count``。"""
        now = datetime.now()
        async with async_db_session.begin() as db:
            db.add(
                AiIntegrationCallLogModel(
                    app_id=app.id,
                    appid=app.appid,
                    category=category,
                    capability=capability,
                    log_type=log_type,
                    method=method,
                    transport=transport or "http",
                    session_id=session_id,
                    client_info=client_info,
                    request_path=request_path or "",
                    request_body=request_body,
                    status=status,
                    error=error,
                    latency_ms=latency_ms,
                    cost_tokens=cost_tokens,
                    result_summary=result_summary,
                )
            )
            row = await db.get(AiIntegrationAppModel, app.id)
            if row:
                row.last_call_at = now
                row.call_count = (row.call_count or 0) + 1


# ---------------------------------------------------------------------- #
# 嵌入短期令牌（P4'）：生成 / 散列 / TTL 夹紧（纯逻辑，无 DB / HTTP）
# ---------------------------------------------------------------------- #

def _generate_embed_token() -> str:
    """生成嵌入 access_token 明文（URL 安全、不含冒号，便于 Bearer 解析）。"""
    return secrets.token_urlsafe(32)


def _hash_embed_token(token: str) -> str:
    """计算嵌入 token 的 sha256 散列（库内只存散列，明文仅签发时返回一次）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clamp_embed_ttl(ttl: int | None) -> int:
    """夹紧换票 TTL：缺省 1800s，下限 60s，上限 86400s（24 小时）。"""
    if ttl is None:
        return 1800
    return max(60, min(int(ttl), 86400))
