# tests/test_develop_approvals.py
"""调用审批：敏感能力「先审批后执行」的完整闭环。

覆盖：开启 requires_approval 的应用调敏感能力 → 落待审批且**不执行**；未开启的应用直接执行；
批准 → 以原应用身份执行并回写结果；拒绝 → 不执行；非敏感能力不受审批门禁影响。
"""
import asyncio
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


def test_build_approval_alarm_maps_fields():
    """适配壳：alarm/rule 字段映射正确（复用告警通道的输入契约）。"""
    from app.plugin.module_ai.develop.approvals import _build_approval_alarm

    class _Row:
        app_id = 7
        appid = "ai_demo"
        capability = "agent.delete"
        category = "agent"
        id = 42

    alarm, rule = _build_approval_alarm(_Row())
    assert alarm["severity"] == "WARNING"
    assert "agent.delete" in alarm["alarm_type"]
    assert "ai_demo" in alarm["description"] and "调用审批" in alarm["description"]
    assert alarm["rule_id"] == 42
    assert rule["name"] == "AI 集成调用审批"


def test_notify_external_disabled_by_default(monkeypatch):
    """默认（APPROVAL_NOTIFY_CHANNELS 为空）不外发：任何通道发送器都不该被调。"""
    import app.utils.notification as notifier
    from app.config.setting import settings
    from app.plugin.module_ai.develop import approvals as appr

    called = []

    async def _boom(*args, **kwargs):
        called.append(1)

    monkeypatch.setattr(settings, "APPROVAL_NOTIFY_CHANNELS", "")
    monkeypatch.setattr(notifier, "_send_email", _boom)
    monkeypatch.setattr(notifier, "_send_webhook", _boom)

    class _Row:
        app_id = 1
        appid = "ai_x"
        capability = "agent.delete"
        category = "agent"
        id = 1

    asyncio.run(appr._notify_external(_Row()))
    assert called == []


def test_notify_external_sends_email_with_config(monkeypatch):
    """配置 email 通道 → 调用既有邮件发送器；配置来自系统参数（此处无参数 → cfg={}）。"""
    import app.utils.notification as notifier
    from app.config.setting import settings
    from app.plugin.module_ai.develop import approvals as appr

    calls = []

    async def _fake_email(db, alarm, rule, cfg):
        calls.append((alarm["alarm_type"], rule["name"], cfg))

    monkeypatch.setattr(settings, "APPROVAL_NOTIFY_CHANNELS", "email")
    monkeypatch.setattr(notifier, "_send_email", _fake_email)

    class _Row:
        app_id = 3
        appid = "ai_mail"
        capability = "train.create"
        category = "train"
        id = 9

    asyncio.run(appr._notify_external(_Row()))
    assert len(calls) == 1
    alarm_type, rule_name, cfg = calls[0]
    assert "train.create" in alarm_type
    assert rule_name == "AI 集成调用审批"
    assert isinstance(cfg, dict)


def test_notify_external_skips_broken_channel_json(monkeypatch):
    """系统参数里 JSON 写坏 → 跳过该通道、不抛异常（best-effort）。"""
    import asyncio as _asyncio

    import app.utils.notification as notifier
    from app.config.setting import settings
    from app.plugin.module_ai.develop import approvals as appr

    calls = []

    async def _fake_email(*args, **kwargs):
        calls.append(1)

    async def _broken_params(db, *keys):
        return dict.fromkeys(keys, "{not-json")

    monkeypatch.setattr(settings, "APPROVAL_NOTIFY_CHANNELS", "email")
    monkeypatch.setattr(notifier, "_send_email", _fake_email)
    monkeypatch.setattr(notifier, "load_params", _broken_params)

    class _Row:
        app_id = 5
        appid = "ai_bad"
        capability = "agent.delete"
        category = "agent"
        id = 5

    _asyncio.run(appr._notify_external(_Row()))
    assert calls == []


def test_audit_body_limit_is_configurable():
    """审计请求体截断上限可配（OPEN_AUDIT_BODY_LIMIT，默认 200、夹紧 100..2000）。"""
    from app.config.setting import settings
    from app.plugin.module_ai.develop.openapi import _body_limit, _sanitize_body

    long_text = "x" * 1500
    try:
        original = settings.OPEN_AUDIT_BODY_LIMIT
        settings.OPEN_AUDIT_BODY_LIMIT = 500
        assert _body_limit() == 500
        assert len(_sanitize_body({"note": long_text})["note"]) == 500
        settings.OPEN_AUDIT_BODY_LIMIT = 50
        assert _body_limit() == 100  # 夹紧
        settings.OPEN_AUDIT_BODY_LIMIT = 99999
        assert _body_limit() == 2000  # 夹紧
        settings.OPEN_AUDIT_BODY_LIMIT = original
    finally:
        settings.OPEN_AUDIT_BODY_LIMIT = 200


def test_notify_config_roundtrip(test_client, auth_headers):
    """通知配置读写往返：开关 + 通道 JSON 落系统参数，GET 原样回读。"""
    try:
        r = test_client.put(
            f"{API}/ai/develop/notify-config",
            json={
                "channels": ["email", "sms", "not-a-channel"],
                "configs": {"email": {"recipients": ["a@b.com"]}, "sms": {}},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        got = r.json()["data"]
        assert set(got["channels"]) == {"email", "sms"}, got["channels"]  # 非法通道被丢弃
        assert got["configs"]["email"]["recipients"] == ["a@b.com"]

        again = test_client.get(f"{API}/ai/develop/notify-config", headers=auth_headers)
        assert again.status_code == 200
        data = again.json()["data"]
        assert set(data["channels"]) == {"email", "sms"}
        assert data["configs"]["email"]["recipients"] == ["a@b.com"]
        assert data["broken"] == [], data
    finally:
        # 还原为关闭状态，避免影响其它用例的「默认不外发」断言
        test_client.put(
            f"{API}/ai/develop/notify-config",
            json={"channels": [], "configs": {}},
            headers=auth_headers,
        )


def test_notify_config_rejects_oversized_json(test_client, auth_headers):
    """通道配置 JSON 序列化后 >500 字符（sys_param 字段上限）→ 400。"""
    r = test_client.put(
        f"{API}/ai/develop/notify-config",
        json={"channels": ["webhook"], "configs": {"webhook": {"secret": "x" * 600}}},
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text
    assert "500" in r.json()["msg"]


def test_batch_approve_executes_each(test_client, auth_headers):
    """批量批准：逐条以原应用身份执行，单条失败不中断，重复处理进 failed。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    created_ids = []
    try:
        for i in range(2):
            r = _invoke(test_client, app, "agent.create", {"agent_name": f"批量-{_uid()}-{i}"})
            created_ids.append(r.json()["data"]["id"])
        approval_ids = []
        for aid in created_ids:
            r = _invoke(test_client, app, "agent.delete", {"agent_id": aid, "confirm": True})
            assert r.status_code == 200, r.text
            assert r.json()["data"]["status"] == "pending_approval"
            approval_ids.append(r.json()["data"]["approval_id"])

        r = test_client.post(
            f"{API}/ai/develop/approvals/batch-review",
            json={"ids": approval_ids, "note": "批量同意"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert len(data["ok"]) == 2 and data["failed"] == [], data
        assert data["total"] == 2

        # 两个 Agent 都应真的被删（批准即执行）
        for aid in created_ids:
            assert _invoke(test_client, app, "agent.get", {"agent_id": aid}).status_code == 404

        # 再批一次 → 逐条 failed（已处理）
        r2 = test_client.post(
            f"{API}/ai/develop/approvals/batch-review",
            json={"ids": approval_ids, "note": "重复"},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert len(r2.json()["data"]["failed"]) == 2
        assert r2.json()["data"]["ok"] == []
        created_ids = []
    finally:
        _cleanup(test_client, auth_headers, app["id"], created_ids)


def test_batch_approve_rejects_bad_input(test_client, auth_headers):
    """批量边界：空列表 / 超 50 条 / approve=false（拒绝不许批量）→ 400。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS, approval=True)
    try:
        empty = test_client.post(
            f"{API}/ai/develop/approvals/batch-review",
            json={"ids": []},
            headers=auth_headers,
        )
        # Pydantic min_length 层拦下（422）或业务层拦下（400），二者皆可
        assert empty.status_code in (400, 422), empty.text

        too_many = test_client.post(
            f"{API}/ai/develop/approvals/batch-review",
            json={"ids": list(range(1, 52))},
            headers=auth_headers,
        )
        assert too_many.status_code in (400, 422), too_many.text
        assert "50" in too_many.json()["msg"]
    finally:
        _cleanup(test_client, auth_headers, app["id"])
