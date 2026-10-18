"""中心调度器「业务作业」API：注册 / 移除 / 同步（Task B1）。

覆盖 Review Focus 4：删除或禁用任务后作业不得残留（无幽灵触发）；`sync_business_jobs` 的
清理范围由 `prefixes` 限定（多调用方只管自己的命名空间，绝不跨模块误删），且绝不触碰
`NodeModel` 的系统定时任务（其 id 为纯数字）。

可 ``PYTEST_NO_APP=1`` 快速跑（纯逻辑，约 2 秒）；默认模式（调度器已启动）同样通过。
"""

import asyncio

from apscheduler.jobstores.base import JobLookupError

# `ap_scheduler` 与 `app.plugin.module_task`（其 job controller 反向 import 调度器）存在**既有**
# 循环导入：先 import `ap_scheduler` 会失败，先 import `module_task` 则成功。这里固定顺序，
# 使本文件的用例在 `PYTEST_NO_APP=1` 快速模式下也能运行（该循环导入非本任务引入）。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil, scheduler


def _job_ids() -> set[str]:
    """当前调度器里的全部作业 id（基线差集断言用，避免依赖进程内全局计数）。"""
    return {str(job.id) for job in scheduler.get_jobs()}


def _record_removals(monkeypatch) -> list[str]:
    """把 `remove_business_job` 打桩成「只记录、不真删」，返回被调用的 job_key 列表。

    共享会话的调度器上可能已有其它用例/启动期（B2/B3/B4 落地后）注册的真实业务作业，
    断言「清理范围」时不应把它们真删掉；需要真删的路径由「按规格同步」用例单独覆盖。
    """
    calls: list[str] = []

    def _record(cls, job_key):
        calls.append(job_key)
        return True

    monkeypatch.setattr(SchedulerUtil, "remove_business_job", classmethod(_record))
    return calls


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
    """同步按规格列表注册；清理列表外的业务作业残留；系统作业（纯数字 id）不受影响。

    断言一律按**具体 key / 基线差集**，不依赖进程内全局计数：启动期可能已注册真实业务作业
    （B2/B3/B4 落地后），全局计数会假失败并误伤后续用例。
    """

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
    before = _job_ids()
    try:
        result = SchedulerUtil.sync_business_jobs(specs)
        after = _job_ids()
        removed_keys = before - after

        assert {"ai_workspace_cron:12", "train_schedule:5"} <= after  # 列表内已注册
        assert "ai_workflow_schedule:404" in removed_keys  # 残留被清理
        assert "987654" in after  # 系统作业不受影响
        assert result["registered"] == 2
        assert result["removed"] == len(removed_keys)

        # 幂等：再同步一次不重复注册（registered 为「本轮注册数」，含幂等替换）、无可清理项
        assert SchedulerUtil.sync_business_jobs(specs) == {"registered": 2, "removed": 0}
        assert _job_ids() == after
    finally:
        for job_key in ("ai_workspace_cron:12", "train_schedule:5", "ai_workflow_schedule:404"):
            SchedulerUtil.remove_business_job(job_key)
        try:
            scheduler.remove_job("987654")
        except JobLookupError:
            pass


def test_unserializable_business_func_keeps_job_log_and_logs_no_error(monkeypatch, test_client):
    """闭包 func 无法被序列化，但执行日志必须照常落库，且全程不得打 ERROR 日志。

    回归：`Job.__getstate__()` 对非模块级引用的 callable 会抛错，此前会让
    `_create_job_log` 整体失败（打一条 ERROR + 该作业的执行日志不落库）。
    """
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

    from app.core import ap_scheduler
    from app.core.database import engine
    from app.plugin.module_task.cronjob.job.model import JobModel

    spy = MagicMock()
    monkeypatch.setattr(ap_scheduler, "log", spy)
    # 「降级只提示一次」是类级标志，可能已被本文件更早的用例置位 → 先复位再断言（否则恒真）
    monkeypatch.setattr(SchedulerUtil, "_unserializable_state_warned", False)

    job_key = "ai_workspace_cron:9001"

    async def _closure_job():
        """闭包（非模块级引用）：`obj_to_ref` 解析不出，触发降级路径。"""
        return None

    SchedulerUtil.register_business_trigger(job_key, "interval", {"minutes": 5}, _closure_job)
    try:
        assert scheduler.get_job(job_key) is not None
        assert spy.error.call_count == 0, spy.error.call_args_list  # 不得打 ERROR 日志
        assert spy.warning.call_count == 1, spy.warning.call_args_list  # 降级只提示一次

        # 再取一次状态：类级标志生效，不重复刷屏
        assert SchedulerUtil._get_job_state(scheduler.get_job(job_key)) is not None
        assert spy.warning.call_count == 1

        # 执行日志（pending）必须落库，且 job_state 是降级后的最小状态
        with Session(engine) as session:
            rows = (
                session
                .query(JobModel)
                .filter(JobModel.job_id == job_key)
                .order_by(JobModel.id.desc())
                .all()
            )
        assert rows, "业务作业的执行日志未落库"
        assert rows[0].status == "pending"
        assert rows[0].job_state and '"trigger"' in rows[0].job_state
        assert rows[0].next_run_time
    finally:
        SchedulerUtil.remove_business_job(job_key)
        with Session(engine) as session:
            session.query(JobModel).filter(JobModel.job_id == job_key).delete()
            session.commit()


def test_serializable_system_job_state_stays_full(monkeypatch, test_client):
    """系统作业（模块级 func 引用，模拟 `NodeModel`）不走降级路径：无 warning、状态格式不变。

    护栏：本次修复只应在「状态无法序列化」时生效，不得改变可序列化作业的既有行为。
    """
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

    from app.core import ap_scheduler
    from app.core.database import engine
    from app.plugin.module_task.cronjob.job.model import JobModel

    spy = MagicMock()
    monkeypatch.setattr(ap_scheduler, "log", spy)

    job_key = "987655"  # 系统作业 id 为纯数字（模拟 NodeModel）
    scheduler.add_job(
        SchedulerUtil._task_wrapper,
        "interval",
        minutes=30,
        id=job_key,
        args=["1", "pass"],
        coalesce=True,
        max_instances=1,
    )
    try:
        assert spy.warning.call_count == 0, spy.warning.call_args_list  # 未触发降级
        assert spy.error.call_count == 0, spy.error.call_args_list
        with Session(engine) as session:
            row = (
                session
                .query(JobModel)
                .filter(JobModel.job_id == job_key)
                .order_by(JobModel.id.desc())
                .first()
            )
        assert row is not None, "系统作业的执行日志未落库"
        # 完整状态来自 `Job.__getstate__()`（含 executor 等字段），与降级最小状态可区分
        assert row.job_state and '"executor"' in row.job_state
    finally:
        scheduler.remove_job(job_key)
        with Session(engine) as session:
            session.query(JobModel).filter(JobModel.job_id == job_key).delete()
            session.commit()


def test_sync_business_jobs_prefixes_scope_cleanup(monkeypatch):
    """Important I1：`prefixes` 限定清理范围（多调用方只管自己的命名空间），None 保持旧语义。

    用「记录 `remove_business_job` 调用」的方式断言**清理候选集**：既精确验证范围判定，
    又不会真删掉别的模块（可能由启动期注册的）作业而污染后续用例。断言一律用子集/差集，
    不依赖进程内全局计数（B2/B3/B4 落地后启动期会有真实业务作业）。
    """

    async def _job():
        return None

    planted = ("ai_workspace_cron:701", "ai_workflow_schedule:702", "train_schedule:703")
    for job_key in planted:
        SchedulerUtil.register_business_trigger(job_key, "interval", {"minutes": 7}, _job)
    scheduler.add_job(_job, "interval", minutes=30, id="987657", coalesce=True)  # 系统作业

    removed_calls = _record_removals(monkeypatch)
    try:
        # ① 指定前缀：清理候选只含该前缀的作业（工作流/训练的残留绝不被清理）
        removed_calls.clear()
        result = SchedulerUtil.sync_business_jobs([], prefixes=("ai_workspace_cron:",))
        assert "ai_workspace_cron:701" in removed_calls
        assert all(key.startswith("ai_workspace_cron:") for key in removed_calls)
        assert result == {"registered": 0, "removed": len(removed_calls)}

        # ③ 空列表 + 指定前缀：只清该前缀的作业
        removed_calls.clear()
        result = SchedulerUtil.sync_business_jobs([], prefixes=("train_schedule:",))
        assert "train_schedule:703" in removed_calls
        assert all(key.startswith("train_schedule:") for key in removed_calls)
        assert result == {"registered": 0, "removed": len(removed_calls)}

        # 裸字符串兜底：按单个前缀处理（不拆成字符集），仍只命中该前缀
        removed_calls.clear()
        result = SchedulerUtil.sync_business_jobs([], prefixes="ai_workspace_cron:")
        assert "ai_workspace_cron:701" in removed_calls
        assert all(key.startswith("ai_workspace_cron:") for key in removed_calls)
        assert result == {"registered": 0, "removed": len(removed_calls)}

        # 空前缀元组：不清理任何作业（安全默认）
        removed_calls.clear()
        assert SchedulerUtil.sync_business_jobs([], prefixes=()) == {"registered": 0, "removed": 0}
        assert removed_calls == []

        # ② prefixes=None：清理全部业务前缀（启动期聚合同步的旧语义），系统作业仍不在范围内
        removed_calls.clear()
        result = SchedulerUtil.sync_business_jobs([])
        assert set(planted) <= set(removed_calls)
        assert "987657" not in removed_calls
        assert result == {"registered": 0, "removed": len(removed_calls)}
    finally:
        monkeypatch.undo()
        for job_key in (*planted, "987657"):
            SchedulerUtil.remove_business_job(job_key)
        try:
            scheduler.remove_job("987657")
        except JobLookupError:
            pass


def test_sync_business_jobs_skips_malformed_spec_without_aborting(monkeypatch):
    """M1：坏规格（元组长度不对）只跳过该条并记一次 warning，不中断整轮同步。

    打桩 `remove_business_job`：本用例只验证逐条容错，不应真删共享调度器上其它用例 /
    启动期（B2/B3/B4 落地后）注册的业务作业。
    """
    from unittest.mock import MagicMock

    from app.core import ap_scheduler

    spy = MagicMock()
    monkeypatch.setattr(ap_scheduler, "log", spy)
    removed_calls = _record_removals(monkeypatch)

    async def _job():
        return None

    result = SchedulerUtil.sync_business_jobs([
        ("ai_workspace_cron:801", "interval", {"minutes": 5}),  # 坏规格：3 元组
        ("ai_workspace_cron:802", "interval", {"minutes": 5}, _job),
    ])
    try:
        assert result["registered"] == 1  # 坏规格被跳过，好规格照常注册
        assert scheduler.get_job("ai_workspace_cron:802") is not None
        assert spy.warning.call_count == 1, spy.warning.call_args_list
        assert spy.error.call_count == 0, spy.error.call_args_list
        # 清理阶段不会误伤系统作业（记录器含注册前的同键移除，故用前缀白名单校验）
        business_prefixes = ("ai_workspace_cron:", "ai_workflow_schedule:", "train_schedule:")
        assert all(key.startswith(business_prefixes) for key in removed_calls)
    finally:
        monkeypatch.undo()
        SchedulerUtil.remove_business_job("ai_workspace_cron:802")
