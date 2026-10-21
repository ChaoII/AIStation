# tests/test_develop_openapi.py
#
# 覆盖 AI 集成开放平台「开放数据面」的鉴权验证端点（Task 5）：
# - ``GET /api/v1/ai/develop-api/auth/verify``：经 ``get_app_api_auth`` 鉴权，
#   返回应用身份 + 能力权限点；成功时写入一条调用审计（log_call）。
# - 401 路径：错误 appkey / 未知 appid / 缺失或畸形 Authorization 头，
#   均由 ``get_app_api_auth`` 依赖抛 ``CustomException(status_code=401)`` 处理。
#
# 说明：未启用 pytest-asyncio，HTTP 用仓库同步 ``test_client`` 夹具，
# DB 校验统一用 ``asyncio.run`` 包一层（参照 test_develop_crud.py）。
# 依赖 test_client 触发应用生命周期（建表），PYTEST_NO_APP=1 时这些用例自动 skip。
import asyncio

import pytest
from sqlalchemy import func, select

from app.core.database import async_db_session
from app.plugin.module_ai.develop.model import AiIntegrationCallLogModel
from app.plugin.module_ai.develop.schema import DevelopCreateSchema
from app.plugin.module_ai.develop.service import DevelopService


async def _make_app(name: str) -> dict:
    """造一个有效应用，返回含一次性明文 appkey 的对外 dict。"""
    return await DevelopService.create_app(
        DevelopCreateSchema(name=name, capabilities=["integration:agent:create"]),
        type("_A", (), {"user": type("_U", (), {"id": 1, "is_superuser": True})()})(),
    )


@pytest.fixture(scope="module")
def create_app():
    # 名称取唯一值避免与 test_develop_crud.py 的 "demo" 撞名（name 唯一约束，跨模块共享会话库）
    return asyncio.run(_make_app("openapi_demo"))


@pytest.mark.app
def test_auth_verify_ok(test_client, create_app: dict):
    resp = test_client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": f"Bearer {create_app['appid']}:{create_app['appkey']}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["appid"] == create_app["appid"]
    assert "perms" in data and isinstance(data["perms"], list)
    # 写入成功 audit
    cnt = asyncio.run(_count_call_logs())
    assert cnt >= 1


async def _count_call_logs() -> int:
    async with async_db_session() as db:
        return await db.scalar(select(func.count()).select_from(AiIntegrationCallLogModel)) or 0


@pytest.mark.app
def test_auth_verify_401_wrong_key(test_client, create_app: dict):
    resp = test_client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": f"Bearer {create_app['appid']}:wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.app
def test_auth_verify_401_unknown_app(test_client):
    resp = test_client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": "Bearer ai_nonexistent:xyz"},
    )
    assert resp.status_code == 401


@pytest.mark.app
def test_auth_verify_missing_or_malformed_header_401(test_client):
    assert test_client.get("/api/v1/ai/develop-api/auth/verify").status_code == 401
    assert (
        test_client.get(
            "/api/v1/ai/develop-api/auth/verify",
            headers={"Authorization": "Bearer no-colon"},
        ).status_code
        == 401
    )
