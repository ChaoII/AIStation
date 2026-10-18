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
