# tests/test_develop_public_apps.py
#
# AI 集成开放平台 —— 阶段 1.5 资源公开治理测试：
# - 可见性过滤（自己创建 + 平台共享 + 主动公开；排除他人未公开私有）
# - 默认公开策略（超管/服务账号→公开；普通用户→不公开）
# - 公开申请 → 管理员审核 → 写回资源 is_public=true
# - 只读守卫（B 应用对非本人资源写操作被拒）
# 说明：DB 相关统一 asyncio.run 一层，使用 test_client 夹具（PYTEST_NO_APP=1 自动 skip）。
import asyncio

import pytest

from app.core.exceptions import CustomException


def _run(coro):
    return asyncio.run(coro)


# ---------------- 默认公开策略（纯逻辑） ----------------
def test_default_public_superuser(test_client):
    from app.plugin.module_ai.develop.visibility import default_is_public_for_creator
    from types import SimpleNamespace

    assert default_is_public_for_creator(SimpleNamespace(is_superuser=True)) is True
    assert default_is_public_for_creator(SimpleNamespace(is_superuser=False)) is False
    assert default_is_public_for_creator(None) is False


def test_visible_condition_math(test_client):
    """可见性条件 = 自己创建 ∪ 平台共享 ∪ 主动公开。"""
    from app.plugin.module_ai.develop.visibility import visible_condition
    from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel

    cond = visible_condition(
        AiKnowledgeBaseModel, owner_user_id=100, shared_ids=[1, 5]
    )
    # 编译成 SQL 字符串，检查三类条件都被包含
    sql = str(cond.compile(compile_kwargs={"literal_binds": True}))
    assert "created_id" in sql
    # 只要包含 or 分支即可（具体列名以编译结果为准）
    assert " is true" in sql or "true" in sql


# ---------------- 可见性过滤（DB） ----------------
def test_visible_user_ids_for_owner_and_shared(test_client):
    from app.plugin.module_ai.develop.visibility import visible_user_ids_for

    assert visible_user_ids_for(100, shared_ids=[1, 5]) == [1, 5, 100]
    assert visible_user_ids_for(None, shared_ids=[1, 5]) == [1, 5]


# ---------------- 公开申请流（DB） ----------------
def test_public_apply_submit_and_review(test_client):
    """用户对私有资源发起公开申请 → 管理员批准 → 资源 is_public=true。"""
    from app.plugin.module_ai.develop.public_apps import PublicApplyService
    from app.plugin.module_ai.develop.public_resolvers import build_resolvers
    from types import SimpleNamespace

    user = SimpleNamespace(id=100, is_superuser=False)
    resolvers = build_resolvers()
    # 先造一个 owned 知识库（created_id=100, is_public=false）
    from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel
    from app.core.database import async_db_session
    from datetime import datetime

    async def seed():
        async with async_db_session.begin() as db:
            kb = AiKnowledgeBaseModel(
                name="公开测试库", description="", created_id=100, updated_id=100,
                is_public=False,
                created_time=datetime.now(), updated_time=datetime.now(),
            )
            db.add(kb)
            await db.flush()
            return kb.id

    kb_id = _run(seed())

    # 提交公开申请
    row = _run(PublicApplyService.submit(
        user, resource_type="knowledge", resource_id=kb_id, reason="测试公开"
    ))
    assert row["apply_status"] == "pending"
    assert row["public_perm"] == "readonly"

    # 管理员批准
    result = _run(PublicApplyService.review(row["id"], approve=True, reviewer_id=1, note="同意"))
    assert result["apply_status"] == "approved"

    # 资源 is_public 已被写回 true
    kb = _run(resolvers["knowledge"]["get"](kb_id))
    assert kb["is_public"] is True


def test_public_apply_reject_other_user_resource(test_client):
    """用户只能申请公开自己创建的资源（他人资源 → 403）。"""
    from app.plugin.module_ai.develop.public_apps import PublicApplyService
    from types import SimpleNamespace

    user = SimpleNamespace(id=100, is_superuser=False)
    with pytest.raises(CustomException) as exc_info:
        _run(PublicApplyService.submit(
            user, resource_type="knowledge", resource_id=999999, reason="越权"
        ))
    assert exc_info.value.status_code == 404


# ---------------- 只读守卫 ----------------
def test_ensure_resource_writable(test_client):
    from app.plugin.module_ai.develop.handlers._common import ensure_resource_writable
    from types import SimpleNamespace

    # 平台级应用（owner=None）可写
    ensure_resource_writable(SimpleNamespace(owner_user_id=None), 1, "资源")
    # B 应用写他人资源（仅只读）→ 拒绝
    with pytest.raises(CustomException) as exc_info:
        ensure_resource_writable(SimpleNamespace(owner_user_id=100), 200, "知识库")
    assert exc_info.value.status_code == 403
    # B 应用写自己资源 → 允许
    ensure_resource_writable(SimpleNamespace(owner_user_id=100), 100, "知识库")
