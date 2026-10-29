"""AI 集成开放平台 —— 资源可见性治理（模式 B 数据过滤的统一基础）。

核心语义（资源公开治理，2026-10-29 设计确认）：

- **平台共享**：由超管 / 平台服务账号创建的资源（``created_id`` 指向这些用户），默认公开。
- **主动公开**：普通用户将资源 ``is_public=true``（默认不公开，公开需走申请与审核）。
- **用户可见范围**（B 应用）＝ **自己创建的**（``created_id=owner``）∪ **平台共享的**
  （``created_id ∈ 平台共享用户``）∪ **主动公开的**（``is_public=true``）；
  排除其它普通用户未公开的私有资源。

本模块把「平台共享用户判定 / 可见性过滤条件 / 默认公开策略」集中在一起，供各
service 的 ``list``/``get`` 复用，避免逐品类硬编码。
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import or_, select

from app.core.database import async_db_session

#: —— 平台共享用户的判定 ——
#: ``created_id`` 属于这类用户的资源视为「平台共享」，其他用户可见。
#: 默认取所有 ``is_superuser=true`` 的 ``sys_user``。服务账号（openai_platform）
#: 在 ``_ensure_open_service_user`` 中同样置 ``is_superuser=True``，故自然纳入。
_PLATFORM_SHARED_IDS: set[int] | None = None
_SHARED_LOCK = asyncio.Lock()


async def platform_shared_user_ids() -> list[int]:
    """返回「平台共享用户」的 ``sys_user.id`` 列表（超管 + 服务账号，缓存）。

    返回稳定顺序（升序），供 ``IN`` 过滤与前端展示。
    """
    global _PLATFORM_SHARED_IDS
    if _PLATFORM_SHARED_IDS is not None:
        return sorted(_PLATFORM_SHARED_IDS)
    async with _SHARED_LOCK:
        if _PLATFORM_SHARED_IDS is not None:
            return sorted(_PLATFORM_SHARED_IDS)
        from app.api.v1.module_system.user.model import UserModel

        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(UserModel.id).where(
                        UserModel.is_deleted.is_(False),
                        UserModel.is_superuser.is_(True),
                    )
                )
            ).scalars().all()
        _PLATFORM_SHARED_IDS = set(rows)
        return sorted(_PLATFORM_SHARED_IDS)


def reset_platform_shared_cache() -> None:
    """清空平台共享用户缓存（测试/动态建号后调用）。"""
    global _PLATFORM_SHARED_IDS
    _PLATFORM_SHARED_IDS = None


async def app_visible_where(app_ctx: Any, model: Any):
    """按开放应用上下文构造「该应用可见资源」的 SQLAlchemy 过滤条件。

    规则（与 :func:`visible_condition` 一致）：
    - **B 应用**（``owner_user_id`` 非空）：自己创建的 ∪ 平台共享 ∪ 主动公开。
    - **平台级/A 应用**（``owner_user_id`` 为空）：平台共享 ∪ 主动公开（无「自己」维度）。

    通过开放面对外可见的资源是「平台共享 + 主动公开 + （B 应用自己的）」，见设计
    文档第 5 章。数据不泄露其它普通用户未公开的私有资源。

    Args:
        app_ctx: 开放应用上下文（含 ``owner_user_id``；可为 None，此时按平台级处理）。
        model: 目标资源模型（含 ``created_id`` / ``is_public`` / ``is_deleted``）。

    Returns:
        过滤条件；无任何受限来源时返回 None（表示不额外过滤）。
    """
    if app_ctx is None:
        # 无应用上下文（如内部调用），不额外过滤，保持现状。
        return None
    owner = getattr(app_ctx, "owner_user_id", None)
    shared = await platform_shared_user_ids()
    cond = visible_condition(model, owner_user_id=owner, shared_ids=shared)
    # 平台级（owner=None）且无共享用户、模型无 is_public 时，cond 会退化为恒假——
    # 这里若 owner 为 None 且没有共享用户，视为「无过滤来源」，返回 None 避免误杀。
    if owner is None and not shared and not hasattr(model, "is_public"):
        return None
    return cond


def default_is_public_for_creator(user: Any) -> bool:
    """根据创建者身份决定资源默认公开与否。

    - 超管 / 平台服务账号（``is_superuser=true``）→ **默认公开**（平台共享）。
    - 普通用户 → **默认不公开**（仅自己可见，公开需申请）。

    Args:
        user: 创建者身份（ORM ``UserModel`` 或含 ``is_superuser`` 的 SimpleNamespace）。

    Returns:
        默认 ``is_public`` 值。
    """
    if user is None:
        # 无创建者身份（理论上不出现）——按不公开处理，保险起见。
        return False
    return bool(getattr(user, "is_superuser", False))


def visible_condition(model: Any, *, owner_user_id: int | None, shared_ids: list[int]) -> Any:
    """构建「某用户可见资源」的 SQLAlchemy 过滤条件。

    规则（并集）：
    1. ``created_id == owner_user_id``（自己创建的）；
    2. ``created_id IN shared_ids``（平台共享）；
    3. ``is_public == true``（主动公开）。

    Args:
        model: 目标资源模型（含 ``created_id`` / ``is_public`` / ``is_deleted`` 列）。
        owner_user_id: 当前数据主体用户 id（B 应用的 owner）。为 ``None`` 表示不限定自己
            （仅平台共享 + 主动公开，用于平台级/管理面）。
        shared_ids: 平台共享用户 id 列表（来自 :func:`platform_shared_user_ids`）。

    Returns:
        ``sqlalchemy`` 条件表达式（与 ``is_deleted=false`` 组合成 WHERE）。
    """
    conds: list[Any] = []
    if owner_user_id is not None:
        conds.append(model.created_id == owner_user_id)
    if shared_ids:
        conds.append(model.created_id.in_(shared_ids))
    if hasattr(model, "is_public"):
        conds.append(model.is_public.is_(True))
    if not conds:
        # 无任何可见来源（理论上仅 owner=None 且无共享/无 is_public 字段），返回恒假，避免全量泄露。
        return model.id.is_(None)
    return or_(*conds)


def visible_user_ids_for(owner_user_id: int | None, *, shared_ids: list[int]) -> list[int] | None:
    """返回「某用户可见」所对应的 ``created_id`` 白名单（供 IN 过滤）；own 为 None 时仅共享。

    与 :func:`visible_condition` 等价，但返回 id 列表（供需要显式 ``user_id`` 入参的
    service 使用，如 mcp 的 ``list_servers(user_id)``）。
    """
    ids: set[int] = set(shared_ids)
    if owner_user_id is not None:
        ids.add(owner_user_id)
    return sorted(ids) if ids else None
