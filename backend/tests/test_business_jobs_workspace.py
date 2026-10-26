"""AI 工作台定时任务并入中心调度器（Task B2）。

覆盖：

- 新建 / 修改 / 启停 / 删除定时任务 → 中心调度器作业同步（启用 → 注册，禁用 / 删除 → 移除）；
- `next_run_time` 由**作业回写**（单一真源），工作台侧不再自算；
- 作业入口 `run_scheduled_workspace_cron` 触发时回写 `last_run_time` / `next_run_time`；
- 启动期按模块同步：`collect_job_specs()` 只收「启用且有表达式」的行，同步只清理
  `ai_workspace_cron:` 前缀，绝不误删工作流 / 训练的作业；
- 源码级锁定：工作台的每分钟自建轮询 `cron_scheduler` 已删除，`init_app` 不再有第二条
  注册路径、且逐模块传自己的前缀（不用 `prefixes=None` 的聚合形态）。

需要应用（`test_client`）的用例在 ``PYTEST_NO_APP=1`` 快速模式下自动 skip。
"""

import asyncio
import inspect
import uuid
from zoneinfo import ZoneInfo

from apscheduler.triggers.date import DateTrigger

# `ap_scheduler` 与 `app.plugin.module_task` 存在**既有**循环导入（B1 已记录）：
# 先 import `module_task` 再 import `ap_scheduler` 才能成功。这里固定顺序，
# 使本文件在 `PYTEST_NO_APP=1` 快速模式下也能导入（该循环导入非本任务引入）。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil, scheduler
from app.plugin.module_ai.workspace import service as workspace_service
from app.plugin.module_ai.workspace.service import (
    WorkspaceService,
    _job_key,
    run_scheduled_workspace_cron,
)

#: 别的模块的作业键（验证「只清理自己的前缀」）
_FOREIGN_JOB_KEYS = ("ai_workflow_schedule:9001", "train_schedule:9001")


def _new_name() -> str:
    return f"pytest-ws-b2-{uuid.uuid4().hex[:8]}"


def _create_cron(
    test_client,
    auth_headers,
    cron: str = "0 9 * * mon",
    enabled: bool = True,
    target_type: str = "workflow",
    target_id: int = 0,
) -> int:
    """建一条工作台定时任务（目标用不存在的 workflow#0：作业执行时静默跳过）。"""
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": _new_name(),
            "description": "",
            "cron": cron,
            "target_type": target_type,
            "target_id": target_id,
            "enabled": enabled,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _update_cron(test_client, auth_headers, cron_id: int, payload: dict):
    return test_client.put(
        f"/api/v1/ai/workspace/cron/update/{cron_id}", json=payload, headers=auth_headers
    )


def _create_cron_now(test_client, auth_headers, enabled: bool = True) -> int:
    """建一条 `trigger="now"`（立即执行）的工作台定时任务：按契约**无参数**。

    目标同样用不存在的 workflow#0（作业执行时静默跳过）。
    """
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": _new_name(),
            "description": "",
            "trigger": "now",
            "trigger_args": None,
            "target_type": "workflow",
            "target_id": 0,
            "enabled": enabled,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_cron(test_client, auth_headers, cron_id: int) -> None:
    test_client.request(
        "DELETE", "/api/v1/ai/workspace/cron/delete", json=cron_id, headers=auth_headers
    )


def _list_items(test_client, auth_headers) -> list[dict]:
    r = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["items"]


def _list_row(test_client, auth_headers, cron_id: int) -> dict:
    return next(x for x in _list_items(test_client, auth_headers) if x["id"] == cron_id)


def _fmt(value) -> str:
    """把 datetime / 响应字符串归一成 `%Y-%m-%d %H:%M:%S`（naive 视为 `Asia/Shanghai`）。

    响应里的 datetime 已被公共响应编码器格式化成字符串，而 `job.next_run_time` 是带时区的
    datetime——两边都归一后再比对。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("T", " ")[:19]
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def test_workspace_cron_registers_and_removes_business_job(test_client, auth_headers):
    """启停同步作业：启用 → `ai_workspace_cron:{id}` 出现；禁用 → 作业移除（不留幽灵触发）。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    job_key = _job_key(cid)
    try:
        job = scheduler.get_job(job_key)
        assert job is not None, "启用定时任务后中心调度器应有对应作业"
        # 作业入口是**模块级函数**（可序列化、日志可读），位置参数即任务 id
        assert job.func is run_scheduled_workspace_cron
        assert job.args == (cid,)
        # 业务作业的调度参数由中心调度器统一显式设置（B1）
        assert job.coalesce is True
        assert job.misfire_grace_time == 60
        assert job.max_instances == 1

        r = _update_cron(test_client, auth_headers, cid, {"enabled": False})
        assert r.status_code == 200, r.text
        assert scheduler.get_job(job_key) is None, "禁用定时任务后作业必须移除"
        assert r.json()["data"]["enabled"] is False
        assert r.json()["data"]["next_run_time"] is None
    finally:
        _delete_cron(test_client, auth_headers, cid)
        SchedulerUtil.remove_business_job(job_key)


def test_workspace_cron_next_run_time_is_read_back_from_job(test_client, auth_headers):
    """状态单一真源：行里的 `next_run_time` 必须等于**作业**的下次触发时刻（不再自算）。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * 1-5", enabled=True)
    job_key = _job_key(cid)
    try:
        job = scheduler.get_job(job_key)
        assert job is not None and job.next_run_time is not None

        row = _list_row(test_client, auth_headers, cid)
        assert row["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"  # 写入即规范化
        assert _fmt(row["next_run_time"]) == _fmt(job.next_run_time)
    finally:
        _delete_cron(test_client, auth_headers, cid)
        SchedulerUtil.remove_business_job(job_key)


def test_workspace_cron_update_expression_replaces_job(test_client, auth_headers):
    """改表达式 → 同键替换作业（触发器换成新的），`next_run_time` 随之刷新。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    job_key = _job_key(cid)
    try:
        before = str(scheduler.get_job(job_key).trigger)

        r = _update_cron(test_client, auth_headers, cid, {"cron": "30 10 * * fri"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["trigger_args"] == "30 10 * * fri"

        job = scheduler.get_job(job_key)
        assert job is not None
        assert str(job.trigger) != before, "改表达式后触发器必须换成新的"
        assert _fmt(r.json()["data"]["next_run_time"]) == _fmt(job.next_run_time)
    finally:
        _delete_cron(test_client, auth_headers, cid)
        SchedulerUtil.remove_business_job(job_key)


def test_workspace_cron_delete_removes_business_job(test_client, auth_headers):
    """删除定时任务不留幽灵触发：行与中心调度器作业一并清理。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    job_key = _job_key(cid)
    try:
        assert scheduler.get_job(job_key) is not None

        _delete_cron(test_client, auth_headers, cid)

        assert scheduler.get_job(job_key) is None
        assert all(x["id"] != cid for x in _list_items(test_client, auth_headers))
    finally:
        SchedulerUtil.remove_business_job(job_key)


def test_run_scheduled_workspace_cron_writes_back_state(test_client, auth_headers):
    """作业入口：执行后回写 `last_run_time`，且 `next_run_time` 仍等于作业的值。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    job_key = _job_key(cid)
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))

        row = _list_row(test_client, auth_headers, cid)
        assert row["last_run_time"] is not None, "作业运行后应回写上次运行时间"
        assert _fmt(row["next_run_time"]) == _fmt(scheduler.get_job(job_key).next_run_time)
    finally:
        _delete_cron(test_client, auth_headers, cid)
        SchedulerUtil.remove_business_job(job_key)


def test_run_scheduled_workspace_cron_skips_disabled_row(test_client, auth_headers):
    """作业触发时以库为准：行已禁用 / 未配置表达式 → 直接跳过，不执行也不记上次运行。"""
    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=False)
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))
        row = _list_row(test_client, auth_headers, cid)
        assert row["last_run_time"] is None
        assert row["next_run_time"] is None
    finally:
        _delete_cron(test_client, auth_headers, cid)
        SchedulerUtil.remove_business_job(_job_key(cid))


def test_collect_job_specs_and_startup_sync_only_touch_own_prefix(test_client, auth_headers):
    """启动期同步：只注册启用且有表达式的行；清理范围只限 `ai_workspace_cron:` 前缀。"""
    cid_on = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    cid_off = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=False)

    async def _other_job():
        return None

    for key in _FOREIGN_JOB_KEYS:
        SchedulerUtil.register_business_trigger(key, "interval", {"minutes": 5}, _other_job)
    try:
        # 模拟「服务刚重启」：清掉进程内作业，再看启动同步能否按库里的启用行重建
        SchedulerUtil.remove_business_job(_job_key(cid_on))
        SchedulerUtil.remove_business_job(_job_key(cid_off))

        specs = asyncio.run(WorkspaceService.collect_job_specs())
        keys = {spec[0] for spec in specs}
        assert _job_key(cid_on) in keys
        assert _job_key(cid_off) not in keys  # 未启用不注册
        assert all(key.startswith("ai_workspace_cron:") for key in keys)

        SchedulerUtil.sync_business_jobs(specs, prefixes=("ai_workspace_cron:",))
        assert scheduler.get_job(_job_key(cid_on)) is not None
        assert scheduler.get_job(_job_key(cid_off)) is None
        # 前缀自律：别的模块的作业绝不被清理
        for key in _FOREIGN_JOB_KEYS:
            assert scheduler.get_job(key) is not None

        # 启动期回写：行里的 next_run_time 刷新为作业算出的值
        asyncio.run(WorkspaceService.write_back_cron_states())
        row = _list_row(test_client, auth_headers, cid_on)
        assert _fmt(row["next_run_time"]) == _fmt(scheduler.get_job(_job_key(cid_on)).next_run_time)
    finally:
        for key in (*_FOREIGN_JOB_KEYS, _job_key(cid_on), _job_key(cid_off)):
            SchedulerUtil.remove_business_job(key)
        _delete_cron(test_client, auth_headers, cid_on)
        _delete_cron(test_client, auth_headers, cid_off)


def test_startup_registration_helper_registers_workspace_jobs(test_client, auth_headers):
    """`init_app` 的启动期注册：按库里的启用行重建工作台作业，且只清理自己的前缀残留。"""
    from app.scripts.init_app import _register_business_jobs_on_startup

    cid = _create_cron(test_client, auth_headers, cron="0 9 * * mon", enabled=True)
    job_key = _job_key(cid)
    leftover_key = "ai_workspace_cron:9002"  # 库里已删除/禁用、进程内残留的作业
    system_key = "987658"  # 系统定时任务（id 为纯数字）：绝不能被业务同步清理

    async def _other_job():
        return None

    SchedulerUtil.register_business_trigger(leftover_key, "interval", {"minutes": 7}, _other_job)
    scheduler.add_job(_other_job, "interval", minutes=30, id=system_key, coalesce=True)
    try:
        # 模拟「服务刚重启」：清掉进程内的工作台作业，再看启动注册能否按库重建
        SchedulerUtil.remove_business_job(job_key)

        asyncio.run(_register_business_jobs_on_startup())

        assert scheduler.get_job(job_key) is not None, "启动期必须按库里的启用行重建作业"
        assert scheduler.get_job(leftover_key) is None, "同前缀的残留作业应被清理"
        assert scheduler.get_job(system_key) is not None, "系统定时任务不受业务同步影响"
        # 启动期只回写 next_run_time，不得把启动时刻误记成「上次运行」
        row = _list_row(test_client, auth_headers, cid)
        assert row["last_run_time"] is None
        assert _fmt(row["next_run_time"]) == _fmt(scheduler.get_job(job_key).next_run_time)
    finally:
        for key in (leftover_key, system_key, job_key):
            SchedulerUtil.remove_business_job(key)
        try:
            scheduler.remove_job(system_key)
        except Exception:  # noqa: BLE001 作业已不在
            pass
        _delete_cron(test_client, auth_headers, cid)


def test_workspace_cron_now_trigger_registers_one_shot_job(test_client, auth_headers):
    """`trigger="now"`（立即执行）必须真的注册一次性作业（Task A9）。

    缺口：守卫曾写成 `not enabled or not trigger_args`，而 `now` 按契约**无参数**
    （`trigger_args` 恒为 `None`）⇒ 作业永远注册不上，「保存后立即执行一次」静默失效。
    口径与工作流侧逐字一致：`enabled and (trigger_args or trigger == "now")`。

    刻意**不触发**作业去真跑（只断言注册结果与触发器类型）。
    """
    cid = _create_cron_now(test_client, auth_headers, enabled=True)
    cid_off = _create_cron_now(test_client, auth_headers, enabled=False)
    job_key = _job_key(cid)
    off_key = _job_key(cid_off)
    try:
        job = scheduler.get_job(job_key)
        assert job is not None, "「立即执行」必须注册一次性作业（now 按契约无参数）"
        assert job.func is run_scheduled_workspace_cron  # 模块级执行体（可日志/可序列化）
        assert job.args == (cid,)
        # 触发器由统一层构造：`now` → `DateTrigger(now + 2s)`
        assert isinstance(job.trigger, DateTrigger)
        assert scheduler.get_job(off_key) is None, "未启用不得注册作业"

        r = _update_cron(test_client, auth_headers, cid, {"enabled": False})
        assert r.status_code == 200, r.text
        assert scheduler.get_job(job_key) is None, "禁用后一次性作业必须移除（不留幽灵触发）"
    finally:
        for key in (job_key, off_key):
            SchedulerUtil.remove_business_job(key)
        _delete_cron(test_client, auth_headers, cid)
        _delete_cron(test_client, auth_headers, cid_off)


def test_workspace_module_has_no_self_polling_and_init_app_registers_per_module():
    """源码级锁定：自建每分钟轮询已删除；`init_app` 逐模块同步、绝不用聚合形态注册。"""
    source = inspect.getsource(workspace_service)
    assert hasattr(WorkspaceService, "cron_scheduler") is False
    assert "cron_scheduler" not in source
    assert "while True" not in source
    assert "asyncio.sleep" not in source
    # `next_run_time` 从**作业**读回（单一真源）：工作台不再自算。统一层 `TriggerUtil.next_run`
    # 只保留「调度器未运行」时的预览兜底（`_preview_next_run`，A5 的源码锁仍要求它存在）。
    assert "scheduler.get_job(" in source
    assert "_preview_next_run" in source

    from app.scripts import init_app

    init_source = inspect.getsource(init_app)
    assert "cron_scheduler" not in init_source, "自建轮询的启动项必须已收口"
    assert "await _register_business_jobs_on_startup()" in init_source
    # 逐模块同步：每个模块只传自己的前缀；`prefixes=None` 的聚合同步会误删别模块的作业
    for prefix in ("ai_workspace_cron:", "ai_workflow_schedule:", "train_schedule:"):
        assert prefix in init_source
    sync_calls = [
        line.strip() for line in init_source.splitlines() if "sync_business_jobs(" in line
    ]
    assert sync_calls, "启动期必须显式调用逐模块同步"
    assert all("prefixes=" in line and "prefixes=None" not in line for line in sync_calls), (
        sync_calls
    )


# ============================================================ Task A11：`now` 语义闭环


def _create_cron_typed(test_client, auth_headers, trigger: str, trigger_args) -> int:
    """按统一契约建一条指定触发类型的启用中定时任务（目标用不存在的 workflow#0）。"""
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": _new_name(),
            "description": "",
            "trigger": trigger,
            "trigger_args": trigger_args,
            # 兼容字段：仅 cron 类型带表达式，其余类型带空串（前端 C4 之后的行为）
            "cron": trigger_args if trigger == "cron" else "",
            "target_type": "workflow",
            "target_id": 0,
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_run_scheduled_workspace_cron_executes_now_row(monkeypatch, test_client, auth_headers):
    """A11 ①：`trigger="now"`（按契约无参数）的行被触发时必须真的执行绑定的资产。

    缺口：执行体守卫写成 `not row.enabled or not row.trigger_args`，而 `now` 的
    `trigger_args` 恒为 `None` ⇒ A9 把作业注册上了、**触发时又被拦下**，作业空转。
    """
    cid = _create_cron_now(test_client, auth_headers, enabled=True)
    job_key = _job_key(cid)
    # 立刻移除刚注册的一次性作业（本用例直接调执行体，且断言副作用已被打桩）
    SchedulerUtil.remove_business_job(job_key)

    calls: list[tuple] = []

    async def _fake_run_target(target_type: str, target_id: int):
        calls.append((target_type, target_id))
        return "", None, []   # 契约：返回 (正文摘要, 错误信息, 工具调用明细)

    monkeypatch.setattr(WorkspaceService, "_run_target", staticmethod(_fake_run_target))
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))
        assert calls == [("workflow", 0)], "now 行必须真的执行绑定的资产"
        row = _list_row(test_client, auth_headers, cid)
        assert row["last_run_time"] is not None, "真正执行过的这一轮才回写上次运行时间"
    finally:
        SchedulerUtil.remove_business_job(job_key)
        _delete_cron(test_client, auth_headers, cid)


def _insert_cron_row(trigger: str, trigger_args, enabled: bool = True) -> int:
    """直接落一条指定触发类型的工作台定时任务行（绕过写入口校验，构造空表达式等场景）。

    直插**不注册作业**，因此不会在测试里被一次性作业意外触发。
    """

    async def _run() -> int:
        from app.core.database import async_db_session
        from app.plugin.module_ai.workspace.model import AiWorkspaceCronModel

        async with async_db_session.begin() as db:
            row = AiWorkspaceCronModel(
                name=f"pytest-A11-直插-{uuid.uuid4().hex[:6]}",
                trigger=trigger,
                trigger_args=trigger_args,
                target_type="workflow",
                target_id=0,
                enabled=enabled,
            )
            db.add(row)
            await db.flush()
            return row.id

    return asyncio.run(_run())


def test_run_scheduled_workspace_cron_still_skips_row_without_trigger(
    monkeypatch, test_client, auth_headers
):
    """A11 ④回归：非 `now` 且无表达式的行仍被拦（不得因放行 `now` 而放行静默失效）。"""
    cid = _insert_cron_row("cron", None, enabled=True)
    calls: list[tuple] = []

    async def _fake_run_target(target_type: str, target_id: int):
        calls.append((target_type, target_id))
        return "", None, []   # 契约：返回 (正文摘要, 错误信息, 工具调用明细)

    monkeypatch.setattr(WorkspaceService, "_run_target", staticmethod(_fake_run_target))
    try:
        asyncio.run(run_scheduled_workspace_cron(cid))
        assert calls == [], "空表达式的行必须被拦下"
        row = _list_row(test_client, auth_headers, cid)
        assert row["last_run_time"] is None, "被跳过的行不记「刚跑过」"
    finally:
        _delete_cron(test_client, auth_headers, cid)


def test_workspace_collect_job_specs_excludes_now_rows(test_client, auth_headers):
    """A11 ②：启动期不重建 `now` 行（`DateTrigger` 注册时算 `now + 2s` ⇒ 每次重启都重跑一次）。

    口径：只收「启用且有触发表达式且非 `now`」的行；cron / interval / date 三类照收（回归）。
    """
    cid_now = _create_cron_now(test_client, auth_headers, enabled=True)
    cid_cron = _create_cron_typed(test_client, auth_headers, "cron", "0 9 * * mon")
    cid_interval = _create_cron_typed(test_client, auth_headers, "interval", {"minutes": 30})
    cid_date = _create_cron_typed(test_client, auth_headers, "date", "2999-01-01 09:00:00")
    keys_all = [_job_key(x) for x in (cid_now, cid_cron, cid_interval, cid_date)]
    try:
        # 模拟「服务刚重启」：清掉进程内作业，再看启动同步能否按库里的启用行重建
        for key in keys_all:
            SchedulerUtil.remove_business_job(key)

        specs = asyncio.run(WorkspaceService.collect_job_specs())
        keys = {spec[0] for spec in specs}
        assert _job_key(cid_now) not in keys, "启动期不得重建 now 行（否则每次重启都重跑一次）"
        for other in (cid_cron, cid_interval, cid_date):
            assert _job_key(other) in keys, "cron / interval / date 行必须照常重建"
    finally:
        for key in keys_all:
            SchedulerUtil.remove_business_job(key)
        for cron_id in (cid_now, cid_cron, cid_interval, cid_date):
            _delete_cron(test_client, auth_headers, cron_id)
