"""中心调度器「业务作业」API：注册 / 移除 / 同步（Task B1）。

覆盖 Review Focus 4：删除或禁用任务后作业不得残留（无幽灵触发），
且 `sync_business_jobs` 只清理业务前缀的作业，绝不触碰 `NodeModel` 的系统定时任务。

可 ``PYTEST_NO_APP=1`` 快速跑（纯逻辑，约 2 秒）；默认模式（调度器已启动）同样通过。
"""

import asyncio

from apscheduler.jobstores.base import JobLookupError

# `ap_scheduler` 与 `app.plugin.module_task`（其 job controller 反向 import 调度器）存在**既有**
# 循环导入：先 import `ap_scheduler` 会失败，先 import `module_task` 则成功。这里固定顺序，
# 使本文件的用例在 `PYTEST_NO_APP=1` 快速模式下也能运行（该循环导入非本任务引入）。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil, scheduler


def test_register_and_remove_business_job_is_idempotent():
    """注册可幂等替换；移除后不留幽灵作业，重复移除返回 False 而不抛。"""

    async def _run():
        calls = []

        async def _job():
            calls.append(1)

        SchedulerUtil.register_business_trigger("t:1", "interval", {"minutes": 5}, _job)
        assert scheduler.get_job("t:1") is not None
        SchedulerUtil.register_business_trigger(
            "t:1", "interval", {"minutes": 10}, _job
        )  # 幂等替换
        assert len(scheduler.get_jobs()) >= 1
        assert SchedulerUtil.remove_business_job("t:1") is True
        assert scheduler.get_job("t:1") is None  # 不留幽灵作业
        assert SchedulerUtil.remove_business_job("t:1") is False  # 再删不报错

    asyncio.run(_run())


def test_business_job_defaults_are_explicit():
    """业务作业必须显式带 coalesce/misfire/max_instances（APScheduler 默认 1 秒 misfire 会丢跑）。"""

    async def _job():
        return None

    SchedulerUtil.register_business_trigger("t:defaults", "interval", {"minutes": 5}, _job)
    try:
        job = scheduler.get_job("t:defaults")
        assert job is not None
        assert job.coalesce is True
        assert job.misfire_grace_time == 60
        assert job.max_instances == 1
    finally:
        SchedulerUtil.remove_business_job("t:defaults")


def test_sync_business_jobs_registers_listed_and_prunes_only_business_jobs():
    """同步按规格列表注册；清理列表外的业务作业残留；系统作业（纯数字 id）不受影响。"""

    async def _job():
        return None

    async def _job_with_arg(schedule_id):
        return schedule_id

    # 模拟 `NodeModel` 系统定时任务（id 为纯数字）：同步时绝不能被清理
    scheduler.add_job(_job, "interval", minutes=30, id="987654", coalesce=True)
    # 模拟「库里已删除/禁用」的业务作业残留
    SchedulerUtil.register_business_trigger(
        "ai_workflow_schedule:404", "interval", {"minutes": 7}, _job
    )
    specs = [
        ("ai_workspace_cron:12", "interval", {"minutes": 5}, _job),
        ("train_schedule:5", "cron", "0 9 * * mon", _job_with_arg, (5,)),
    ]
    try:
        assert SchedulerUtil.sync_business_jobs(specs) == {"registered": 2, "removed": 1}
        assert scheduler.get_job("ai_workspace_cron:12") is not None
        assert scheduler.get_job("train_schedule:5") is not None
        assert scheduler.get_job("ai_workflow_schedule:404") is None  # 残留被清理
        assert scheduler.get_job("987654") is not None  # 系统作业不受影响

        # 幂等：再同步一次不重复注册（registered 为「本轮注册数」，含幂等替换）、无可清理项
        assert SchedulerUtil.sync_business_jobs(specs) == {"registered": 2, "removed": 0}
    finally:
        for job_key in ("ai_workspace_cron:12", "train_schedule:5", "ai_workflow_schedule:404"):
            SchedulerUtil.remove_business_job(job_key)
        try:
            scheduler.remove_job("987654")
        except JobLookupError:
            pass
