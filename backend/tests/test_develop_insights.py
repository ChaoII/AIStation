# tests/test_develop_insights.py
"""调用概览 / 时间范围过滤 / CSV 导出 / 能力试调 / 配额用量。

覆盖新能力的行为契约，以及「时间范围过滤真的生效」这类容易写成摆设的查询。
"""
from datetime import datetime, timedelta
from uuid import uuid4

API = "/api/v1"
CAPS = ["integration:agent:query", "integration:agent:create", "integration:agent:delete"]


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, *, approval=False, quota=None):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={
            "name": f"概览面-{_uid()}",
            "capabilities": CAPS,
            "requires_approval": approval,
            "quota": quota,
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


def _cleanup(test_client, auth_headers, app_id):
    test_client.request("DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers)


def test_stats_shape_and_counts(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    try:
        _invoke(test_client, app, "agent.list", {})
        r = test_client.get(f"{API}/ai/develop/stats", params={"days": 7}, headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["today"]["calls"] >= 1
        assert 0.0 <= data["today"]["success_rate"] <= 1.0
        assert len(data["series"]) == 7
        # 趋势按日期升序、字段齐全
        assert data["series"][-1]["date"] == datetime.now().strftime("%Y-%m-%d")
        assert {"calls", "success", "failed", "denied", "pending"} <= set(data["series"][0])
        assert data["apps"]["total"] >= 1
        assert "pending" in data["approvals"]
        assert any(item["capability"] == "agent.list" for item in data["top_capabilities"])
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_call_log_filters_by_time_range(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    try:
        _invoke(test_client, app, "agent.list", {})
        now = datetime.now()
        future = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        past = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        inside = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "start_time": past, "end_time": future, "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert inside, "时间范围内应有日志"

        outside = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "start_time": future, "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert outside == [], "起始时间在未来时不应返回日志"

        bad = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"start_time": "not-a-time"},
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_call_logs_csv_export(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    try:
        _invoke(test_client, app, "agent.list", {})
        r = test_client.get(
            f"{API}/ai/develop/call-logs/export",
            params={"app_id": app["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers.get("content-disposition", "")
        text = r.content.decode("utf-8-sig")
        header = text.splitlines()[0]
        assert "时间" in header and "能力" in header and "状态" in header
        assert app["appid"] in text
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_app_usage_and_quota(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, quota={"agent": 100})
    try:
        _invoke(test_client, app, "agent.list", {})
        _invoke(test_client, app, "agent.list", {})
        r = test_client.get(f"{API}/ai/develop/apps/{app['id']}/usage", headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["usage"].get("agent", 0) >= 2
        assert data["quota"]["agent"] == 100
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_capability_try_runs_without_creating_approval(test_client, auth_headers):
    """试调跳过审批门禁：敏感能力也不会进待审批队列，但会走权限与审计。"""
    app = _create_app(
        test_client,
        auth_headers,
        approval=True,
        quota=None,
    )
    agent_id = None
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"试调-{_uid()}"})
        agent_id = created.json()["data"]["id"]

        # 通过管理面「试调」调用 agent.delete（敏感能力）
        r = test_client.post(
            f"{API}/ai/develop/apps/{app['id']}/try",
            json={"capability": "agent.delete", "payload": {"agent_id": agent_id, "confirm": True}},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["deleted"] == agent_id
        agent_id = None

        # 不应产生新的待审批记录
        pending = test_client.get(
            f"{API}/ai/develop/approvals",
            params={"app_id": app["id"], "status": "pending", "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert pending == []

        # 试调也写审计（request_path=/try/...）
        logs = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert any((log["request_path"] or "").startswith("/try/") for log in logs)
    finally:
        if agent_id:
            test_client.request(
                "DELETE", f"{API}/ai/agents/delete", json=[agent_id], headers=auth_headers
            )
        _cleanup(test_client, auth_headers, app["id"])


def test_try_unknown_capability_or_missing_perm(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    try:
        unknown = test_client.post(
            f"{API}/ai/develop/apps/{app['id']}/try",
            json={"capability": "agent.nope", "payload": {}},
            headers=auth_headers,
        )
        assert unknown.status_code == 404, unknown.text

        denied = test_client.post(
            f"{API}/ai/develop/apps/{app['id']}/try",
            json={"capability": "train.list", "payload": {}},
            headers=auth_headers,
        )
        assert denied.status_code == 403, denied.text
        assert "无权限" in denied.json()["msg"]
    finally:
        _cleanup(test_client, auth_headers, app["id"])
