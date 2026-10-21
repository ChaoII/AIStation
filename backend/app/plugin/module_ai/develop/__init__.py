"""AI 集成开放平台 —— 开发者目录子包。

对外暴露能力品类与权限点定义（见 :mod:`capabilities`），
供后续的应用 CRUD、鉴权与开放 API 直接复用。
"""
from app.plugin.module_ai.develop.capabilities import (
    CATEGORIES,
    CATEGORY_PERMS,
    PERMISSION_CODES,
    is_valid_perm,
    normalize_permissions,
    permissions_by_category,
)

__all__ = [
    "CATEGORIES",
    "CATEGORY_PERMS",
    "PERMISSION_CODES",
    "is_valid_perm",
    "normalize_permissions",
    "permissions_by_category",
]
