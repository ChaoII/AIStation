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
