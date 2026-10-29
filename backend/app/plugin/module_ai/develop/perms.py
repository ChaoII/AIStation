"""AI 集成开放平台 —— 平台权限映射与用户权限校验（模式 B 用）。

开放能力码（``integration:<category>:<action>``）与平台用户角色权限串
（``module_ai:<category>:<action>``，train 属 ``module_train:task:*``）两套命名
几乎一一对应。模式 B 用户自助申请时，须校验「用户申请的能力码」所对应的
**平台权限串**是否在该用户角色的权限集合内——防止只持查询权限却能申请
创建/删除/更新等高权限能力（越权提权）。

- :func:`platform_perm_for`：能力码 → 平台权限串（带 action 维度）。
- :func:`user_has_perm`：判断某平台用户是否具备某权限串（复刻 ``AuthPermission``
  的用户权限集合推导，但不限于当前登录者）。
"""
from __future__ import annotations

from app.plugin.module_ai.develop.registry import get_capability

#: 品类码 → 平台权限域前缀（缺省 ``module_ai``；train 属独立 ``module_train`` 模块）。
_CATEGORY_DOMAIN: dict[str, str] = {
    "train": "module_train",
    "chat": "module_ai",
    "bot": "module_ai",
}


def _domain_for(category: str) -> str:
    return _CATEGORY_DOMAIN.get(category, "module_ai")


def platform_perm_for(capability_code: str) -> str | None:
    """把开放能力码映射到平台权限串（如 ``agent.list`` → ``module_ai:agent:query``）。

    规则：取 ``registry`` 中该能力的 ``perm``（``integration:<category>:<action>``），
    把 ``integration`` 前缀换成对应域（默认 ``module_ai``，train → ``module_train``），
    保留 ``<category>:<action>``。能力码不存在或非 ``integration:`` 前缀返回 ``None``。

    特殊映射：
    - 训练（train）：``module_train:task:<action>``（task 是训练模块的实体名）。
    - 对话/机器人（chat/bot）：无独立菜单域，映射到 ``module_ai:assistant:query``（只读）。

    Args:
        capability_code: 开放能力码（如 ``"agent.list"``）。

    Returns:
        平台权限串；无法映射返回 ``None``。
    """
    cap = get_capability(capability_code)
    if cap is None or not cap.perm or not cap.perm.startswith("integration:"):
        return None
    rest = cap.perm[len("integration:"):]  # "<category>:<action>"
    category, _, action = rest.partition(":")
    if not action:
        return None
    domain = _domain_for(category)
    # chat/bot 无独立实体动作域，只读映射到助手查询权限
    if category in ("chat", "bot"):
        return f"{domain}:assistant:query"
    # train 实体名为 task，其余保留品类码
    entity = "task" if category == "train" else category
    return f"{domain}:{entity}:{action}"


def user_has_perm(user, perm: str) -> bool:
    """判断平台用户是否具备某平台权限串（复刻 ``AuthPermission`` 的用户权限集合推导）。

    - 超管（``is_superuser``）直接放行；
    - 否则按 ``user.roles -> role.menus -> menu.permission`` 展开，任一命中即 True。

    Args:
        user: 平台用户 ORM 实例（含 ``roles``，已 ``selectinload`` 时可避免懒加载）。
        perm: 平台权限串（如 ``module_ai:agent:query``）。

    Returns:
        具备返回 ``True``，否则 ``False``。
    """
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    perms: set[str] = set()
    for role in getattr(user, "roles", None) or []:
        if not role or getattr(role, "status", "0") != "0":
            continue
        for menu in getattr(role, "menus", None) or []:
            if not menu:
                continue
            if getattr(menu, "status", "0") != "0":
                continue
            p = getattr(menu, "permission", None)
            if p:
                perms.add(p)
    return perm in perms


def user_has_capability(user, capability_code: str) -> bool:
    """判断平台用户是否具备申请某开放能力所需的最小平台权限。

    Args:
        user: 平台用户 ORM 实例。
        capability_code: 开放能力码（``agent.list`` 等）。

    Returns:
        具备返回 ``True``；能力码无法映射到平台权限串时按「不具备」处理（保守拒绝）。
    """
    perm = platform_perm_for(capability_code)
    if perm is None:
        return False
    return user_has_perm(user, perm)
