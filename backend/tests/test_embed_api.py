# tests/test_embed_api.py
"""嵌入公开面：token 鉴权依赖（401 家族）与 /embed/meta。

覆盖 Review Focus 第 1 条：过期/吊销/停用每请求重校验，一律 401；
以及「权限收回即时生效（403）」与 use_count 累计。
"""
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.database import async_db_session
from app.plugin.module_ai.develop.model import AiIntegrationAccessTokenModel
from app.plugin.module_ai.develop.service import _hash_embed_token

API = "/api/v1"


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps=None):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"嵌入公开面-{_uid()}", "capabilities": caps or ["integration:embed:use"]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _create_workflow(test_client, auth_headers):
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={
            "name": f"嵌入目标-{_uid()}",
            "graph": {"nodes": [{"id": "start", "type": "start", "data": {}}], "edges": []},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _exchange(test_client, app, target_id, kind="workflow"):
    r = test_client.post(
        f"{API}/ai/develop-api/auth/token",
        json={"kind": kind, "target_id": target_id},
        headers={
            "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
            "X-Forwarded-For": "127.0.0.1",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _token_auth(token):
    # X-Forwarded-For：匿名 POST 经 OperationLogRoute 记操作日志时需要合法 IP
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": "127.0.0.1"}


def _mutate_token(token: str, **values) -> None:
    """直接改令牌行（模拟过期/吊销，管理端点尚未覆盖这两个动作）。"""

    async def _go():
        async with async_db_session.begin() as db:
            await db.execute(
                update(AiIntegrationAccessTokenModel)
                .where(AiIntegrationAccessTokenModel.token_hash == _hash_embed_token(token))
                .values(**values)
            )

    asyncio.run(_go())


def _read_token(token: str) -> dict:
    async def _go():
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiIntegrationAccessTokenModel).where(
                        AiIntegrationAccessTokenModel.token_hash == _hash_embed_token(token)
                    )
                )
            ).scalar_one()
            return {"use_count": row.use_count, "last_used_at": row.last_used_at}

    return asyncio.run(_go())


@pytest.fixture()
def embed_env(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    wf = _create_workflow(test_client, auth_headers)
    yield {"app": app, "workflow_id": wf}
    test_client.request("DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers)
    test_client.request("DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers)


def test_meta_missing_header_401(test_client, embed_env):
    r = test_client.get(f"{API}/ai/embed/meta")
    assert r.status_code == 401, r.text


def test_meta_garbage_token_401(test_client, embed_env):
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth("not-a-real-token"))
    assert r.status_code == 401, r.text


def test_meta_expired_token_401(test_client, embed_env):
    token = _exchange(test_client, embed_env["app"], embed_env["workflow_id"])
    _mutate_token(token, expires_at=datetime.now() - timedelta(hours=1))
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
    assert r.status_code == 401, r.text


def test_meta_revoked_token_401(test_client, embed_env):
    token = _exchange(test_client, embed_env["app"], embed_env["workflow_id"])
    _mutate_token(token, revoked=True)
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
    assert r.status_code == 401, r.text


def test_meta_after_app_disabled_401(test_client, embed_env, auth_headers):
    token = _exchange(test_client, embed_env["app"], embed_env["workflow_id"])
    r = test_client.put(
        f"{API}/ai/develop/update/{embed_env['app']['id']}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
    assert r.status_code == 401, r.text


def test_meta_after_perm_removed_403(test_client, embed_env, auth_headers):
    token = _exchange(test_client, embed_env["app"], embed_env["workflow_id"])
    r = test_client.put(
        f"{API}/ai/develop/update/{embed_env['app']['id']}",
        json={"capabilities": []},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
    assert r.status_code == 403, r.text


def test_meta_ok_and_use_count(test_client, embed_env):
    token = _exchange(test_client, embed_env["app"], embed_env["workflow_id"])
    r = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["kind"] == "workflow" and data["target_id"] == embed_env["workflow_id"]
    assert data["name"] and "welcome" in data and data["expire_at"]
    row = _read_token(token)
    assert row["use_count"] >= 1 and row["last_used_at"] is not None
