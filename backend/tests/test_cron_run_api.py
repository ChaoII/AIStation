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


# ============================================================ 结果回写：成功摘正文 / 失败认 RunError


def test_run_target_collects_run_content_text(monkeypatch):
    """RunContent 帧要攒成正文（卡片「上次结果」用它）。"""
    import asyncio

    from app.plugin.module_ai.agent.service import AiAgentService
    from app.plugin.module_ai.assistant.agno_service import agno_event_frame
    from app.plugin.module_ai.workspace import service as ws

    async def fake_run_ui_stream(cls, agent_id, ui_messages, auth, variables=None, session_id=None):
        yield agno_event_frame("RunContent", {"content": "数据集 273 个，"})
        yield agno_event_frame("RunContent", {"content": "标注任务 237 个。"})

    monkeypatch.setattr(AiAgentService, "run_ui_stream", classmethod(fake_run_ui_stream))
    text, err, tools = asyncio.run(ws.WorkspaceService._run_target("agent", 42))
    assert err is None
    assert text == "数据集 273 个，标注任务 237 个。"
    assert tools == []


def test_run_target_treats_runerror_frame_as_failure(monkeypatch):
    """智能体被禁用时接口不抛异常、只发一帧 RunError：必须算失败，不能记成成功。"""
    import asyncio

    from app.plugin.module_ai.agent.service import AiAgentService
    from app.plugin.module_ai.assistant.agno_service import agno_error_frame
    from app.plugin.module_ai.workspace import service as ws

    async def fake_run_ui_stream(cls, agent_id, ui_messages, auth, variables=None, session_id=None):
        yield agno_error_frame("智能体不存在或未启用")

    monkeypatch.setattr(AiAgentService, "run_ui_stream", classmethod(fake_run_ui_stream))
    text, err, tools = asyncio.run(ws.WorkspaceService._run_target("agent", 42))
    assert text == ""
    assert err == "智能体不存在或未启用"
    assert tools == []


def test_run_scheduled_skips_when_locked(monkeypatch):
    """同一任务不允许并发：闸门里已有记录时，这一轮直接跳过（不跑执行体）。"""
    import asyncio
    import time as _t

    from app.plugin.module_ai.workspace import service as ws

    cid = 987654321
    called: list = []

    async def fake_once(x):
        called.append(x)

    monkeypatch.setattr(ws, "_run_cron_once", fake_once)
    ws._RUNNING_CRONS[cid] = _t.monotonic()
    try:
        asyncio.run(ws.run_scheduled_workspace_cron(cid))
        assert called == [], "锁没生效：这一轮不该执行"
    finally:
        ws._RUNNING_CRONS.pop(cid, None)


def test_run_scheduled_releases_lock_after_run(monkeypatch):
    """跑完必须解锁，否则这个任务以后再也不会执行。"""
    import asyncio

    from app.plugin.module_ai.workspace import service as ws

    cid = 135792468
    called: list = []

    async def fake_once(x):
        called.append(x)

    monkeypatch.setattr(ws, "_run_cron_once", fake_once)
    asyncio.run(ws.run_scheduled_workspace_cron(cid))
    assert called == [cid]
    assert cid not in ws._RUNNING_CRONS


def test_run_scheduled_releases_lock_on_error(monkeypatch):
    """执行体抛异常也要解锁（否则一次失败把任务永久锁死）。"""
    import asyncio

    from app.plugin.module_ai.workspace import service as ws

    cid = 246813579

    async def boom(_x):
        raise RuntimeError("boom")

    monkeypatch.setattr(ws, "_run_cron_once", boom)
    try:
        asyncio.run(ws.run_scheduled_workspace_cron(cid))
    except RuntimeError:
        pass
    assert cid not in ws._RUNNING_CRONS


def test_cron_running_guard_releases_stale_lock():
    """卡死的执行记录超过阈值要自动放开，否则任务被永远锁死。"""
    import time as _t

    from app.plugin.module_ai.workspace import service as ws

    cid = 123456789
    ws._RUNNING_CRONS[cid] = _t.monotonic() - (ws._CRON_LOCK_STALE_SEC + 5)
    try:
        assert ws.cron_is_running(cid) is False
        assert cid not in ws._RUNNING_CRONS
    finally:
        ws._RUNNING_CRONS.pop(cid, None)


def test_run_target_collects_tool_calls(monkeypatch):
    """工具调用（Started/Completed）要攒成明细，卡片「过程」里可展开看参数与结果。"""
    import asyncio

    from app.plugin.module_ai.agent.service import AiAgentService
    from app.plugin.module_ai.assistant.agno_service import agno_event_frame
    from app.plugin.module_ai.workspace import service as ws

    async def fake_run_ui_stream(cls, agent_id, ui_messages, auth, variables=None, session_id=None):
        yield agno_event_frame(
            "ToolCallStarted",
            {"tool": {"tool_name": "list_datasets", "tool_call_id": "c1", "tool_args": {"limit": 3}}},
        )
        yield agno_event_frame(
            "ToolCallCompleted",
            {"tool": {"tool_name": "list_datasets", "tool_call_id": "c1", "result": {"total": 273}}},
        )
        yield agno_event_frame("RunContent", {"content": "共 273 个数据集。"})

    monkeypatch.setattr(AiAgentService, "run_ui_stream", classmethod(fake_run_ui_stream))
    text, err, tools = asyncio.run(ws.WorkspaceService._run_target("agent", 42))
    assert err is None
    assert text == "共 273 个数据集。"
    assert len(tools) == 1
    assert tools[0]["name"] == "list_datasets"
    assert tools[0]["args"] == {"limit": 3}
    assert tools[0]["result"] == {"total": 273}
    assert tools[0]["ok"] is True


def _insert_cron_row(enabled: bool = True) -> int:
    """直插一条定时任务行（不注册作业），用于验证回写逻辑。"""
    import asyncio
    import uuid

    async def _run() -> int:
        from app.core.database import async_db_session
        from app.plugin.module_ai.workspace.model import AiWorkspaceCronModel

        async with async_db_session.begin() as db:
            row = AiWorkspaceCronModel(
                name=f"pytest-cron-streak-{uuid.uuid4().hex[:6]}",
                trigger="cron",
                trigger_args="0 9 * * mon",
                target_type="workflow",
                target_id=0,
                enabled=enabled,
            )
            db.add(row)
            await db.flush()
            return row.id

    return asyncio.run(_run())


def _row_of(test_client, auth_headers, cid: int) -> dict:
    items = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers).json()["data"][
        "items"
    ]
    return next(x for x in items if x["id"] == cid)


def test_cron_auto_disabled_after_repeated_failures(test_client, auth_headers):
    """连续失败到上限自动停用；重新启用后计数清零。"""
    import asyncio

    from app.plugin.module_ai.workspace import service as ws

    cid = _insert_cron_row()
    try:
        async def _fail(n: int):
            for _ in range(n):
                await ws.WorkspaceService.write_back_cron_state(
                    cid, status="error", duration_ms=10, message="boom", run_id="r1"
                )

        # 1 次失败：只记次数，不停用
        asyncio.run(_fail(1))
        row = _row_of(test_client, auth_headers, cid)
        assert row["fail_streak"] == 1
        assert row["enabled"] is True and row["auto_disabled"] is False

        # 成功一次：计数清零（启用状态下才可能发生）
        asyncio.run(
            ws.WorkspaceService.write_back_cron_state(cid, status="success", message="ok")
        )
        row = _row_of(test_client, auth_headers, cid)
        assert row["fail_streak"] == 0 and row["auto_disabled"] is False

        # 连续失败到上限：自动停用 + 摘掉下次运行时间
        asyncio.run(_fail(ws._CRON_FAIL_STREAK_LIMIT))
        row = _row_of(test_client, auth_headers, cid)
        assert row["fail_streak"] == ws._CRON_FAIL_STREAK_LIMIT
        assert row["enabled"] is False, "连续失败到上限必须自动停用"
        assert row["auto_disabled"] is True
        assert row["next_run_time"] is None, "停用后不该再有下次运行时间"

        # 手动重新启用：计数清零、恢复启用（修好后能继续跑）
        r = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cid}",
            json={"enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        row = _row_of(test_client, auth_headers, cid)
        assert row["enabled"] is True
        assert row["fail_streak"] == 0 and row["auto_disabled"] is False

        # 再失败到上限 → 再次自动停用（闸门没有卡在"已经停过一次"）
        asyncio.run(_fail(ws._CRON_FAIL_STREAK_LIMIT))
        assert _row_of(test_client, auth_headers, cid)["auto_disabled"] is True
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/workspace/cron/delete",
            json=cid,
            headers=auth_headers,
        )


def _steps_of(test_client, auth_headers, run_id: str) -> list[dict]:
    r = test_client.get(
        "/api/v1/ai/agents/office/steps",
        params={"run_id": run_id, "limit": 60},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return sorted(r.json()["data"] or [], key=lambda x: x["seq"])


def test_cron_retries_once_then_succeeds(test_client, auth_headers, monkeypatch):
    """第 1 次失败要自动重试一次；重试成功就记成功，失败计数清零。"""
    import asyncio

    from app.plugin.module_ai.workspace.service import (
        WorkspaceService,
        run_scheduled_workspace_cron,
    )

    cid = _insert_cron_row()
    calls = {"n": 0}

    async def fake_run_target(target_type: str, target_id: int):
        calls["n"] += 1
        if calls["n"] == 1:
            return "", "模型瞬时超时", []
        return "重试后的正文", None, []

    monkeypatch.setattr(WorkspaceService, "_run_target", staticmethod(fake_run_target))
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))
        assert calls["n"] == 2, "必须自动重试一次"

        row = _row_of(test_client, auth_headers, cid)
        assert row["last_status"] == "success"
        assert row["fail_streak"] == 0
        assert "重试后的正文" in (row["last_message"] or "")

        steps = _steps_of(test_client, auth_headers, row["last_run_id"])
        kinds = [x["kind"] for x in steps]
        assert "retry" in kinds, f"时间线里应有重试步骤：{kinds}"
        assert kinds[-1] == "summary", f"最后一次应是完成：{kinds}"
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cid, headers=auth_headers
        )


def test_cron_retry_failure_marks_error(test_client, auth_headers, monkeypatch):
    """重试仍失败：记最终失败（失败计数 +1），时间线里能看到两次失败。"""
    import asyncio

    from app.plugin.module_ai.workspace.service import (
        WorkspaceService,
        run_scheduled_workspace_cron,
    )

    cid = _insert_cron_row()
    calls = {"n": 0}

    async def always_fail(target_type: str, target_id: int):
        calls["n"] += 1
        return "", f"第 {calls['n']} 次就失败", []

    monkeypatch.setattr(WorkspaceService, "_run_target", staticmethod(always_fail))
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))
        assert calls["n"] == 2

        row = _row_of(test_client, auth_headers, cid)
        assert row["last_status"] == "error"
        assert row["fail_streak"] == 1
        assert "重试后仍失败" in (row["last_message"] or "")

        kinds = [x["kind"] for x in _steps_of(test_client, auth_headers, row["last_run_id"])]
        assert kinds.count("error") == 1 and "retry" in kinds
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cid, headers=auth_headers
        )


def test_cron_auto_disable_notifies_admin(test_client, auth_headers, monkeypatch):
    """自动停用要给管理员发通知（email + webhook），描述里带任务名与最近错误。"""
    import asyncio

    import app.utils.notification as notif
    from app.plugin.module_ai.workspace import service as ws

    sent: list[tuple[str, str, str]] = []

    async def fake_load_params(db, *keys):
        return {
            "ai_cron_notify_channels": "email,webhook",
            "notify_admin_email": "admin@example.com",
            "notify_webhook_default_url": "http://127.0.0.1:9/hook",
        }

    async def fake_email(db, alarm, rule, cfg):
        sent.append(("email", alarm["alarm_type"], alarm["description"]))

    async def fake_webhook(db, alarm, rule, cfg):
        sent.append(("webhook", alarm["alarm_type"], alarm["description"]))

    monkeypatch.setattr(notif, "load_params", fake_load_params)
    monkeypatch.setattr(notif, "_send_email", fake_email)
    monkeypatch.setattr(notif, "_send_webhook", fake_webhook)

    cid = _insert_cron_row()
    try:
        async def _fail_n(n: int):
            for _ in range(n):
                await ws.WorkspaceService.write_back_cron_state(
                    cid, status="error", message="模型连续超时"
                )

        asyncio.run(_fail_n(ws._CRON_FAIL_STREAK_LIMIT))
        assert [x[0] for x in sent] == ["email", "webhook"], f"通知没发全：{sent}"
        assert sent[0][1] == "定时任务自动停用"
        assert "模型连续超时" in sent[0][2]
        assert "连续失败" in sent[0][2]
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cid, headers=auth_headers
        )
