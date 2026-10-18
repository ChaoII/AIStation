"""训练定时调度并入中心调度器（Task B4）。

覆盖：

- 新建定时训练计划 → 中心调度器出现 `train_schedule:{id}` 作业（启用即注册，函数为模块级可引用函数）；
- 禁用 → 作业移除（无幽灵作业）、再启用 → 重新注册、改表达式 → 触发器同步替换、删除 → 作业移除；
- 列表回显的 `next_run_time` **取自作业本身**（状态单一真源，训练模块不再自算下次运行时间）；
- 按模块同步只清理自己的 `train_schedule:` 前缀，绝不误删别的模块的业务作业（B1 审查钉死的约定）；
- A5 遗留的「`croniter` 到期判定」死轮询路径已彻底删除（`get_due_schedules` 及其调用点），
  且训练模块的其它轮询职责（孤儿恢复 / GPU 看门狗）保留。
"""

import asyncio
import inspect
from types import SimpleNamespace

from apscheduler.triggers.cron import CronTrigger

# `ap_scheduler` 与 `app.plugin.module_task` 存在**既有**循环导入：先 import `module_task`
# 则成功（同 tests/test_business_scheduler.py 的处理，非本任务引入）。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil, scheduler
from app.plugin.module_train import scheduler as train_scheduler
from app.plugin.module_train.schedule_service import ScheduleService
from app.utils.trigger_util import TriggerUtil

_AUTH = SimpleNamespace(user=SimpleNamespace(id=1))


def _data(cron_expr: str, name: str = "pytest-B4-定时训练") -> SimpleNamespace:
    """构造与 `TrainScheduleCreateSchema` 同形的入参（签名与 `create_schedule` 一致）。"""
    return SimpleNamespace(
        name=name,
        dataset_id=1,
        annotation_task_id=None,
        framework="torchkiln",
        hyperparams={},
        cron_expr=cron_expr,
    )


def _job_key(schedule_id: int) -> str:
    return f"train_schedule:{schedule_id}"


def _insert_schedule_row(trigger_args: str | None, name: str = "pytest-B4-直插") -> int:
    """直接落一条计划行（用于构造遗留脏数据场景，绕过写入口的校验）。"""

    async def _run() -> int:
        from app.core.database import async_db_session
        from app.plugin.module_train.schedule_model import TrainScheduleModel

        async with async_db_session.begin() as db:
            row = TrainScheduleModel(
                name=name,
                dataset_id=1,
                framework="torchkiln",
                trigger="cron",
                trigger_args=trigger_args,
            )
            db.add(row)
            await db.flush()
            return row.id

    return asyncio.run(_run())


def test_create_schedule_registers_business_job():
    """新建计划（默认启用）→ 作业注册；作业函数模块级可引用、参数为计划 id、触发器同源。"""
    created = asyncio.run(ScheduleService.create_schedule(_data("0 9 * * 1-5"), _AUTH))
    sid = created["id"]
    try:
        job = scheduler.get_job(_job_key(sid))
        assert job is not None, "新建定时训练计划后中心调度器必须有对应作业"
        assert job.func is train_scheduler.run_scheduled_training  # 模块级引用（可日志/可序列化）
        assert job.args == (sid,)
        assert isinstance(job.trigger, CronTrigger)
        # 触发器与统一层同源（写入即规范化：1-5 → mon,tue,wed,thu,fri）
        assert str(job.trigger) == str(TriggerUtil.to_cron_trigger("0 9 * * mon,tue,wed,thu,fri"))
        assert job.misfire_grace_time == 60 and job.coalesce is True
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))
    assert scheduler.get_job(_job_key(sid)) is None, "删除计划后作业必须移除（不留幽灵作业）"


def test_disable_reenable_and_reconfigure_sync_job():
    """禁用 → 移除；再启用 → 重新注册；改表达式 → 触发器同步替换。"""
    created = asyncio.run(ScheduleService.create_schedule(_data("0 9 * * mon"), _AUTH))
    sid = created["id"]
    try:
        assert scheduler.get_job(_job_key(sid)) is not None

        asyncio.run(ScheduleService.update_schedule(sid, SimpleNamespace(enabled=False)))
        assert scheduler.get_job(_job_key(sid)) is None, "禁用后不得残留作业"

        asyncio.run(ScheduleService.update_schedule(sid, SimpleNamespace(enabled=True)))
        assert scheduler.get_job(_job_key(sid)) is not None, "重新启用后必须重新注册"

        asyncio.run(ScheduleService.update_schedule(sid, SimpleNamespace(cron_expr="30 2 * * *")))
        job = scheduler.get_job(_job_key(sid))
        assert job is not None
        assert str(job.trigger) == str(TriggerUtil.to_cron_trigger("30 2 * * *"))
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))


def test_list_next_run_time_comes_from_job():
    """列表的 `next_run_time` 必须等于作业的 `next_run_time`（单一真源，模块不自算）。"""
    created = asyncio.run(ScheduleService.create_schedule(_data("0 9 * * mon"), _AUTH))
    sid = created["id"]
    try:
        job = scheduler.get_job(_job_key(sid))
        assert job is not None and job.next_run_time is not None  # 调度器已启动，作业有下次运行时间
        rows = asyncio.run(ScheduleService.list_schedules())
        row = next(r for r in rows if r["id"] == sid)
        assert row["next_run_time"] == job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))


def test_update_with_legacy_invalid_trigger_args_does_not_raise():
    """遗留脏表达式（Quartz 6 段）行只改名字：不得 500，也不注册幽灵作业。"""
    sid = _insert_schedule_row("0 0 9 L * *", name="pytest-B4-遗留")
    try:
        asyncio.run(ScheduleService.update_schedule(sid, SimpleNamespace(name="pytest-B4-改名")))
        assert scheduler.get_job(_job_key(sid)) is None, "非法表达式不得注册作业"
        rows = asyncio.run(ScheduleService.list_schedules())
        row = next(r for r in rows if r["id"] == sid)
        assert row["name"] == "pytest-B4-改名"
        assert row["next_run_time"] is None  # 没有作业 → 没有下次运行时间（列表可见）
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))


def test_sync_train_schedule_jobs_only_touches_own_prefix():
    """按模块同步只清理 `train_schedule:` 前缀，别的模块的业务作业不受影响。"""
    sid = _insert_schedule_row("0 9 * * mon", name="pytest-B4-同步")

    async def _other_job():
        return None

    SchedulerUtil.register_business_trigger(
        "ai_workspace_cron:9101", "interval", {"minutes": 5}, _other_job
    )
    try:
        result = asyncio.run(ScheduleService.sync_train_schedule_jobs())
        assert result["registered"] >= 1
        assert scheduler.get_job(_job_key(sid)) is not None
        assert scheduler.get_job("ai_workspace_cron:9101") is not None, "别的模块的作业不得被清理"
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))
        SchedulerUtil.remove_business_job("ai_workspace_cron:9101")


def test_due_schedule_polling_path_is_removed():
    """A5 遗留的 `croniter` 到期判定死轮询路径必须彻底删除（不是留个恒返回 [] 的方法）。

    用 AST 检查**真实使用**（属性访问 / 导入 / 调用），不检查注释与文档字符串：
    删除原因写在注释里是有价值的，不该被这种守卫测试逼着删掉。
    """
    import ast

    assert not hasattr(ScheduleService, "get_due_schedules"), "死方法必须删除，而不是留着被继续调用"

    tree = ast.parse(inspect.getsource(train_scheduler))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.name for n in ast.walk(tree) if isinstance(n, ast.alias)}
    assert "get_due_schedules" not in names, "scheduler.py 不得再调用到期判定轮询"
    assert "croniter" not in names, "训练定时不再用 croniter 自判到期"

    # 只删「定时调度」这一条路径：训练模块的其它轮询职责必须保留（同样按 AST 真实调用判定）
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "recover_orphans" in called, "周期孤儿恢复轮询必须保留"
    assert "reap_stale" in called, "GPU/端口看门狗必须保留"


def test_remove_train_schedule_job_survives_scheduler_not_running(monkeypatch):
    """调度器未启动时 APScheduler 抛 `SchedulerNotRunningError`（不是 `JobLookupError`）：
    移除作业不得把「删除/禁用计划」的请求打成 500。"""
    from apscheduler.schedulers.base import SchedulerNotRunningError

    from app.core.ap_scheduler import SchedulerUtil
    from app.plugin.module_train import schedule_service as sched_svc

    def _boom(_job_key):
        raise SchedulerNotRunningError

    monkeypatch.setattr(SchedulerUtil, "remove_business_job", _boom)
    assert sched_svc.remove_train_schedule_job(123456) is False  # 吞掉异常，接口照常成功
    sched_svc.sync_train_schedule_job(123456, "cron", "0 9 * * mon", enabled=False)  # 同样不得抛


# ---------------------------------------------------------------- 作业执行体行为
#
# 旧轮询路径自 A5 起恒返回 []，等于「定时训练真的被触发」这条语义**从未被测过**——
# 而这正是本任务存在的意义。下面直接执行作业函数（两侧副作用打桩），覆盖：
# 启用行 → 建任务 + 启动 + 回写；禁用行 → 不建不回写；已删除行 → 静默跳过；建任务失败 → 吞掉且作业仍健康。


def _read_row(schedule_id: int) -> dict:
    """读回计划行的执行状态（作业回写断言用）。"""

    async def _run() -> dict:
        from app.core.database import async_db_session
        from app.plugin.module_train.schedule_model import TrainScheduleModel

        async with async_db_session() as db:
            row = await db.get(TrainScheduleModel, schedule_id)
            return {
                "enabled": row.enabled,
                "last_run_at": row.last_run_at,
                "last_task_id": row.last_task_id,
            }

    return asyncio.run(_run())


def _patch_training_side(monkeypatch, *, new_task_id: int | None = 4242) -> dict:
    """把执行体两侧（建任务 / 启动训练）换成记录器：不落库、不起容器。"""
    from app.plugin.module_train.service import TrainService

    calls: dict = {"created": [], "started": []}

    async def _fake_create_task(data, auth):
        calls["created"].append((data.name, auth.user.id))
        if new_task_id is None:
            raise RuntimeError("模拟建任务失败")
        return {"id": new_task_id}

    async def _fake_start_training(task_id):
        calls["started"].append(task_id)

    monkeypatch.setattr(TrainService, "create_task", _fake_create_task)
    monkeypatch.setattr(train_scheduler, "start_training", _fake_start_training)
    return calls


def test_run_scheduled_training_creates_task_and_writes_back(monkeypatch):
    """启用行：真的建训练任务（以计划创建者身份）+ 立即启动 + 回写执行状态。"""
    sid = _insert_schedule_row("0 9 * * mon", name="pytest-B4-执行体")
    calls = _patch_training_side(monkeypatch)
    try:
        asyncio.run(train_scheduler.run_scheduled_training(sid))
        # 直插行没有 created_id → 退化为 1（admin），与旧轮询口径一致
        assert calls["created"] == [("[定时] pytest-B4-执行体", 1)]
        assert calls["started"] == [4242]
        row = _read_row(sid)
        assert row["last_task_id"] == 4242, "必须回写本次触发的任务 id"
        assert row["last_run_at"] is not None, "必须回写执行时间"
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))


def test_run_scheduled_training_skips_disabled_row(monkeypatch):
    """禁用行：不建任务、不回写（作业与调度行之间有窗口期，不得误触发已停用的计划）。"""
    sid = _insert_schedule_row("0 9 * * mon", name="pytest-B4-执行体禁用")
    asyncio.run(ScheduleService.update_schedule(sid, SimpleNamespace(enabled=False)))
    calls = _patch_training_side(monkeypatch)
    try:
        asyncio.run(train_scheduler.run_scheduled_training(sid))
        assert calls["created"] == [] and calls["started"] == []
        row = _read_row(sid)
        assert row["last_run_at"] is None and row["last_task_id"] is None
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))


def test_run_scheduled_training_skips_deleted_row(monkeypatch):
    """计划已被删除：静默跳过，不抛异常、不建任务。"""
    calls = _patch_training_side(monkeypatch)
    asyncio.run(train_scheduler.run_scheduled_training(10**9))
    assert calls["created"] == [] and calls["started"] == []


def test_run_scheduled_training_swallows_failure_and_keeps_job_healthy(monkeypatch):
    """建任务抛异常：不冒出（只记日志）、回写 last_task_id=None、已注册作业仍健康。"""
    sid = _insert_schedule_row("0 9 * * mon", name="pytest-B4-执行体失败")
    asyncio.run(ScheduleService.sync_train_schedule_jobs())  # 先有作业，才能断言失败后仍健康
    calls = _patch_training_side(monkeypatch, new_task_id=None)
    try:
        asyncio.run(train_scheduler.run_scheduled_training(sid))  # 不得抛出
        assert calls["created"], "应已尝试建任务（随后失败）"
        assert calls["started"] == [], "建任务失败 → 不得启动训练"
        row = _read_row(sid)
        assert row["last_task_id"] is None
        assert row["last_run_at"] is not None, "失败也记录执行时间（与旧轮询行为一致）"
        job = scheduler.get_job(_job_key(sid))
        assert job is not None and job.next_run_time is not None, "作业不得因一次失败而失效/被移除"
    finally:
        asyncio.run(ScheduleService.delete_schedules([sid]))
