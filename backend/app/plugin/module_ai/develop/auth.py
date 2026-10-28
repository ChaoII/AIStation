"""AI 集成开放平台 —— 开放数据面鉴权依赖（纯逻辑 + FastAPI 依赖）。

- ``AppContext``：鉴权成功后的应用上下文，供开放 API（Task 5）读取
  应用身份、授权能力集合与配额。
- ``_parse_bearer``：解析 ``Authorization: Bearer <appid>:<appkey>`` 请求头，
  在**首个冒号**处切分，保证 appkey 可含冒号。
- ``get_app_api_auth``：FastAPI 依赖——按 ``appid/appkey`` 校验，构造
  ``AppContext``；解析/校验任一失败抛 401（**不区分原因**，避免 appid 枚举）。
- ``require_capability``：按「能力码 + 出口」校验，未授权/未开放出口抛 403。
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from app.core.exceptions import CustomException

from .registry import resolve_capability_grants, resolve_channels
from .service import DevelopService, _app_to_dict


@dataclass
class AppContext:
    """已鉴权应用上下文。

    Attributes:
        app_id: 应用主键 ID（DB 行 ``id``）。
        appid: 对外暴露的应用标识。
        grants: 授权**能力码**集合（旧 ``integration:*`` 权限点已展开为能力码）。
        channels: 出口控制 ``{能力码: {rest,mcp}}``（缺省出口已归一）。
        quota: 配额配置（JSON 对象），可为 ``None``。
        app: 应用的对外 dict（**不含** ``appkey_hash`` / 明文 appkey）。
    """

    app_id: int
    appid: str
    grants: set[str]
    channels: dict[str, set[str]]
    quota: dict | None
    app: dict


def _ctx_from_row(row) -> AppContext:
    """由应用 ORM 行构造 :class:`AppContext`（把权限点展开为能力码 + 归一出口）。"""
    grants = resolve_capability_grants(row.capabilities)
    return AppContext(
        app_id=row.id,
        appid=row.appid,
        grants=grants,
        channels=resolve_channels(row.channels, grants),
        quota=row.quota,
        app=_app_to_dict(row),
    )


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
    return _ctx_from_row(row)


def require_capability(ctx: AppContext, code: str, channel: str) -> None:
    """校验应用是否已授权 ``code`` 能力且开放指定出口（``rest`` / ``mcp``）。

    Args:
        ctx: 已鉴权应用上下文。
        code: 能力码（如 ``"agent.list"``）。
        channel: 出口标识（``"rest"`` / ``"mcp"``）。

    Raises:
        CustomException: 未授权该能力或未开放该出口时抛
            ``msg="无权限操作", code=10403, status_code=403``（不区分授权/出口，避免探测）。
    """
    from .registry import is_granted

    if not is_granted(ctx.grants, ctx.channels, code, channel):
        raise CustomException(msg="无权限操作", code=10403, status_code=403)
