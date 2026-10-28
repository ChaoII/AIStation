"""AI 集成开放平台 —— 能力品类与权限点定义（纯逻辑，无 DB / HTTP）。

本模块是能力目录的**单一真源**：后续任务（应用 CRUD、鉴权、开放 API）
都从这里读取品类码、中文名与合法权限点，避免多处硬编码导致漂移。

- ``CATEGORIES``：品类码 → 中文名（训练 / 智能体 / 对话 / 机器人 / 向量嵌入）。
- ``CATEGORY_PERMS``：品类码 → 该品类下的**合法权限点**列表（权限码均以
  ``integration:`` 开头，代表「开放平台集成」域）。
- ``PERMISSION_CODES``：全部合法权限点的合集（由 ``CATEGORY_PERMS`` 展开）。
- 辅助函数：``is_valid_perm`` / ``normalize_permissions`` / ``permissions_by_category``。
"""
from __future__ import annotations

#: 品类码 → 中文名（顺序即展示顺序）。
CATEGORIES: dict[str, str] = {
    "train": "模型训练",
    "agent": "智能体",
    "chat": "对话",
    "bot": "机器人",
}

#: 品类码 → 该品类下的合法权限点列表。
CATEGORY_PERMS: dict[str, list[str]] = {
    "train": [
        "integration:train:create",
        "integration:train:query",
        "integration:train:start",
        "integration:train:stop",
    ],
    "agent": [
        "integration:agent:create",
        "integration:agent:query",
        "integration:agent:update",
        "integration:agent:delete",
    ],
    "chat": [
        "integration:chat:send",
        "integration:chat:query",
    ],
    "bot": [
        "integration:bot:use",
    ],
}

#: 全部合法权限点（由 ``CATEGORY_PERMS`` 的值展开拼接）。
PERMISSION_CODES: list[str] = [perm for perms in CATEGORY_PERMS.values() for perm in perms]

#: 合法权限点集合，供 ``is_valid_perm`` 做 O(1) 判断。
_VALID_PERMS: set[str] = set(PERMISSION_CODES)

#: 权限点 → 其所属品类码，供 ``permissions_by_category`` 反向分组。
_PERM_TO_CATEGORY: dict[str, str] = {
    perm: category
    for category, perms in CATEGORY_PERMS.items()
    for perm in perms
}


def is_valid_perm(perm: str) -> bool:
    """判断给定的权限码是否合法（存在于 ``PERMISSION_CODES`` 中）。

    Args:
        perm: 待校验的权限码字符串。

    Returns:
        合法返回 ``True``，否则 ``False``。
    """
    if not isinstance(perm, str):
        return False
    return perm in _VALID_PERMS


def normalize_permissions(perms: list[str]) -> set[str]:
    """规范化权限列表：去重 + 只保留合法项，**不抛错**。

    Args:
        perms: 原始权限码列表（可能含非法项与重复项）。

    Returns:
        去重后的合法权限码集合。
    """
    if not perms:
        return set()
    return {perm for perm in perms if is_valid_perm(perm)}


def permissions_by_category(perms: list[str]) -> dict[str, list[str]]:
    """把权限码按所属品类分组，非法项会被丢弃。

    Args:
        perms: 原始权限码列表。

    Returns:
        ``{品类码: [该品类下的合法权限码, ...]}``，仅包含出现过的品类。
    """
    out: dict[str, list[str]] = {}
    if not perms:
        return out
    for perm in perms:
        category = _PERM_TO_CATEGORY.get(perm)
        if category is not None:
            out.setdefault(category, []).append(perm)
    return out
