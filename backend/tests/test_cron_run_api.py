"""定时任务「立即执行一次」接口（`POST /ai/workspace/cron/{id}/run`）。

配套改动：cron 系列接口权限从 `module_ai:workspace:*` 切换为独立的 `module_ai:cron:*`
（定时任务独立菜单页落地，权限与工作台分离）；本文件同时覆盖：

1. 存在的任务 → 200「已触发执行」（执行入后台，与调度器同一执行路径，
   目标执行失败只记日志、不抛出，见 `run_scheduled_workspace_cron`）；
2. 不存在的 id → 400「定时任务不存在」；
3. 列表接口在 `module_ai:cron:query` 权限下可用（admin 超管恒通过）。

需要应用（`test_client`）的用例在 ``PYTEST_NO_APP=1`` 快速模式下自动 skip。
"""

import uuid


def _create_cron(test_client, auth_headers) -> int:
    """建一个最小的启用任务（目标为不存在的工作流：执行只记日志失败，不影响断言）。"""
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": f"pytest-cron-run-{uuid.uuid4().hex[:6]}",
            "description": "立即执行接口用例",
            "trigger": "cron",
            "trigger_args": "0 9 * * mon",
            "target_type": "workflow",
            "target_id": 999999,
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_run_existing_cron_accepted(test_client, auth_headers):
    """存在的任务 → 200「已触发执行」，接口只入队不等待目标跑完。"""
    cron_id = _create_cron(test_client, auth_headers)
    try:
        r = test_client.post(
            f"/api/v1/ai/workspace/cron/{cron_id}/run", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["msg"] == "已触发执行"
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cron_id, headers=auth_headers
        )


def test_run_missing_cron_400(test_client, auth_headers):
    """不存在的 id → 400，且给出可读原因（前端直接回显）。"""
    r = test_client.post("/api/v1/ai/workspace/cron/99999999/run", headers=auth_headers)
    assert r.status_code == 400, r.text
    assert "不存在" in r.json()["msg"]


def test_cron_list_on_cron_permission(test_client, auth_headers):
    """列表接口带 needs_review 标注（独立菜单页「需人工确认」列的数据源）。"""
    r = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert isinstance(items, list)
    for row in items:
        assert "needs_review" in row


# ============================================================ 调度执行目标：agent/app 真执行

def test_run_target_agent_consumes_stream(monkeypatch):
    """agent 目标：消费 run_ui_stream 的完整流（不落会话、不抛），并带固定调度消息。"""
    import asyncio

    from app.plugin.module_ai.agent.service import AiAgentService
    from app.plugin.module_ai.workspace import service as ws

    seen: dict = {}

    async def fake_run_ui_stream(cls, agent_id, ui_messages, auth, variables=None, session_id=None):
        seen.update(agent_id=agent_id, messages=ui_messages, auth=auth, session_id=session_id)
        yield "frame-1"
        yield "frame-2"

    monkeypatch.setattr(
        AiAgentService, "run_ui_stream", classmethod(fake_run_ui_stream)
    )
    asyncio.run(ws.WorkspaceService._run_target("agent", 42))

    assert seen["agent_id"] == 42
    # 固定调度消息（agent guardrail 拒绝空输入）
    assert seen["messages"] == [{"role": "user", "content": "按你的配置执行"}]
    # 调度上下文没有登录用户：auth=None / session_id=None（不落用户会话）
    assert seen["auth"] is None and seen["session_id"] is None


def test_run_target_app_consumes_stream(monkeypatch):
    """app 目标：消费 run_app_ui_stream 的完整流，口径与 agent 一致。"""
    import asyncio

    from app.plugin.module_ai.apps import service as app_service
    from app.plugin.module_ai.workspace import service as ws

    seen: dict = {}

    async def fake_run_app_ui_stream(app_id, ui_messages, auth, variables=None, session_id=None):
        seen.update(app_id=app_id, messages=ui_messages, auth=auth, session_id=session_id)
        yield "frame"

    monkeypatch.setattr(app_service, "run_app_ui_stream", fake_run_app_ui_stream)
    asyncio.run(ws.WorkspaceService._run_target("app", 7))

    assert seen["app_id"] == 7
    assert seen["messages"] == [{"role": "user", "content": "按你的配置执行"}]
    assert seen["auth"] is None and seen["session_id"] is None


def test_run_target_unknown_type_does_not_raise():
    """未知目标类型只告警，不抛（避免单行坏配置拖垮调度作业）。"""
    import asyncio

    from app.plugin.module_ai.workspace import service as ws

    asyncio.run(ws.WorkspaceService._run_target("unknown", 1))
