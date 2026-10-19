"""RAG 后台任务：任务状态机、worker 与 job。"""
import asyncio


def _run(coro):
    return asyncio.run(coro)


def _claim_until(task_id: int, limit: int = 30):
    """抢到指定任务为止（跳过其它测试遗留的 pending 任务，避免顺序耦合）。"""
    from app.plugin.module_ai.knowledge import tasks

    for _ in range(limit):
        claimed = _run(tasks.claim_next())
        if claimed is None:
            return None
        if claimed["id"] == task_id:
            return claimed
        _run(tasks.update_task(claimed["id"], status="canceled"))
    return None


def test_create_claim_update_task():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("document_ingest", kb_id=1, document_id=2, payload={"a": 1}))
    assert t["status"] == "pending" and t["progress"] == 0

    claimed = _claim_until(t["id"])
    assert claimed is not None and claimed["status"] == "running"
    assert claimed["started_time"] is not None

    _run(tasks.update_task(t["id"], progress=40, step="抽词"))
    cur = _run(tasks.get_task(t["id"]))
    assert cur["progress"] == 40 and cur["step"] == "抽词"

    _run(tasks.update_task(t["id"], status="succeeded"))
    done = _run(tasks.get_task(t["id"]))
    assert done["status"] == "succeeded" and done["progress"] == 100
    assert done["finished_time"] is not None


def test_progress_is_clamped():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=1))
    _run(tasks.update_task(t["id"], progress=180))
    assert _run(tasks.get_task(t["id"]))["progress"] == 100
    _run(tasks.update_task(t["id"], progress=-5))
    assert _run(tasks.get_task(t["id"]))["progress"] == 0


def test_cancel_pending_becomes_canceled():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=1))
    c = _run(tasks.cancel_task(t["id"]))
    assert c["status"] == "canceled" and c["cancel_requested"] is True

    # 已终态的任务再取消：幂等返回，不改变状态
    again = _run(tasks.cancel_task(t["id"]))
    assert again["status"] == "canceled"


def test_cancel_missing_task_raises():
    from app.plugin.module_ai.knowledge import tasks

    try:
        _run(tasks.cancel_task(99999999))
    except ValueError as e:
        assert "任务不存在" in str(e)
    else:  # pragma: no cover
        raise AssertionError("不存在的任务应抛 ValueError")


def test_reset_stale_running():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=1))
    assert _claim_until(t["id"]) is not None
    assert _run(tasks.get_task(t["id"]))["status"] == "running"
    assert _run(tasks.reset_stale_running()) >= 1
    assert _run(tasks.get_task(t["id"]))["status"] == "pending"


def test_list_tasks_filters_and_pages():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=777))
    page = _run(tasks.list_tasks(kb_id=777))
    assert {"page_no", "page_size", "total", "has_next", "items"} <= set(page)
    assert any(item["id"] == t["id"] for item in page["items"])
    assert page["total"] >= 1


def _run_until_done(task_id: int, limit: int = 30):
    """同步驱动 worker 直到目标任务进入终态。"""
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import worker

    for _ in range(limit):
        status = _run(tasks.get_task(task_id))["status"]
        if status in ("succeeded", "failed", "canceled"):
            return status
        _run(worker.run_worker(max_iterations=1))
    return _run(tasks.get_task(task_id))["status"]


def test_worker_marks_failed_on_handler_error():
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import jobs

    t = _run(tasks.create_task("unit_test_fail"))

    async def boom(task):
        raise RuntimeError("故意失败")

    jobs.register("unit_test_fail", boom)
    try:
        assert _run_until_done(t["id"]) == "failed"
        cur = _run(tasks.get_task(t["id"]))
        assert "故意失败" in (cur["error"] or "")
    finally:
        jobs.JOB_HANDLERS.pop("unit_test_fail", None)


def test_worker_marks_succeeded_and_reports_progress():
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import jobs

    t = _run(tasks.create_task("unit_test_ok"))

    async def ok(task):
        await tasks.report_progress(task["id"], progress=50, step="一半")

    jobs.register("unit_test_ok", ok)
    try:
        assert _run_until_done(t["id"]) == "succeeded"
        cur = _run(tasks.get_task(t["id"]))
        assert cur["progress"] == 100
        assert cur["step"] == "一半"
    finally:
        jobs.JOB_HANDLERS.pop("unit_test_ok", None)


def test_worker_cancel_before_run_does_not_execute():
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import jobs

    executed = {"n": 0}
    t = _run(tasks.create_task("unit_test_cancel"))

    async def handler(task):
        executed["n"] += 1

    jobs.register("unit_test_cancel", handler)
    try:
        _run(tasks.cancel_task(t["id"]))
        _run_until_done(t["id"])
        assert _run(tasks.get_task(t["id"]))["status"] == "canceled"
        assert executed["n"] == 0
    finally:
        jobs.JOB_HANDLERS.pop("unit_test_cancel", None)


def test_worker_unknown_kind_fails():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("unit_test_unknown_kind"))
    assert _run_until_done(t["id"]) == "failed"
    assert "未知任务类型" in (_run(tasks.get_task(t["id"]))["error"] or "")
