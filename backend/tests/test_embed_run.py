# tests/test_embed_run.py
"""嵌入对话通道：真实工作流成功路径 + sid 绑定冲突 + 三形态分派垫片。

覆盖 Review Focus 2/3/6：
- 匿名垫片 ``user=None`` 在三形态 run 链路不炸（agent/app 分派单元验证）；
- 同 sid 换目标 → 403；
- SSE 响应头必须带共享契约（no-transform / x-accel-buffering / identity）。
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.core.database import async_db_session
from app.plugin.module_ai.develop.model import AiIntegrationAccessTokenModel
from app.plugin.module_ai.develop.service import _hash_embed_token

API = "/api/v1"


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps=None):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"嵌入对话-{_uid()}", "capabilities": caps or ["integration:embed:use"]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _create_workflow(test_client, auth_headers, template="结果"):
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={
            "name": f"嵌入目标-{_uid()}",
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {"id": "tpl", "type": "template", "data": {"template": template, "output_variable": "out"}},
                    {"id": "end", "type": "end", "data": {"output_template": "{{out}}"}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "tpl"},
                    {"id": "e2", "source": "tpl", "target": "end"},
                ],
            },
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _exchange(test_client, app, kind, target_id):
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
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": "127.0.0.1"}


def _mutate_token(token: str, **values) -> None:
    async def _go():
        async with async_db_session.begin() as db:
            await db.execute(
                update(AiIntegrationAccessTokenModel)
                .where(AiIntegrationAccessTokenModel.token_hash == _hash_embed_token(token))
                .values(**values)
            )

    asyncio.run(_go())


def _embed_logs(test_client, auth_headers):
    return test_client.get(
        f"{API}/ai/develop/call-logs",
        params={"category": "embed", "method": "EMBED", "page_size": 50},
        headers=auth_headers,
    ).json()["data"]["items"]


def test_run_workflow_success_stream_headers_and_audit(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    wf = _create_workflow(test_client, auth_headers)
    try:
        token = _exchange(test_client, app, "workflow", wf)
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "你好"},
            headers=_token_auth(token),
        )
        assert r.status_code == 200, r.text
        # SSE 共享契约（代理/压缩两坑）
        assert r.headers.get("content-encoding") == "identity"
        assert "no-transform" in r.headers.get("cache-control", "")
        assert r.headers.get("x-accel-buffering") == "no"
        assert r.headers.get("x-vercel-ai-ui-message-stream") == "v1"
        # 首帧 data-embed + 真实引擎输出 + 收尾
        assert '"data-embed"' in r.text.replace(" ", "")
        assert "结果" in r.text and "data: [DONE]" in r.text

        row = next(
            i
            for i in _embed_logs(test_client, auth_headers)
            if i["app_id"] == app["id"] and i["capability"] == "run"
        )
        assert row["status"] == "success" and row["latency_ms"] >= 0
        assert token not in str(row.get("request_body"))
    finally:
        test_client.request("DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers)
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers
        )


def test_run_sid_target_conflict_403(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    wf1 = _create_workflow(test_client, auth_headers, template="甲")
    wf2 = _create_workflow(test_client, auth_headers, template="乙")
    sid = f"sid-{_uid()}xx"
    try:
        t1 = _exchange(test_client, app, "workflow", wf1)
        r = test_client.post(
            f"{API}/ai/embed/run", json={"sid": sid, "message": "hi"}, headers=_token_auth(t1)
        )
        assert r.status_code == 200, r.text
        # 同 app 换目标、复用同一 sid → 绑定冲突
        t2 = _exchange(test_client, app, "workflow", wf2)
        r = test_client.post(
            f"{API}/ai/embed/run", json={"sid": sid, "message": "hi"}, headers=_token_auth(t2)
        )
        assert r.status_code == 403, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf1, wf2], headers=auth_headers
        )
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers
        )


def test_run_expired_token_401(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    wf = _create_workflow(test_client, auth_headers)
    try:
        token = _exchange(test_client, app, "workflow", wf)
        _mutate_token(token, expires_at=datetime.now() - timedelta(minutes=5))
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "hi"},
            headers=_token_auth(token),
        )
        assert r.status_code == 401, r.text
    finally:
        test_client.request("DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers)
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers
        )


def _run_async(coro):
    return asyncio.run(coro)


def test_run_dispatch_agent_and_app_with_anonymous_shim(monkeypatch):
    """三形态分派 + 匿名垫片（uid=None）单元验证（不触真实模型/引擎）。"""
    from app.plugin.module_ai.agent import service as agent_service
    from app.plugin.module_ai.apps import service as apps_service
    from app.plugin.module_ai.develop.embed import EmbedService
    from app.plugin.module_ai.develop.service import DevelopService
    from app.plugin.module_ai.sessions import service as sessions_service
    from app.plugin.module_ai.streaming import UiMessageStream

    seen_uid: list = []
    seen_target: list = []
    logged: list = []

    async def fake_log(cls, app, **kwargs):
        logged.append(kwargs)

    monkeypatch.setattr(DevelopService, "log_call", classmethod(fake_log))

    async def fake_messages(cls, session_id):
        return []

    monkeypatch.setattr(sessions_service.AiSessionService, "get_messages", classmethod(fake_messages))

    def _fake_stream_factory(tag: str):
        async def _stream(target_id, msgs, auth, variables=None, session_id=None):
            seen_target.append(target_id)
            seen_uid.append(getattr(getattr(auth, "user", None), "id", None))
            ms = UiMessageStream()
            yield ms.start()
            yield ms.error(f"{tag}-未配置模型")
            yield ms.data("finish", {"reply": ""})
            yield ms.done()

        return _stream

    monkeypatch.setattr(
        agent_service.AiAgentService, "run_ui_stream", staticmethod(_fake_stream_factory("agent"))
    )
    monkeypatch.setattr(apps_service, "run_app_ui_stream", _fake_stream_factory("app"))

    from app.plugin.module_ai.develop.embed import EmbedService as ES

    async def _collect(kind: str, target_id: int):
        ctx = SimpleNamespace(
            app_id=1, appid="ai_test", kind=kind, target_id=target_id,
            perms={"integration:embed:use"}, quota=None,
        )
        app_row = SimpleNamespace(id=1, appid="ai_test")
        frames = []
        async for frame in ES.run_stream(ctx, "sid-abcdefgh", app_row, 1, True, "你好", None):
            frames.append(frame)
        return frames

    agent_frames = _run_async(_collect("agent", 7))
    app_frames = _run_async(_collect("app", 9))

    assert seen_uid == [None, None] and seen_target == [7, 9]  # 垫片 uid=None 且分派到对应目标
    assert any("data-embed" in f.replace(" ", "") for f in agent_frames)
    assert any("agent-未配置模型" in f for f in agent_frames)
    assert any("app-未配置模型" in f for f in app_frames)
    # 审计：method=EMBED / category=embed / capability=run，且不含明文 token
    assert len(logged) == 2
    assert all(kw["method"] == "EMBED" and kw["capability"] == "run" for kw in logged)
    assert all("token" not in str(kw.get("request_body")) for kw in logged)
