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
