# tests/test_develop_approvals.py
"""调用审批：敏感能力「先审批后执行」的完整闭环。

覆盖：开启 requires_approval 的应用调敏感能力 → 落待审批且**不执行**；未开启的应用直接执行；
批准 → 以原应用身份执行并回写结果；拒绝 → 不执行；非敏感能力不受审批门禁影响。
"""
from uuid import uuid4

API = "/api/v1"
AGENT_CAPS = ["integration:agent:query", "integration:agent:create", "integration:agent:delete"]


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps, *, approval: bool):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={
            "name": f"审批面-{_uid()}",
            "capabilities": caps,
            "requires_approval": approval,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _app_auth(app):
    return {
        "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def _invoke(test_client, app, code, payload):
    return test_client.post(
        f"{API}/ai/develop-api/capabilities/{code}",
        json={"payload": payload},
        headers=_app_auth(app),
    )


def _approvals(test_client, auth_headers, **params):
    query = {"page_size": 50, **params}
    return test_client.get(
        f"{API}/ai/develop/approvals", params=query, headers=auth_headers
    ).json()["data"]


def _review(test_client, auth_headers, approval_id, approve, note=None):
    return test_client.post(
        f"{API}/ai/develop/approvals/{approval_id}/review",
        json={"approve": approve, "note": note},
        headers=auth_headers,
    )


def _cleanup(test_client, auth_headers, app_id, agent_ids=()):
    for agent_id in agent_ids:
        test_client.request(
            "DELETE", f"{API}/ai/agents/delete", json=[agent_id], headers=auth_headers
        )
    test_client.request(
        "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
    )


def test_sensitive_capability_enters_pending_and_does_not_execute(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"审批-A-{_uid()}"})
        assert created.status_code == 200, created.text
        agent_id = created.json()["data"]["id"]

        # 敏感能力（agent.delete）→ 待审批，未执行
        blocked = _invoke(test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True})
        assert blocked.status_code == 200, blocked.text
        body = blocked.json()["data"]
        assert body["status"] == "pending_approval"
        approval_id = body["approval_id"]
        # 资源仍在
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 200

        pending = _approvals(test_client, auth_headers, status="pending")
        row = next(r for r in pending["items"] if r["id"] == approval_id)
        assert row["capability"] == "agent.delete"
        assert row["payload"]["agent_id"] == agent_id
        # 审计：pending 状态 + method=REST
        logs = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "status": "pending", "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert any(log["capability"] == "agent.delete" for log in logs), logs

        # 批准 → 真正执行（Agent 被删）
        ok = _review(test_client, auth_headers, approval_id, True, note="同意")
        assert ok.status_code == 200, ok.text
        assert ok.json()["data"]["status"] == "approved"
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 404
        agent_id = None
    finally:
        _cleanup(test_client, auth_headers, app["id"], [agent_id] if agent_id else [])


def test_non_sensitive_capability_bypasses_approval(test_client, auth_headers):
    """开启审批的应用，非敏感能力（agent.create/list）照常直接执行。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        r = _invoke(test_client, app, "agent.create", {"agent_name": f"审批-B-{_uid()}"})
        assert r.status_code == 200, r.text
        assert "id" in r.json()["data"]
        agent_id = r.json()["data"]["id"]
        assert _approvals(test_client, auth_headers, status="pending")["items"] == [] or all(
            row["capability"] != "agent.create"
            for row in _approvals(test_client, auth_headers, status="pending")["items"]
        )
    finally:
        _cleanup(test_client, auth_headers, app["id"], [agent_id] if agent_id else [])


def test_approval_disabled_app_executes_immediately(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=False)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"审批-C-{_uid()}"})
        agent_id = created.json()["data"]["id"]
        deleted = _invoke(test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True})
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["data"]["deleted"] == agent_id
        agent_id = None
    finally:
        _cleanup(test_client, auth_headers, app["id"], [agent_id] if agent_id else [])


def test_approval_keeps_full_payload():
    """审批行必须保存完整入参（仅剔除凭证），不能存审计用的截断体。

    否则长文本参数（如工作流提示/超参）在批准执行时会被截断，语义改变。
    """
    from app.plugin.module_ai.develop.openapi import _sanitize_body, _strip_secrets

    payload = {"name": "x" * 400, "appkey": "secret-value", "n": 3}
    audit = _sanitize_body(payload)
    stored = _strip_secrets(payload)
    assert len(audit["name"]) == 200  # 审计体截断
    assert len(stored["name"]) == 400  # 审批体保留完整
    assert stored["appkey"] == "***"
    assert stored["n"] == 3


def test_reject_keeps_resource_untouched(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"审批-D-{_uid()}"})
        agent_id = created.json()["data"]["id"]
        blocked = _invoke(test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True})
        approval_id = blocked.json()["data"]["approval_id"]

        rejected = _review(test_client, auth_headers, approval_id, False, note="不允许删除")
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["data"]["status"] == "rejected"
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 200

        # 重复审批 → 400（已处理）
        again = _review(test_client, auth_headers, approval_id, True)
        assert again.status_code == 400, again.text
    finally:
        _cleanup(test_client, auth_headers, app["id"], [agent_id] if agent_id else [])


def test_approval_review_requires_permission(test_client, auth_headers):
    """审批接口需要 module_ai:develop:approve（admin 有；此处校验未登录场景 401/403）。"""
    r = test_client.post(f"{API}/ai/develop/approvals/1/review", json={"approve": True})
    assert r.status_code in (401, 403), r.text


def _backdate(approval_id: int, hours: int) -> None:
    """把审批行的申请时间往前挪（测试用；HTTP 面没有改时间的入口）。"""
    import asyncio
    from datetime import datetime, timedelta

    from sqlalchemy import update

    from app.core.database import async_db_session
    from app.plugin.module_ai.develop.model import AiIntegrationApprovalModel

    async def _run() -> None:
        async with async_db_session.begin() as db:
            await db.execute(
                update(AiIntegrationApprovalModel)
                .where(AiIntegrationApprovalModel.id == approval_id)
                .values(created_time=datetime.now() - timedelta(hours=hours))
            )

    asyncio.run(_run())


def test_expire_stale_approvals_closes_and_audits(test_client, auth_headers):
    """超时未处理的待审批 → 自动关闭为 expired，并写一条 expired 审计。"""
    from app.plugin.module_ai.develop.approvals import expire_stale_approvals

    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"超时-{_uid()}"})
        agent_id = created.json()["data"]["id"]
        blocked = _invoke(
            test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True}
        )
        approval_id = blocked.json()["data"]["approval_id"]

        _backdate(approval_id, hours=48)
        assert asyncio_run(expire_stale_approvals) == 1

        rows = _approvals(test_client, auth_headers, app_id=app["id"])["items"]
        row = next(r for r in rows if r["id"] == approval_id)
        assert row["status"] == "expired"
        assert "小时未处理" in (row["review_note"] or "") and "自动关闭" in (row["review_note"] or "")

        logs = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "status": "expired", "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert any(log["capability"] == "agent.delete" for log in logs), logs

        # 关掉的审批不能再被批准执行
        again = _review(test_client, auth_headers, approval_id, True)
        assert again.status_code == 400, again.text
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 200
        agent_id = None
    finally:
        _cleanup(test_client, auth_headers, app["id"], [agent_id] if agent_id else [])


def test_expire_stale_keeps_fresh_pending(test_client, auth_headers):
    """刚提交的 pending 不受影响（TTL 未到）。"""
    from app.plugin.module_ai.develop.approvals import expire_stale_approvals

    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"新鲜-{_uid()}"})
        agent_id = created.json()["data"]["id"]
        blocked = _invoke(
            test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True}
        )
        approval_id = blocked.json()["data"]["approval_id"]

        asyncio_run(expire_stale_approvals, 24)

        rows = _approvals(test_client, auth_headers, app_id=app["id"])["items"]
        row = next(r for r in rows if r["id"] == approval_id)
        assert row["status"] == "pending"
    finally:
        if agent_id:
            test_client.request(
                "DELETE", f"{API}/ai/agents/delete", json=[agent_id], headers=auth_headers
            )
        _cleanup(test_client, auth_headers, app["id"])


def test_pending_approval_notifies_admin(test_client, auth_headers):
    """有待审批时给超级管理员（role_id=1）发站内通知。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"通知-{_uid()}"})
        agent_id = created.json()["data"]["id"]
        blocked = _invoke(
            test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True}
        )
        approval_id = blocked.json()["data"]["approval_id"]

        items = test_client.get(
            f"{API}/system/notification/list", params={"page_size": 20}, headers=auth_headers
        ).json()["data"]["items"]
        assert any(
            "待审批" in (n.get("title") or "") and str(approval_id) in str(n.get("module_id"))
            for n in items
        ), [n.get("title") for n in items]
    finally:
        if agent_id:
            test_client.request(
                "DELETE", f"{API}/ai/agents/delete", json=[agent_id], headers=auth_headers
            )
        _cleanup(test_client, auth_headers, app["id"])


def asyncio_run(fn, *args):
    """在测试进程里跑一次异步函数（与既有测试同款用法）。"""
    import asyncio

    return asyncio.run(fn(*args))
