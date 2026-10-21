"""AI 集成开放平台 —— 开放数据面鉴权依赖（纯逻辑 + FastAPI 依赖）。

- ``AppContext``：鉴权成功后的应用上下文，供开放 API（Task 5）读取
  应用身份、授权能力集合与配额。
- ``_parse_bearer``：解析 ``Authorization: Bearer <appid>:<appkey>`` 请求头，
  在**首个冒号**处切分，保证 appkey 可含冒号。
- ``get_app_api_auth``：FastAPI 依赖——按 ``appid/appkey`` 校验，构造
  ``AppContext``；解析/校验任一失败抛 401（**不区分原因**，避免 appid 枚举）。
- ``require_app_perm``：权限点校验，未授权抛 403。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Header
from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiIntegrationAccessTokenModel, AiIntegrationAppModel
from .service import DevelopService, _app_to_dict, _hash_embed_token


@dataclass
class AppContext:
    """已鉴权应用上下文。

    Attributes:
        app_id: 应用主键 ID（DB 行 ``id``）。
        appid: 对外暴露的应用标识。
        perms: 授权能力集合（由 ``row.capabilities`` 归一而来）。
        quota: 配额配置（JSON 对象），可为 ``None``。
        app: 应用的对外 dict（**不含** ``appkey_hash`` / 明文 appkey）。
    """

    app_id: int
    appid: str
    perms: set[str]
    quota: dict | None
    app: dict


def _parse_bearer(authorization: str | None) -> tuple[str, str] | None:
    """解析 ``Authorization: Bearer <appid>:<appkey>``，返回 ``(appid, appkey)``。

    - 缺头 / 空头 / 非 ``Bearer `` 前缀 / 无冒号 均返回 ``None``。
    - 用 ``credentials.split(":", 1)`` 在**第一个冒号**处切分，使 **appkey 可含冒号**
      （``"appid:abc:def"`` → ``("appid", "abc:def")``）。appid 由生成器产生、不含冒号，
      故取首个冒号即健壮；反之 ``rsplit`` 会把 appkey 截断成最后一个片段，属错误切分。

    Args:
        authorization: ``Authorization`` 请求头原始值。

    Returns:
        ``(appid, appkey)`` 元组；解析失败返回 ``None``。
    """
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    credentials = authorization[7:].strip()
    parts = credentials.split(":", 1)
    if len(parts) != 2:
        return None
    appid, appkey = parts
    # 空 appid / 空 appkey 视为无效凭证（避免把空串交给后续 verify 造成无谓开销）
    if not appid or not appkey:
        return None
    return appid, appkey


async def get_app_api_auth(authorization: str | None = Header(None)) -> AppContext:
    """FastAPI 依赖：解析并校验 ``Authorization`` 头，返回 :class:`AppContext`。

    解析失败或 ``DevelopService.verify_appkey`` 校验失败，一律抛
    ``CustomException(msg="鉴权失败", code=10401, status_code=401)``，
    **不区分失败原因**，避免 appid 枚举。

    Args:
        authorization: ``Authorization`` 头参数（FastAPI 自动映射）。

    Returns:
        :class:`AppContext`（已鉴权应用的上下文）。
    """
    parsed = _parse_bearer(authorization)
    if parsed is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    appid, appkey = parsed
    row = await DevelopService.verify_appkey(appid, appkey)
    if row is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    return AppContext(
        app_id=row.id,
        appid=row.appid,
        perms=set(row.capabilities or []),
        quota=row.quota,
        app=_app_to_dict(row),
    )


def require_app_perm(ctx: AppContext, perm: str) -> None:
    """校验应用是否具备 ``perm`` 权限点。

    Args:
        ctx: 已鉴权应用上下文。
        perm: 待校验的权限码（如 ``"integration:chat:send"``）。

    Raises:
        CustomException: 应用不具备该权限时抛
            ``msg="无权限操作", code=10403, status_code=403``。
    """
    if perm not in ctx.perms:
        raise CustomException(msg="无权限操作", code=10403, status_code=403)
