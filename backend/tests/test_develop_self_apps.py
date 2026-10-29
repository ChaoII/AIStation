# tests/test_develop_self_apps.py
#
# AI 集成开放平台 —— 模式 B（用户自助申请应用）与权限映射 / 能力上限校验测试。
# 说明：本项目未引入 pytest-asyncio，DB 相关统一用「asyncio.run 一层」写法，
# 使用 test_client 夹具确保应用构造完成后才执行（PYTEST_NO_APP=1 时自动 skip）。
import asyncio

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.develop.perms import platform_perm_for
from app.plugin.module_ai.develop.self_apps import SelfApplyService
from app.plugin.module_ai.develop.schema import DevelopApplySchema


def _run(coro):
    return asyncio.run(coro)


class _Role:
    def __init__(self, perms):
        self.status = "0"
        self.menus = [_Menu(p) for p in perms]


class _Menu:
    def __init__(self, perm):
        self.status = "0"
        self.permission = perm


class _SuperUser:
    id = 1
    is_superuser = True
    roles = []


class _NormalUser:
    """普通用户：具备 module_ai:agent:query + knowledge:query，无 create/delete。"""
    id = 100
    is_superuser = False
    roles = [_Role(["module_ai:agent:query", "module_ai:knowledge:query"])]


class _Auth:
    def __init__(self, user):
        self.user = user


# ---------------- 权限映射 ----------------
def test_platform_perm_for_query_and_delete():
    assert platform_perm_for("agent.list") == "module_ai:agent:query"
    assert platform_perm_for("agent.create") == "module_ai:agent:create"
    assert platform_perm_for("agent.delete") == "module_ai:agent:delete"


def test_platform_perm_for_train_and_chat_specials():
    assert platform_perm_for("train.list") == "module_train:task:query"
    assert platform_perm_for("train.create") == "module_train:task:create"
    # chat/bot 无独立菜单域，映射到助手查询权限（只读）
    assert platform_perm_for("chat.send") == "module_ai:assistant:query"


def test_platform_perm_for_unknown():
    assert platform_perm_for("nonexistent.list") is None


# ---------------- 能力上限校验 ----------------
def test_user_capability_scope_ok(test_client):
    """普通用户具备 query 权限 → 可申请查询类能力。"""
    from app.plugin.module_ai.develop.perms import user_has_capability

    user = _NormalUser()
    assert user_has_capability(user, "agent.list") is True
    assert user_has_capability(user, "knowledge.list") is True


def test_user_capability_scope_denied(test_client):
    """普通用户无 create/delete 权限 → 不能申请创建/删除类能力（防越权提权）。"""
    from app.plugin.module_ai.develop.perms import user_has_capability

    user = _NormalUser()
    assert user_has_capability(user, "agent.create") is False
    assert user_has_capability(user, "knowledge.delete") is False


def test_superuser_can_apply_anything(test_client):
    from app.plugin.module_ai.develop.perms import user_has_capability

    assert user_has_capability(_SuperUser(), "agent.delete") is True


# ---------------- 自助申请流（DB） ----------------
def test_submit_apply_write_pending(test_client):
    """普通用户提交申请（合法能力）→ 写 pending 申请单。"""
    data = DevelopApplySchema(name="我的自助应用", capabilities=["agent.list", "knowledge.list"])
    row = _run(SelfApplyService.submit(_NormalUser(), data))
    assert row["applicant_id"] == 100
    assert row["apply_status"] == "pending"
    assert set(row["capabilities"]) == {"agent.list", "knowledge.list"}


def test_submit_apply_reject_privilege_escalation(test_client):
    """普通用户申请超出自身权限的能力（agent.create）→ 拒绝（越权提权）。"""
    data = DevelopApplySchema(name="越权应用", capabilities=["agent.list", "agent.create"])
    with pytest.raises(CustomException):
        _run(SelfApplyService.submit(_NormalUser(), data))


def test_review_approve_creates_app_bound_to_owner(test_client):
    """管理员批准 → 生成应用（source_type=self，owner_user_id=申请者），返回 appkey 一次。"""
    from app.plugin.module_ai.develop.model import AiIntegrationAppModel

    data = DevelopApplySchema(name="待批准应用", capabilities=["agent.list"])
    apply_row = _run(SelfApplyService.submit(_NormalUser(), data))
    result = _run(
        SelfApplyService.review(
            apply_row["id"], approve=True, reviewer_id=1, note="同意"
        )
    )
    assert result["apply_status"] == "approved"
    assert result["app"]["source_type"] == "self"
    assert result["app"]["owner_user_id"] == 100
    assert result["app"]["appkey"] and len(result["app"]["appkey"]) >= 32
    assert result["app"]["capabilities"] == ["agent.list"]
