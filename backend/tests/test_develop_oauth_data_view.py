# tests/test_develop_oauth_data_view.py
#
# 阶段 2（OAuth 2.1）—— Task 7：数据面按 sub 过滤 + OAuth 审计不崩。
# 用 knowledge.list 验证：委托 token（sub=100）只返回自己私有 + 平台共享，
# 不含其它用户（sub=200）的私有；审计走 OAuth 分支（app_id 为空、不崩）。
import asyncio
from types import SimpleNamespace

from app.core.database import async_db_session


def _run(coro):
    return asyncio.run(coro)


async def _seed_kb(name, created_id, is_public, is_superuser=False):
    from datetime import datetime

    from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel

    async with async_db_session.begin() as db:
        obj = AiKnowledgeBaseModel(
            name=name,
            created_id=created_id,
            updated_id=created_id,
            is_public=is_public,
            created_time=datetime.now(),
            updated_time=datetime.now(),
        )
        db.add(obj)
        await db.flush()
        return obj.id


async def _make_oauth_ctx(client_dict, user_id, scope):
    """走完整 OAuth 流程，返回委托 token + AppContext。"""
    from app.plugin.module_ai.develop.oauth_auth import get_oauth_api_auth
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    row = await OAuthClientService.get_client(client_dict["client_id"])
    code = await OAuthClientService.issue_authorization_code(
        row, user_id, scope=scope, redirect_uri="https://assistant.example/callback",
        code_challenge=None, code_challenge_method=None,
    )
    pair = await OAuthTokenService.exchange_code(
        client_id=client_dict["client_id"],
        client_secret=client_dict["client_secret"],
        code=code["code"],
        redirect_uri="https://assistant.example/callback",
        code_verifier=None,
    )
    return pair["access_token"], await get_oauth_api_auth(f"Bearer {pair['access_token']}")


async def _seed_client(service, max_scope=None):
    import uuid

    from app.plugin.module_ai.develop.oauth_schema import OAuthClientCreateSchema

    data = OAuthClientCreateSchema(
        name=f"测试客户端-{uuid.uuid4().hex[:8]}",
        description="测试",
        redirect_uris=["https://assistant.example/callback"],
        max_scope=max_scope or ["knowledge.list"],
    )
    return await service.create_client(data, SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True)))


def test_oauth_invoke_filters_by_sub(test_client):
    """委托 token（sub=100）的 knowledge.list 只返回自己私有 + 平台共享，不含 sub=200 私有。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService
    from app.plugin.module_ai.develop.openapi import invoke_capability
    from app.plugin.module_ai.develop.visibility import reset_platform_shared_cache

    reset_platform_shared_cache()

    # 平台共享（超管 id=1 创建，默认公开）
    shared_id = _run(_seed_kb("平台共享库", created_id=1, is_public=True))
    # 用户 100 私有
    own_id = _run(_seed_kb("用户100私有库", created_id=100, is_public=False))
    # 用户 200 私有（不应出现在 sub=100 的结果里）
    other_id = _run(_seed_kb("用户200私有库", created_id=200, is_public=False))

    created = _run(_seed_client(OAuthClientService))
    _, ctx = _run(_make_oauth_ctx(created, user_id=100, scope=["knowledge.list"]))

    result = _run(invoke_capability(ctx, "knowledge.list", {}, method="REST"))
    ids = [item["id"] for item in result["items"]]
    assert own_id in ids, "sub=100 应看到自己的私有库"
    assert shared_id in ids, "sub=100 应看到平台共享库"
    assert other_id not in ids, "sub=100 不应看到用户200的私有库"


def test_oauth_invoke_audit_does_not_crash(test_client):
    """OAuth ctx 调 invoke_capability 成功，审计（app_id 为空）不抛。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService
    from app.plugin.module_ai.develop.openapi import invoke_capability
    from app.plugin.module_ai.develop.visibility import reset_platform_shared_cache

    reset_platform_shared_cache()
    _run(_seed_kb("审计测试库", created_id=100, is_public=False))

    created = _run(_seed_client(OAuthClientService))
    _, ctx = _run(_make_oauth_ctx(created, user_id=100, scope=["knowledge.list"]))

    result = _run(invoke_capability(ctx, "knowledge.list", {}, method="REST"))
    assert "items" in result

    # 审计应落库（app_id 为空、appid=client_id）
    from app.plugin.module_ai.develop.model import AiIntegrationCallLogModel
    from sqlalchemy import select

    async def latest_log():
        async with async_db_session() as db:
            return (
                await db.execute(
                    select(AiIntegrationCallLogModel)
                    .order_by(AiIntegrationCallLogModel.id.desc())
                    .limit(1)
                )
            ).scalars().first()

    log = _run(latest_log())
    assert log is not None
    assert log.app_id is None  # OAuth 无应用行
    assert log.appid == created["client_id"]
    assert log.capability == "knowledge.list"
