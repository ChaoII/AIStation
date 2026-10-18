"""AI 工作流定时调度并入中心调度器（Task B3）。

覆盖：

- 启停/增改调度行 → 中心调度器作业同步（启用 → 注册，禁用/清空 → 移除，幂等）；
- `next_run_time` 由**作业回写**（单一真源），业务侧不再自算；
- 启动期一次性同步（不再自建每分钟轮询）；
- 单行同步只动自己的作业：别的模块（工作台）与别的工作流的作业不受影响；
- 删除工作流不留「幽灵作业」（调度行 + 中心调度器作业一并清理）。

需要应用（`test_client`）的用例在 ``PYTEST_NO_APP=1`` 快速模式下自动 skip。
"""

import asyncio
import inspect
import uuid
from zoneinfo import ZoneInfo

# `ap_scheduler` 与 `app.plugin.module_task` 存在**既有**循环导入（B1 已记录）：
# 先 import `module_task` 再 import `ap_scheduler` 才能成功。这里固定顺序，
# 使本文件在 `PYTEST_NO_APP=1` 快速模式下也能导入（该循环导入非本任务引入）。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil, scheduler
from app.plugin.module_ai.workflow import service as workflow_service
from app.plugin.module_ai.workflow.service import (
    AiWorkflowService,
    _job_key,
    run_scheduled_workflow,
)

#: 远端模块的作业键（用于验证「只清理自己的前缀」）
_WORKSPACE_JOB_KEY = "ai_workspace_cron:9001"


def _new_name() -> str:
    return f"pytest-wf-b3-{uuid.uuid4().hex[:8]}"


def _create_workflow(test_client, auth_headers) -> int:
    """建一个最小可运行的工作流（start → end）。"""
    r = test_client.post(
        "/api/v1/ai/workflows/create",
        json={
            "name": _new_name(),
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {"id": "end", "type": "end", "data": {"output_template": "ok"}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "end"}],
            },
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_workflows(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=list(ids), headers=auth_headers
        )


def _put_schedule(test_client, auth_headers, workflow_id: int, cron: str, enabled: bool):
    return test_client.put(
        f"/api/v1/ai/workflows/{workflow_id}/schedule",
        json={"cron": cron, "enabled": enabled},
        headers=auth_headers,
    )


def _get_schedule(test_client, auth_headers, workflow_id: int) -> dict:
    r = test_client.get(f"/api/v1/ai/workflows/{workflow_id}/schedule", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fmt(value) -> str:
    """把 datetime / 响应字符串归一成 `%Y-%m-%d %H:%M:%S`（naive 视为 `Asia/Shanghai`）。

    响应里的 datetime 已被公共响应编码器格式化成字符串（`%Y-%m-%d %H:%M:%S`），
    而 `job.next_run_time` 是带时区的 datetime——两边都归一后再比对。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("T", " ")[:19]
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def test_workflow_schedule_registers_and_removes_business_job(test_client, auth_headers):
    """启停同步作业：启用 → `ai_workflow_schedule:{id}` 出现；禁用 → 作业移除（不留幽灵作业）。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        r = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon-fri", True)
        assert r.status_code == 200, r.text
        job = scheduler.get_job(job_key)
        assert job is not None, "启用调度后中心调度器应有对应作业"
        # 作业入口是**模块级函数**（可序列化、日志可读），位置参数即工作流 id
        assert job.func is run_scheduled_workflow
        assert job.args == (wid,)
        # 业务作业的调度参数由中心调度器统一显式设置（B1）
        assert job.coalesce is True
        assert job.misfire_grace_time == 60
        assert job.max_instances == 1

        r2 = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon-fri", False)
        assert r2.status_code == 200, r2.text
        assert scheduler.get_job(job_key) is None, "禁用调度后作业必须移除"
        d = _get_schedule(test_client, auth_headers, wid)
        assert d["enabled"] is False
        assert d["next_run_time"] is None
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_workflow_schedule_next_run_time_is_read_back_from_job(test_client, auth_headers):
    """状态单一真源：调度行的 `next_run_time` 必须等于**作业**的下次触发时刻（不再自算）。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        r = _put_schedule(test_client, auth_headers, wid, "0 9 * * 1-5", True)
        assert r.status_code == 200, r.text
        job = scheduler.get_job(job_key)
        assert job is not None and job.next_run_time is not None

        saved = r.json()["data"]
        assert saved["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"  # 写入即规范化
        assert _fmt(saved["next_run_time"]) == _fmt(job.next_run_time)

        d = _get_schedule(test_client, auth_headers, wid)
        assert _fmt(d["next_run_time"]) == _fmt(job.next_run_time)
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_run_scheduled_workflow_runs_and_writes_back_state(test_client, auth_headers):
    """作业入口：运行工作流（落运行历史）并把 `last_run_time`/`next_run_time` 回写调度行。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        r = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon-fri", True)
        assert r.status_code == 200, r.text
        job = scheduler.get_job(job_key)
        assert job is not None

        asyncio.run(run_scheduled_workflow(wid))

        d = _get_schedule(test_client, auth_headers, wid)
        assert d["last_run_time"] is not None, "作业运行后应回写上次运行时间"
        assert _fmt(d["next_run_time"]) == _fmt(scheduler.get_job(job_key).next_run_time)

        r = test_client.get(f"/api/v1/ai/workflows/{wid}/run-logs", headers=auth_headers)
        logs = r.json()["data"]
        assert logs and logs[0]["status"] == "success"
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_start_scheduler_registers_enabled_rows_once_without_polling(test_client, auth_headers):
    """启动期一次性同步：只注册启用行；且源码里不再有自建轮询与自算 `next_run`。"""
    wf_on = _create_workflow(test_client, auth_headers)
    wf_off = _create_workflow(test_client, auth_headers)
    try:
        r_on = _put_schedule(test_client, auth_headers, wf_on, "0 9 * * mon", True)
        assert r_on.status_code == 200, r_on.text
        r_off = _put_schedule(test_client, auth_headers, wf_off, "0 9 * * mon", False)
        assert r_off.status_code == 200, r_off.text
        # 模拟「服务刚重启」：清掉进程内作业，再看启动同步能否按库里的启用行重建
        SchedulerUtil.remove_business_job(_job_key(wf_on))
        SchedulerUtil.remove_business_job(_job_key(wf_off))

        asyncio.run(AiWorkflowService.start_scheduler())

        assert scheduler.get_job(_job_key(wf_on)) is not None
        assert scheduler.get_job(_job_key(wf_off)) is None

        # 源码级锁定：启动钩子不再轮询、业务侧不再自算下次运行时间
        source = inspect.getsource(AiWorkflowService.start_scheduler)
        assert "while True" not in source
        module_source = inspect.getsource(workflow_service)
        assert "TriggerUtil.next_run" not in module_source
    finally:
        _delete_workflows(test_client, auth_headers, [wf_on, wf_off])
        for key in (_job_key(wf_on), _job_key(wf_off)):
            SchedulerUtil.remove_business_job(key)


def test_set_schedule_keeps_other_business_jobs(test_client, auth_headers):
    """单行同步只动自己的作业：别的模块与别的工作流的作业绝不被清理（前缀自律）。"""
    wf_a = _create_workflow(test_client, auth_headers)
    wf_b = _create_workflow(test_client, auth_headers)

    async def _other_job():
        return None

    try:
        r_a = _put_schedule(test_client, auth_headers, wf_a, "0 9 * * mon", True)
        assert r_a.status_code == 200, r_a.text
        r_b = _put_schedule(test_client, auth_headers, wf_b, "0 10 * * mon", True)
        assert r_b.status_code == 200, r_b.text
        # 别的模块（工作台）的作业：同步范围只限 `ai_workflow_schedule:`，不得误删
        SchedulerUtil.register_business_trigger(
            _WORKSPACE_JOB_KEY, "interval", {"minutes": 5}, _other_job
        )

        # 再次修改 wf_a 的调度（幂等替换）
        r_a2 = _put_schedule(test_client, auth_headers, wf_a, "0 11 * * mon", True)
        assert r_a2.status_code == 200, r_a2.text

        assert scheduler.get_job(_job_key(wf_a)) is not None
        assert scheduler.get_job(_job_key(wf_b)) is not None
        assert scheduler.get_job(_WORKSPACE_JOB_KEY) is not None
    finally:
        _delete_workflows(test_client, auth_headers, [wf_a, wf_b])
        for key in (_job_key(wf_a), _job_key(wf_b), _WORKSPACE_JOB_KEY):
            SchedulerUtil.remove_business_job(key)


def test_workflow_delete_removes_business_job_and_schedule_row(test_client, auth_headers):
    """删除工作流不留幽灵作业：调度行与中心调度器作业一并清理。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        assert _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", True).status_code == 200
        assert scheduler.get_job(job_key) is not None

        _delete_workflows(test_client, auth_headers, [wid])

        assert scheduler.get_job(job_key) is None
        # 调度行已删：读取回落到「未配置」默认值
        d = _get_schedule(test_client, auth_headers, wid)
        assert d["enabled"] is False
        assert d["trigger_args"] == ""
        assert d["next_run_time"] is None
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


# ============================================================ 审查收口（Minor 1/2 + 行为测试缺口）


def test_invalid_cron_is_rejected_and_registers_no_job(test_client, auth_headers):
    """非法表达式：400（原因来自统一层）**且不注册作业**、不落库。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        before = _get_schedule(test_client, auth_headers, wid)

        r = _put_schedule(test_client, auth_headers, wid, "0 9 * * 5-1", True)
        assert r.status_code == 400, r.text
        assert "跨周" in r.json()["msg"]
        assert scheduler.get_job(job_key) is None, "非法表达式不得注册作业"
        assert _get_schedule(test_client, auth_headers, wid) == before, "非法表达式不得落库"
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_enable_with_empty_cron_is_rejected_and_not_persisted(test_client, auth_headers):
    """「启用 + 空表达式」：400（不留「已启用但永不触发」）且不落库、不注册作业。"""
    from app.plugin.module_ai.workflow.service import _EMPTY_TRIGGER_MSG

    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        before = _get_schedule(test_client, auth_headers, wid)

        r = _put_schedule(test_client, auth_headers, wid, "", True)
        assert r.status_code == 400, r.text
        assert r.json()["msg"] == _EMPTY_TRIGGER_MSG
        assert scheduler.get_job(job_key) is None
        after = _get_schedule(test_client, auth_headers, wid)
        assert after == before
        assert after["enabled"] is False
        assert after["trigger_args"] == ""
        assert after["next_run_time"] is None
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_resaving_schedule_replaces_trigger_under_same_key(test_client, auth_headers):
    """改表达式 = 同键替换作业（触发器真的换了，不是留着旧触发器）。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        r1 = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", True)
        assert r1.status_code == 200, r1.text
        job_before = scheduler.get_job(job_key)
        assert job_before is not None

        r2 = _put_schedule(test_client, auth_headers, wid, "0 23 * * mon", True)
        assert r2.status_code == 200, r2.text
        job_after = scheduler.get_job(job_key)
        assert job_after is not None and job_after is not job_before
        # 触发器确实换成了新表达式：字符串描述变化 + 下次触发时刻跟着变（23 点而非 9 点）
        assert str(job_after.trigger) != str(job_before.trigger)
        assert _fmt(job_after.next_run_time) != _fmt(job_before.next_run_time)
        assert _fmt(job_after.next_run_time).endswith("23:00:00")
        assert _fmt(r2.json()["data"]["next_run_time"]) == _fmt(job_after.next_run_time)
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_stale_trigger_is_skipped_when_schedule_disabled(test_client, auth_headers):
    """Minor 2：作业入口重读调度行——禁用后即使作业被直接调用（窗口期）也不运行工作流。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        assert _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", True).status_code == 200
        logs_before = test_client.get(
            f"/api/v1/ai/workflows/{wid}/run-logs", headers=auth_headers
        ).json()["data"]

        r_off = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", False)
        assert r_off.status_code == 200, r_off.text
        assert scheduler.get_job(job_key) is None

        # 模拟「禁用请求刚提交、作业已在执行队列里」的最后一次触发
        asyncio.run(run_scheduled_workflow(wid))

        logs_after = test_client.get(
            f"/api/v1/ai/workflows/{wid}/run-logs", headers=auth_headers
        ).json()["data"]
        assert len(logs_after) == len(logs_before), "已停用的调度不得再运行工作流"
        assert _get_schedule(test_client, auth_headers, wid)["last_run_time"] is None
    finally:
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


def test_register_failure_reports_readable_error_and_clears_ghost_job(
    monkeypatch, test_client, auth_headers
):
    """Minor 1：注册作业失败必须兜底——可读 400（不是 500）、清掉残留作业（无幽灵作业）。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        assert _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", True).status_code == 200
        assert scheduler.get_job(job_key) is not None  # 先有一个真实作业，验证失败时被清理

        def _boom(*args, **kwargs):
            raise RuntimeError("调度器不可用")

        monkeypatch.setattr(SchedulerUtil, "register_business_trigger", staticmethod(_boom))
        r = _put_schedule(test_client, auth_headers, wid, "0 9 * * mon", True)

        assert r.status_code == 400, r.text  # 可读错误，而不是未处理的 500
        assert "调度" in r.json()["msg"]
        assert scheduler.get_job(job_key) is None, "注册失败后不得留下残留作业"
    finally:
        monkeypatch.undo()
        _delete_workflows(test_client, auth_headers, [wid])
        SchedulerUtil.remove_business_job(job_key)


# ============================================================ Task A11：`now` 语义闭环


def _put_schedule_trigger(
    test_client, auth_headers, workflow_id: int, trigger: str, trigger_args, enabled: bool = True
):
    """按统一契约保存调度配置（`trigger` + `trigger_args`，兼容字段按类型给值）。"""
    return test_client.put(
        f"/api/v1/ai/workflows/{workflow_id}/schedule",
        json={
            "trigger": trigger,
            "trigger_args": trigger_args,
            "cron": trigger_args if trigger == "cron" else "",
            "enabled": enabled,
        },
        headers=auth_headers,
    )


def _insert_schedule_row(
    workflow_id: int, trigger: str, trigger_args, enabled: bool = True
) -> None:
    """直接落一条调度行（绕过写入口校验，构造「已启用但无表达式」的遗留坏行）。

    直插**不注册作业**，因此不会在测试里被一次性作业意外触发。
    """

    async def _run() -> None:
        from app.core.database import async_db_session
        from app.plugin.module_ai.workflow.model import AiWorkflowScheduleModel

        async with async_db_session.begin() as db:
            db.add(
                AiWorkflowScheduleModel(
                    workflow_id=workflow_id,
                    trigger=trigger,
                    trigger_args=trigger_args,
                    enabled=enabled,
                )
            )

    asyncio.run(_run())


def test_run_scheduled_workflow_executes_now_row(monkeypatch, test_client, auth_headers):
    """A11 ①：`trigger="now"`（按契约无参数）的调度行被触发时必须真的运行工作流。

    缺口：执行体守卫写成 `not row.enabled or not row.trigger_args`，而 `now` 的
    `trigger_args` 恒为 `None` ⇒ A9 把作业注册上了、**触发时又被拦下**，作业空转。
    """
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        r = _put_schedule_trigger(test_client, auth_headers, wid, "now", None, True)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["trigger"] == "now", r.text
        # 立刻移除刚注册的一次性作业（本用例直接调执行体，且断言副作用已被打桩）
        SchedulerUtil.remove_business_job(job_key)

        calls: list[int] = []

        async def _fake_run_schedule(workflow_id: int) -> None:
            calls.append(workflow_id)

        monkeypatch.setattr(AiWorkflowService, "run_schedule", _fake_run_schedule)
        asyncio.run(run_scheduled_workflow(wid))
        assert calls == [wid], "now 行必须真的运行工作流"
        assert _get_schedule(test_client, auth_headers, wid)["last_run_time"] is not None
    finally:
        SchedulerUtil.remove_business_job(job_key)
        _delete_workflows(test_client, auth_headers, [wid])


def test_run_scheduled_workflow_still_skips_row_without_trigger(
    monkeypatch, test_client, auth_headers
):
    """A11 ④回归：非 `now` 且无表达式的遗留坏行仍被拦（不得因放行 `now` 而放行静默失效）。"""
    wid = _create_workflow(test_client, auth_headers)
    job_key = _job_key(wid)
    try:
        _insert_schedule_row(wid, "cron", None, enabled=True)

        calls: list[int] = []

        async def _fake_run_schedule(workflow_id: int) -> None:
            calls.append(workflow_id)

        monkeypatch.setattr(AiWorkflowService, "run_schedule", _fake_run_schedule)
        asyncio.run(run_scheduled_workflow(wid))
        assert calls == [], "空表达式的行必须被拦下"
        assert _get_schedule(test_client, auth_headers, wid)["last_run_time"] is None
    finally:
        SchedulerUtil.remove_business_job(job_key)
        _delete_workflows(test_client, auth_headers, [wid])


def test_workflow_collect_job_specs_excludes_now_rows(test_client, auth_headers):
    """A11 ②：启动期不重建 `now` 行（`DateTrigger` 注册时算 `now + 2s` ⇒ 每次重启都重跑一次）。

    口径：只收「启用且有触发表达式且非 `now`」的行；cron / interval / date 三类照收（回归）。
    """
    wf_now = _create_workflow(test_client, auth_headers)
    wf_cron = _create_workflow(test_client, auth_headers)
    wf_interval = _create_workflow(test_client, auth_headers)
    wf_date = _create_workflow(test_client, auth_headers)
    cases = (
        (wf_now, "now", None),
        (wf_cron, "cron", "0 9 * * mon"),
        (wf_interval, "interval", {"minutes": 30}),
        (wf_date, "date", "2999-01-01 09:00:00"),
    )
    try:
        for wid, trigger, args in cases:
            assert (
                _put_schedule_trigger(
                    test_client, auth_headers, wid, trigger, args, True
                ).status_code
                == 200
            )
        # 模拟「服务刚重启」：清掉进程内作业，再看启动同步能否按库里的启用行重建
        for wid, _trigger, _args in cases:
            SchedulerUtil.remove_business_job(_job_key(wid))

        specs = asyncio.run(AiWorkflowService.collect_job_specs())
        keys = {spec[0] for spec in specs}
        assert _job_key(wf_now) not in keys, "启动期不得重建 now 行（否则每次重启都重跑一次）"
        for wid, _trigger, _args in cases[1:]:
            assert _job_key(wid) in keys, "cron / interval / date 行必须照常重建"

        # 启动同步本身也不得把 now 行重新注册进调度器（端到端行为，不只是规格函数）
        asyncio.run(AiWorkflowService.start_scheduler())
        assert scheduler.get_job(_job_key(wf_now)) is None
        for wid, _trigger, _args in cases[1:]:
            assert scheduler.get_job(_job_key(wid)) is not None
    finally:
        for wid, _trigger, _args in cases:
            SchedulerUtil.remove_business_job(_job_key(wid))
        _delete_workflows(test_client, auth_headers, [w for w, _t, _a in cases])
