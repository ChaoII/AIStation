# tests/test_develop_chat.py
"""开放面 chat / bot 能力：会话归属隔离、聚合回复、权限点独立。

覆盖 Review Focus 第 1 条（跨应用会话不可见）与第 2 条（bot.use 需独立权限点）。
"""
from uuid import uuid4

API = "/api/v1"
CHAT_CAPS = ["integration:chat:send", "integration:chat:query"]
CHAT_CAPS_NO_BOT = CHAT_CAPS  # bot.use 需要 integration:bot:use，故意不给


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"对话面-{_uid()}", "capabilities": caps},
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


def _create_template_workflow(test_client, auth_headers, text="开放面回复：你好"):
    """建一个不依赖模型的工作流（start → template → end），供对话聚合用例使用。"""
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "tpl",
                "type": "template",
                "data": {"template": text, "output_variable": "out"},
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{out}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "tpl"},
            {"id": "e2", "source": "tpl", "target": "end"},
        ],
    }
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={"name": f"对话目标-{_uid()}", "graph": graph},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _cleanup(test_client, auth_headers, app_id=None, workflow_id=None):
    if workflow_id:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[workflow_id], headers=auth_headers
        )
    if app_id:
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
        )


def test_chat_send_returns_reply_and_binds_session(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, CHAT_CAPS)
    wf = None
    try:
        wf = _create_template_workflow(test_client, auth_headers, text="开放面回复：你好")
        r = _invoke(
            test_client,
            app,
            "chat.send",
            {"kind": "workflow", "target_id": wf, "message": "在吗", "sid": f"sid{_uid()}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "开放面回复：你好" in data["reply"]
        assert isinstance(data["session_id"], int)

        # 续接：同 sid 再发一次仍复用同一会话
        again = _invoke(
            test_client,
            app,
            "chat.send",
            {"kind": "workflow", "target_id": wf, "message": "再来", "sid": data["sid"]},
        )
        assert again.status_code == 200, again.text
        assert again.json()["data"]["session_id"] == data["session_id"]
        assert again.json()["data"]["session_reset"] is False

        # 会话与消息可查（本应用）
        sessions = _invoke(test_client, app, "chat.sessions", {})
        assert sessions.status_code == 200, sessions.text
        ids = [item["id"] for item in sessions.json()["data"]["items"]]
        assert data["session_id"] in ids
        messages = _invoke(test_client, app, "chat.messages", {"session_id": data["session_id"]})
        assert messages.status_code == 200, messages.text
        assert len(messages.json()["data"]["items"]) >= 2
    finally:
        _cleanup(test_client, auth_headers, app["id"], wf)


def test_chat_session_isolation_between_apps(test_client, auth_headers):
    """Review Focus 1：B 应用读不到 A 应用的会话消息。"""
    app_a = _create_app(test_client, auth_headers, CHAT_CAPS)
    app_b = _create_app(test_client, auth_headers, CHAT_CAPS)
    wf = None
    try:
        wf = _create_template_workflow(test_client, auth_headers)
        sent = _invoke(
            test_client,
            app_a,
            "chat.send",
            {"kind": "workflow", "target_id": wf, "message": "A 的消息", "sid": f"sid{_uid()}"},
        )
        assert sent.status_code == 200, sent.text
        session_id = sent.json()["data"]["session_id"]

        leaked = _invoke(test_client, app_b, "chat.messages", {"session_id": session_id})
        assert leaked.status_code == 404, leaked.text
        b_sessions = _invoke(test_client, app_b, "chat.sessions", {})
        assert session_id not in [i["id"] for i in b_sessions.json()["data"]["items"]]
    finally:
        _cleanup(test_client, auth_headers, app_a["id"], wf)
        _cleanup(test_client, auth_headers, app_b["id"])


def test_internal_session_not_visible_to_app(test_client, auth_headers):
    """平台内部会话（无 source_app_id）不得出现在开放面会话列表。"""
    app = _create_app(test_client, auth_headers, CHAT_CAPS)
    created = test_client.post(
        f"{API}/ai/sessions/create",
        json={"title": f"内部会话-{_uid()}"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    internal_id = created.json()["data"]["id"]
    try:
        sessions = _invoke(test_client, app, "chat.sessions", {})
        assert internal_id not in [i["id"] for i in sessions.json()["data"]["items"]]
        leaked = _invoke(test_client, app, "chat.messages", {"session_id": internal_id})
        assert leaked.status_code == 404, leaked.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/sessions/delete", json=[internal_id], headers=auth_headers
        )
        _cleanup(test_client, auth_headers, app["id"])


def test_bot_use_requires_bot_perm(test_client, auth_headers):
    """Review Focus 2：只有 chat 权限的应用调 bot.use → 403 + denied 审计。"""
    app = _create_app(test_client, auth_headers, CHAT_CAPS_NO_BOT)
    try:
        r = _invoke(test_client, app, "bot.use", {"app_id": 1, "message": "你好"})
        assert r.status_code == 403, r.text
        logs = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "status": "denied", "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert any(log["capability"] == "bot.use" for log in logs), logs
    finally:
        _cleanup(test_client, auth_headers, app["id"])
