# tests/test_asset_embed_run.py
"""资产嵌入对话通道：真实工作流成功路径 + 鉴权（缺/吊销/过期）+ 会话滑动续期 + 分派垫片。

嵌入域已从开放平台剥离：令牌由 ``AssetEmbedService`` 独立绑定 ``kind+target_id`` 签发，
``/ai/embed/run`` 凭资产令牌鉴权，审计写入 ``ai_asset_embed_logs``（不再走 develop 调用日志）。
"""
import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.asset_embed.embed import AssetEmbedService
from app.plugin.module_ai.asset_embed.model import (
    AiAssetAccessTokenModel,
    AiAssetEmbedLogModel,
    AiAssetEmbedSessionModel,
)
from app.plugin.module_ai.asset_embed.service import AssetTokenService, hash_asset_token

API = "/api/v1"


def _uid() -> str:
    return uuid4().hex[:8]


def _create_workflow(test_client, auth_headers, template="结果"):
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={
            "name": f"嵌入目标-{_uid()}",
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {
                        "id": "tpl",
                        "type": "template",
                        "data": {"template": template, "output_variable": "out"},
                    },
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


def _issue(
    kind: str,
    target_id: int,
    ttl: int | None = None,
    permanent: bool = False,
    allow_domains: str | None = None,
    allow_ips: str | None = None,
) -> dict:
    """直接走服务签发资产令牌（绕过管理端权限依赖，聚焦鉴权/运行链路）。"""
    return asyncio.run(
        AssetTokenService.issue_token(
            kind,
            target_id,
            ttl=ttl,
            permanent=permanent,
            allow_domains=allow_domains,
            allow_ips=allow_ips,
        )
    )


def _token_id(token: str) -> int:
    async def _go():
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiAssetAccessTokenModel).where(
                        AiAssetAccessTokenModel.token_hash == hash_asset_token(token)
                    )
                )
            ).scalar_one()
            return row.id

    return asyncio.run(_go())


def _revoke(token: str) -> None:
    async def _go():
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiAssetAccessTokenModel).where(
                        AiAssetAccessTokenModel.token_hash == hash_asset_token(token)
                    )
                )
            ).scalar_one()
            row.revoked = True

    asyncio.run(_go())


def _expire(token: str) -> None:
    async def _go():
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiAssetAccessTokenModel).where(
                        AiAssetAccessTokenModel.token_hash == hash_asset_token(token)
                    )
                )
            ).scalar_one()
            row.expires_at = datetime.now() - timedelta(minutes=5)

    asyncio.run(_go())


def _token_auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": "127.0.0.1"}


def test_run_missing_token_401(test_client):
    r = test_client.post(
        f"{API}/ai/embed/run", json={"sid": f"sid-{_uid()}xx", "message": "hi"}
    )
    assert r.status_code == 401, r.text


def test_run_workflow_success_stream_headers_and_audit(test_client, auth_headers):
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    try:
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

        from app.plugin.module_ai.asset_embed.model import AiAssetEmbedLogModel

        async def _fetch():
            async with async_db_session() as db:
                return (
                    (
                        await db.execute(
                            select(AiAssetEmbedLogModel).where(
                                AiAssetEmbedLogModel.kind == "workflow",
                                AiAssetEmbedLogModel.target_id == wf,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

        rows = []
        for _ in range(15):  # 审计 fire-and-forget：短暂轮询等待落库
            rows = asyncio.run(_fetch())
            if rows:
                break
            time.sleep(0.2)
        assert rows, "后台审计未在 3 秒内落库"
        row = rows[0]
        assert row.result_status == "success" and row.latency_ms >= 0
        assert token not in (row.message or "")
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_revoked_token_401(test_client, auth_headers):
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    _revoke(token)
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "hi"},
            headers=_token_auth(token),
        )
        assert r.status_code == 401, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_expired_token_401(test_client, auth_headers):
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    _expire(token)
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "hi"},
            headers=_token_auth(token),
        )
        assert r.status_code == 401, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_prepare_session_slides_expiry(test_client, auth_headers):
    """闲置 TTL 滑动：复用会话时 expires_at 必须向后延长，不能按创建时间硬截止。"""
    wf = _create_workflow(test_client, auth_headers)
    ctx = SimpleNamespace(kind="workflow", target_id=wf, token_hash12="abcdef123456")
    sid = f"sid-ttl-{_uid()}"

    async def _read_expiry():
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiAssetEmbedSessionModel).where(
                        AiAssetEmbedSessionModel.kind == "workflow",
                        AiAssetEmbedSessionModel.target_id == wf,
                        AiAssetEmbedSessionModel.sid == sid,
                    )
                )
            ).scalar_one()
            return row.session_id, row.expires_at

    async def _go():
        sid1, reset1 = await AssetEmbedService.prepare_session(ctx, sid)
        session1, expires1 = await _read_expiry()
        await asyncio.sleep(0.05)
        sid2, reset2 = await AssetEmbedService.prepare_session(ctx, sid)
        session2, expires2 = await _read_expiry()
        return sid1, sid2, reset1, reset2, session1, session2, expires1, expires2

    try:
        sid1, sid2, reset1, reset2, session1, session2, expires1, expires2 = asyncio.run(_go())
        assert reset1 is True and reset2 is False
        assert sid1 == sid2 == session1 == session2  # 复用同一平台会话
        assert expires2 > expires1  # 每次使用滑动续期
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_dispatch_agent_with_anonymous_shim(monkeypatch):
    """分派 + 匿名垫片（uid=None）单元验证（不触真实模型/引擎、不落审计）。"""
    from app.plugin.module_ai.agent import service as agent_service
    from app.plugin.module_ai.sessions import service as sessions_service
    from app.plugin.module_ai.streaming import UiMessageStream

    seen_uid: list = []
    seen_target: list = []

    async def fake_messages(cls, session_id):
        return []

    monkeypatch.setattr(
        sessions_service.AiSessionService, "get_messages", classmethod(fake_messages)
    )

    async def fake_write_log(*a, **k):
        return None

    monkeypatch.setattr(AssetEmbedService, "_write_log", staticmethod(fake_write_log))

    async def _stream(target_id, msgs, auth, variables=None, session_id=None):
        seen_target.append(target_id)
        seen_uid.append(getattr(getattr(auth, "user", None), "id", None))
        ms = UiMessageStream()
        yield ms.start()
        yield ms.error("agent-未配置模型")
        yield ms.data("finish", {"reply": ""})
        yield ms.done()

    monkeypatch.setattr(
        agent_service.AiAgentService, "run_ui_stream", staticmethod(_stream)
    )

    ctx = SimpleNamespace(kind="agent", target_id=7, token_hash12="abcdef123456")

    async def _collect():
        frames = []
        async for frame in AssetEmbedService.run_stream(
            ctx, "sid-abcdefgh", 1, True, "你好", None
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(_collect())
    assert seen_uid == [None] and seen_target == [7]
    assert any("data-embed" in f.replace(" ", "") for f in frames)
    assert any("agent-未配置模型" in f for f in frames)


def test_run_whitelist_domain_403(test_client, auth_headers):
    """仅配域名白名单，但请求无来源头（也非来源域名）→ 403。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf, allow_domains="example.com")["token"]
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "hi"},
            headers=_token_auth(token),
        )
        assert r.status_code == 403, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_whitelist_domain_pass(test_client, auth_headers):
    """仅配域名白名单，请求带命中来源域名 → 200。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf, allow_domains="example.com")["token"]
    try:
        h = _token_auth(token)
        h["Origin"] = "https://example.com"
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "你好"},
            headers=h,
        )
        assert r.status_code == 200, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_whitelist_ip_pass(test_client, auth_headers):
    """仅配 IP 白名单，来源 IP 命中 → 200（X-Forwarded-For 127.0.0.1）。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf, allow_ips="127.0.0.1")["token"]
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "你好"},
            headers=_token_auth(token),
        )
        assert r.status_code == 200, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_run_whitelist_empty_unbounded(test_client, auth_headers):
    """白名单为空（NULL）→ 不限（兼容旧令牌）。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "你好"},
            headers=_token_auth(token),
        )
        assert r.status_code == 200, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_audit_log_token_and_ip(test_client, auth_headers):
    """成功调用后审计关联 token_id 与 client_ip。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    tid = _token_id(token)
    try:
        r = test_client.post(
            f"{API}/ai/embed/run",
            json={"sid": f"sid-{_uid()}xx", "message": "你好"},
            headers=_token_auth(token),
        )
        assert r.status_code == 200, r.text

        from app.plugin.module_ai.asset_embed.model import AiAssetEmbedLogModel

        async def _fetch():
            async with async_db_session() as db:
                return (
                    (
                        await db.execute(
                            select(AiAssetEmbedLogModel).where(
                                AiAssetEmbedLogModel.token_id == tid
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

        rows = []
        for _ in range(15):
            rows = asyncio.run(_fetch())
            if rows:
                break
            time.sleep(0.2)
        assert rows, "后台审计未在 3 秒内落库"
        row = rows[0]
        assert row.token_id == tid
        assert row.client_ip != ""
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_update_token_whitelist(test_client, auth_headers):
    """更新令牌白名单（域名字段）→ 列表接口返回新值。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    tid = _token_id(token)
    try:
        r = test_client.put(
            f"{API}/ai/asset-embed/tokens/{tid}",
            json={"allow_domains": "a.com"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        r2 = test_client.get(
            f"{API}/ai/asset-embed/tokens",
            params={"kind": "workflow", "target_id": wf},
            headers=auth_headers,
        )
        items = r2.json()["data"]["items"]
        row = next(i for i in items if i["id"] == tid)
        assert row["allow_domains"] == "a.com"
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )


def test_update_token_whitelist_404(test_client, auth_headers):
    r = test_client.put(
        f"{API}/ai/asset-embed/tokens/99999999",
        json={"allow_domains": "a.com"},
        headers=auth_headers,
    )
    assert r.status_code == 404, r.text


def test_list_token_logs_pagination(test_client, auth_headers):
    """令牌使用日志分页 & 按时间倒序 & 结构完整。"""
    wf = _create_workflow(test_client, auth_headers)
    token = _issue("workflow", wf)["token"]
    tid = _token_id(token)
    try:
        for i in range(3):
            r = test_client.post(
                f"{API}/ai/embed/run",
                json={"sid": f"sid-{_uid()}xx", "message": f"你好{i}"},
                headers=_token_auth(token),
            )
            assert r.status_code == 200, r.text

        # 等审计落库
        async def _count():
            async with async_db_session() as db:
                from sqlalchemy import func

                return (
                    await db.execute(
                        select(func.count())
                        .select_from(AiAssetEmbedLogModel)
                        .where(AiAssetEmbedLogModel.token_id == tid)
                    )
                ).scalar_one()

        for _ in range(15):
            if asyncio.run(_count()) >= 3:
                break
            time.sleep(0.2)

        r = test_client.get(
            f"{API}/ai/asset-embed/tokens/{tid}/logs",
            params={"page_no": 1, "page_size": 2},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] >= 3
        assert data["page_no"] == 1 and data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["has_next"] is True
        times = [it["created_time"] for it in data["items"]]
        assert times == sorted(times, reverse=True)  # 按时间倒序
        assert all(it["client_ip"] != "" for it in data["items"])
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers
        )
