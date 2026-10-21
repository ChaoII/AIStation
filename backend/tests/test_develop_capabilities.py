# tests/test_develop_capabilities.py （PYTEST_NO_APP=1）
from app.plugin.module_ai.develop.capabilities import (
    CATEGORIES,
    CATEGORY_PERMS,
    PERMISSION_CODES,
    is_valid_perm,
    normalize_permissions,
    permissions_by_category,
)


def test_categories_have_perms():
    for cat, name in CATEGORIES.items():
        assert name  # 有中文名
        assert CATEGORIES.keys() == {"train", "agent", "chat", "bot", "embed"}
        assert cat in CATEGORY_PERMS and CATEGORY_PERMS[cat]


def test_permission_codes_are_integration_scoped():
    assert all(p.startswith("integration:") for p in PERMISSION_CODES)
    for perms in CATEGORY_PERMS.values():
        assert len(perms) == len(set(perms))  # 不重复


def test_is_valid_perm():
    assert is_valid_perm("integration:train:create")
    assert not is_valid_perm("integration:xxx:yyy")
    assert not is_valid_perm("module_ai:train:create")


def test_normalize_permissions_drops_invalid_and_dedupes():
    got = normalize_permissions(["integration:agent:create", "integration:agent:create", "bad"])
    assert got == {"integration:agent:create"}


def test_permissions_by_category_groups():
    got = permissions_by_category(["integration:agent:create", "integration:chat:send"])
    assert set(got["agent"]) == {"integration:agent:create"}
    assert set(got["chat"]) == {"integration:chat:send"}
