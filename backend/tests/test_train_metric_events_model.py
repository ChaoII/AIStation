"""``train_metric_events`` 模型行为测试（简单模式 bridge · Task 3）。

四组行为级验证（不 mock ``insert_event`` / ``list_events`` 本身）：

1. 幂等插入：同 ``(task_id, seq)`` 二次插入不重复落库（唯一约束兜底）；
2. ``type_`` 过滤：``list_events`` 按类型只返回匹配事件；
3. 排序分页：按 ``seq`` 升序，``limit`` / ``offset`` 生效；
4. ``ts`` 转换：float（epoch 秒）落库为 datetime，读回为 datetime（UTC 语义）。

参考 ``tests/test_ontology_regressions.py``：同步测试 + ``asyncio.run`` 包 async 代码；
需要应用（``test_client`` 启动 app 已建表），**不要** ``PYTEST_NO_APP=1``。

注意：会话用 ``async with async_db_session()``（**不带** ``.begin()``）——
``insert_event`` 语义自带 commit（幂等冲突时自己 rollback），若在 ``.begin()``
上下文内调用，内部 commit 会关闭上下文管理器的事务，后续操作直接
``InvalidRequestError``。
"""
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.core.database import async_db_session
from app.plugin.module_train.model import (
    TrainFramework,
    TrainMetricEvent,
    TrainTask,
    insert_event,
    list_events,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def task_id(test_client):
    """建一条真实训练任务，返回其 id（事件的 task_id 外键引用）。"""

    async def _create():
        async with async_db_session() as db:
            task = TrainTask(
                name="metric-events-test-task",
                framework=TrainFramework.TORKILN,
                dataset_id=1,
                docker_image="torchkiln:0.1.0",
            )
            db.add(task)
            await db.commit()
        return task.id

    return _run(_create())


def test_insert_event_idempotent(task_id, test_client):
    """同一 ``(task_id, seq)`` 第二次插入：返回 False 且不重复落库。"""

    async def _case():
        async with async_db_session() as db:
            ok1 = await insert_event(
                db, task_id, seq=1, ts=1_700_000_000.0, type_="step", payload={"epoch": 1})
            ok2 = await insert_event(
                db, task_id, seq=1, ts=1_700_000_000.0, type_="step", payload={"epoch": 1})
            count = (await db.execute(
                select(func.count()).select_from(TrainMetricEvent)
                .where(TrainMetricEvent.task_id == task_id)
            )).scalar_one()
        return ok1, ok2, count

    ok1, ok2, count = _run(_case())
    assert ok1 is True, "首次插入应返回 True"
    assert ok2 is False, "重复 (task_id, seq) 应返回 False（不落库）"
    assert count == 1, f"同 (task_id, seq) 只允许一行，实际 {count} 行"


def test_list_events_type_filter(task_id, test_client):
    """``list_events(type_='env')`` 只返回 env 事件。"""

    async def _case():
        async with async_db_session() as db:
            await insert_event(db, task_id, seq=10, ts=1_700_000_010.0,
                               type_="step", payload={"epoch": 10})
            await insert_event(db, task_id, seq=11, ts=1_700_000_011.0,
                               type_="step", payload={"epoch": 11})
            await insert_event(db, task_id, seq=12, ts=1_700_000_012.0,
                               type_="env", payload={"gpu": "0"})
            env_rows = await list_events(db, task_id, type_="env")
        return env_rows

    env_rows = _run(_case())
    assert [e["seq"] for e in env_rows] == [12], "type_ 过滤应只返回 env 事件"
    assert all(e["type"] == "env" for e in env_rows)


def test_list_events_order_limit_offset(task_id, test_client):
    """乱序插入后仍按 ``seq`` 升序；``limit`` / ``offset`` 生效。"""

    async def _case():
        async with async_db_session() as db:
            # 故意乱序插入，验证排序不依赖插入顺序
            await insert_event(db, task_id, seq=30, ts=1_700_000_030.0,
                               type_="order", payload={"n": 30})
            await insert_event(db, task_id, seq=28, ts=1_700_000_028.0,
                               type_="order", payload={"n": 28})
            await insert_event(db, task_id, seq=29, ts=1_700_000_029.0,
                               type_="order", payload={"n": 29})
            all_rows = await list_events(db, task_id, type_="order")
            paged = await list_events(db, task_id, type_="order", limit=2, offset=1)
        return all_rows, paged

    all_rows, paged = _run(_case())
    assert [e["seq"] for e in all_rows] == [28, 29, 30], "应按 seq 升序返回"
    assert [e["seq"] for e in paged] == [29, 30], "limit=2, offset=1 应取第 2、3 条"


def test_ts_float_stored_as_datetime(task_id, test_client):
    """``ts`` 传 float（epoch 秒）→ 落库为 datetime；读回仍是 datetime 且 UTC 语义一致。"""
    epoch = 1_700_000_000.0
    expected = datetime.fromtimestamp(epoch, tz=timezone.utc)

    async def _case():
        async with async_db_session() as db:
            await insert_event(db, task_id, seq=40, ts=epoch,
                               type_="ts", payload={})
            rows = await list_events(db, task_id, type_="ts")
        return rows

    rows = _run(_case())
    assert len(rows) == 1
    stored = rows[0]["ts"]
    assert isinstance(stored, datetime), "读回的 ts 必须是 datetime 对象"
    # SQLite 不存时区信息（读回 naive）；PG 的 timestamptz 读回 UTC aware。
    # 两种情况下「归一到 UTC 后比较」都应成立——即存的是 UTC 墙钟时间。
    assert stored.replace(tzinfo=timezone.utc) == expected, (
        f"ts 应为 UTC 语义（{expected.isoformat()}），实际 {stored!r}"
    )
