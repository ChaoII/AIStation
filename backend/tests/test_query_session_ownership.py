"""会话归属校验回归（越权读/删他人问数历史）。

修复前 `list_messages` / `delete_session` 只按 id 查：任何拿到
`module_ai:query:ask` 的用户枚举 id 就能读到、删掉**别人的**会话历史。
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.query.service import AiQueryService as S


def _auth(uid: int | None):
    if uid is None:
        return None
    return SimpleNamespace(user=SimpleNamespace(id=uid))


def test_owner_can_access() -> None:
    S._ensure_session_owner(SimpleNamespace(user_id=7), _auth(7))  # 不应抛


def test_other_user_is_denied_and_existence_hidden() -> None:
    """拒绝时必须用「不存在」文案，避免泄露 id 是否存在。"""
    with pytest.raises(CustomException) as exc:
        S._ensure_session_owner(SimpleNamespace(user_id=7), _auth(8))
    assert "不存在" in str(exc.value)
    assert "权限" not in str(exc.value)


def test_legacy_session_without_owner_stays_accessible() -> None:
    S._ensure_session_owner(SimpleNamespace(user_id=None), _auth(9))  # 遗留数据不回归


def test_missing_session_is_denied() -> None:
    with pytest.raises(CustomException):
        S._ensure_session_owner(None, _auth(1))


def test_internal_call_without_auth_skips_check() -> None:
    """内部调用（如问句重写读历史）没有 HTTP 用户上下文，放行。"""
    S._ensure_session_owner(SimpleNamespace(user_id=7), None)
