"""TorchKiln 简单模式指标读取测试（简单模式 bridge · Task 6）。

覆盖事件表**读取侧**的五组行为（真实走 SQLite 临时库，不 mock 落库/物化逻辑）：

1. ``/metrics``：simple 任务（hyperparams 带 ``__tk_mode`` 标记）从事件表物化——
   行结构与旧 ``metrics_log`` 行一致（``_kind``/``seq``/摊平字段）、seq 升序、
   ``offset`` 增量可用；
2. ``/metrics``：旧/容器任务（无标记，只有 ``metrics_log`` 列）仍返回旧行（兼容回退）；
3. ``/env-metrics``：只返回 env 事件行，每行带 ``ts``（epoch 秒）与嵌套 gpu，
   ``start``/``end`` 按 epoch 秒闭区间过滤；
4. ``/status``：simple 且 running 的任务，progress 由事件物化行推算
   （simple 任务无容器 train.log，不能走日志解析）；
5. ``/detail``：simple 任务 detail 契约里的 ``metrics_log`` 由事件表补全为物化行。

task_id 用显式新区间（≥3000）避免与 Task 3/4/5 测试冲突（同会话共享同一临时库）。
参考 ``tests/test_simple_event_ingest.py``：同步测试 + ``asyncio.run`` 包 async 代码；
需要应用（``test_client`` 启动 app 已建表），**不要** ``PYTEST_NO_APP=1``。
"""
import asyncio

import pytest

from app.core.database import async_db_session
from app.plugin.module_train.model import (
    TrainFramework,
    TrainStatus,
    TrainTask,
    insert_event,
)

#: 插件容器前缀 /train 下的任务端点
_URL = "/api/v1/train/task"


def _run(coro):
    return asyncio.run(coro)


def _make_task(task_id: int, name: str, hyperparams: dict,
               status=TrainStatus.PENDING, metrics_log: list | None = None) -> None:
    """按显式 id 建一条真实训练任务（满足事件表 task_id 外键约束）。"""

    async def _create():
        async with async_db_session() as db:
            db.add(TrainTask(
                id=task_id,
                name=name,
                framework=TrainFramework.TORKILN,
                dataset_id=1,
                docker_image="torchkiln:0.1.0",
                hyperparams=hyperparams,
                status=status,
                metrics_log=metrics_log,
            ))
            await db.commit()

    _run(_create())


def _insert_events(task_id: int, events: list[dict]) -> None:
    """批量幂等插入事件（payload 为完整事件，与回调端点落库约定一致）。"""

    async def _insert():
        async with async_db_session() as db:
            for ev in events:
                await insert_event(
                    db, task_id, seq=ev["seq"], ts=ev["ts"],
                    type_=ev["type"], payload=ev,
                )

    _run(_insert())


@pytest.fixture(scope="module")
def simple_task_id(test_client):
    """simple 任务（带 ``__tk_mode`` 标记）。"""
    _make_task(3001, "simple-metrics-read-test-task", {"__tk_mode": "simple"})
    return 3001


@pytest.fixture(scope="module")
def legacy_task_id(test_client):
    """旧任务（无标记，只有 metrics_log 列），验证兼容回退。"""
    old_rows = [
        {"_kind": "step", "seq": 1, "epoch": 1, "global_step": 10,
         "loss": 0.9, "lr": 0.01, "ips": 12.0, "total_epochs": 10},
        {"_kind": "eval", "seq": 2, "best": None, "epoch": 1,
         "global_step": 100, "main_value": 0.55, "precision": 0.6, "recall": 0.7},
    ]
    _make_task(3002, "legacy-metrics-read-test-task", {}, metrics_log=old_rows)
    return 3002


def test_metrics_from_events_for_simple(test_client, auth_headers, simple_task_id):
    """/metrics 对 simple 任务返回事件表物化行：结构与旧行一致、seq 升序、total 正确。"""
    _insert_events(simple_task_id, [
        {"task_id": simple_task_id, "seq": 3001, "ts": 1_700_000_100.0, "type": "step",
         "loss": 0.8, "lr": 0.01, "epoch": 1, "global_step": 10, "epoch_num": 10,
         "comps": {"cls": 0.5, "dfl": 0.3}},
        {"task_id": simple_task_id, "seq": 3002, "ts": 1_700_000_110.0, "type": "step",
         "loss": 0.6, "lr": 0.01, "epoch": 2, "global_step": 20, "epoch_num": 10,
         "comps": {"cls": 0.4, "dfl": 0.2}},
        {"task_id": simple_task_id, "seq": 3003, "ts": 1_700_000_120.0, "type": "eval",
         "epoch": 2, "global_step": 20, "main_indicator": "precision",
         "main_value": 0.7, "epoch_num": 10, "metrics": {"precision": 0.7, "recall": 0.8}},
    ])

    r = test_client.get(f"{_URL}/{simple_task_id}/metrics", headers=auth_headers)
    assert r.status_code == 200, f"/metrics 应 200，实际 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["task_id"] == simple_task_id
    items = data["items"]
    assert data["total"] == len(items) == 3, f"应物化出 3 行，实际 {len(items)}: {items}"

    # seq 升序 + 行结构与旧行一致（_kind/seq/业务字段齐全）
    assert [row["seq"] for row in items] == [3001, 3002, 3003], "应按 seq 升序物化"
    step1 = items[0]
    assert step1["_kind"] == "step", f"首行 _kind 应为 step，实际 {step1.get('_kind')}"
    assert step1["loss"] == 0.8 and step1["epoch"] == 1 and step1["total_epochs"] == 10
    assert step1["cls"] == 0.5 and step1["dfl"] == 0.3, "comps 应摊平进行"
    ev_row = items[2]
    assert ev_row["_kind"] == "eval" and ev_row["main_value"] == 0.7
    assert ev_row["precision"] == 0.7 and ev_row["recall"] == 0.8, "eval metrics 应摊平"


def test_metrics_fallback_metrics_log(test_client, auth_headers, legacy_task_id):
    """/metrics 对无标记旧任务仍返回 metrics_log 旧行（兼容回退，不读事件表）。"""
    r = test_client.get(f"{_URL}/{legacy_task_id}/metrics", headers=auth_headers)
    assert r.status_code == 200, f"/metrics 应 200，实际 {r.status_code}: {r.text}"
    data = r.json()["data"]
    items = data["items"]
    assert data["total"] == len(items) == 2, f"应返回 metrics_log 的 2 行，实际 {len(items)}"
    assert items[0]["loss"] == 0.9 and items[0]["total_epochs"] == 10, "应原样返回旧行"
    assert items[1]["_kind"] == "eval" and items[1]["main_value"] == 0.55


def test_env_metrics_filter(test_client, auth_headers, simple_task_id):
    """/env-metrics：只返回 env 行，每行带 ts（epoch 秒）与嵌套 gpu，start/end 闭区间过滤。"""
    _insert_events(simple_task_id, [
        {"task_id": simple_task_id, "seq": 3101, "ts": 1_700_002_000.0, "type": "env",
         "gpu": [{"id": 0, "util": 50.0, "mem_reserved_mb": 1024}], "cpu": 12.5,
         "mem": {"used_mb": 8192, "total_mb": 32768}},
        {"task_id": simple_task_id, "seq": 3102, "ts": 1_700_002_010.0, "type": "env",
         "gpu": [{"id": 0, "util": 60.0, "mem_reserved_mb": 2048}], "cpu": 22.5,
         "mem": {"used_mb": 9000, "total_mb": 32768}},
        {"task_id": simple_task_id, "seq": 3103, "ts": 1_700_002_020.0, "type": "env",
         "gpu": [{"id": 0, "util": 70.0, "mem_reserved_mb": 3072}], "cpu": 32.5,
         "mem": {"used_mb": 9500, "total_mb": 32768}},
        # 同任务下的 step 事件不应混入 env-metrics
        {"task_id": simple_task_id, "seq": 3104, "ts": 1_700_002_030.0, "type": "step",
         "loss": 0.4, "epoch": 3, "global_step": 30, "epoch_num": 10},
    ])

    r = test_client.get(f"{_URL}/{simple_task_id}/env-metrics", headers=auth_headers)
    assert r.status_code == 200, f"/env-metrics 应 200，实际 {r.status_code}: {r.text}"
    data = r.json()["data"]
    items = data["items"]
    assert data["task_id"] == simple_task_id
    assert data["total"] == len(items) == 3, f"应只返回 3 条 env 行，实际 {len(items)}"
    assert all(row["_kind"] == "env" for row in items), "不应混入非 env 行"
    for row, expect_ts, expect_util in zip(
            items, (1_700_002_000.0, 1_700_002_010.0, 1_700_002_020.0),
            (50.0, 60.0, 70.0), strict=True):
        assert row["seq"] in (3101, 3102, 3103)
        assert row["ts"] == pytest.approx(expect_ts), (
            f"ts 应为 epoch 秒（{expect_ts}），实际 {row['ts']!r}")
        assert row["gpu"][0]["util"] == expect_util, "gpu 嵌套结构应原样透传"
        assert "cpu" in row and "mem" in row

    # start/end 闭区间过滤（epoch 秒）
    r2 = test_client.get(f"{_URL}/{simple_task_id}/env-metrics",
                         params={"start": 1_700_002_005, "end": 1_700_002_015},
                         headers=auth_headers)
    assert r2.status_code == 200, f"带过滤参数应 200，实际 {r2.status_code}: {r2.text}"
    d2 = r2.json()["data"]
    assert d2["total"] == len(d2["items"]) == 1, f"闭区间应命中 1 条，实际 {d2['total']}"
    assert d2["items"][0]["seq"] == 3102

    r3 = test_client.get(f"{_URL}/{simple_task_id}/env-metrics",
                         params={"start": 1_700_002_010, "end": 1_700_002_020},
                         headers=auth_headers)
    d3 = r3.json()["data"]
    assert d3["total"] == len(d3["items"]) == 2, "闭区间两端均含，应命中 2 条"
    assert [row["seq"] for row in d3["items"]] == [3102, 3103]


def test_offset_incremental(test_client, auth_headers, simple_task_id):
    """/metrics?offset=N 只返回 seq>N 的物化行（断点续传语义）。"""
    r = test_client.get(f"{_URL}/{simple_task_id}/metrics", headers=auth_headers)
    items = r.json()["data"]["items"]
    assert items, "前置用例应已插入事件，物化行不应为空"
    seqs = [row["seq"] for row in items if isinstance(row.get("seq"), int)]
    max_seq = max(seqs)

    r2 = test_client.get(f"{_URL}/{simple_task_id}/metrics",
                         params={"offset": max_seq - 1}, headers=auth_headers)
    d2 = r2.json()["data"]
    assert [row["seq"] for row in d2["items"]] == [max_seq], (
        f"offset={max_seq - 1} 应只返回 seq={max_seq} 一行，实际 {d2['items']}")

    r3 = test_client.get(f"{_URL}/{simple_task_id}/metrics",
                         params={"offset": max_seq}, headers=auth_headers)
    assert r3.json()["data"]["items"] == [], "offset=max_seq 应返回空（无更新）"


def test_detail_progress_simple(test_client, auth_headers):
    """simple 且 running 的任务：/status 的 progress 由事件物化行推算（epoch/total_epochs）。"""
    task_id = 3003
    _make_task(task_id, "simple-progress-test-task", {"__tk_mode": "simple"},
               status=TrainStatus.RUNNING)
    _insert_events(task_id, [
        {"task_id": task_id, "seq": 3201, "ts": 1_700_003_000.0, "type": "step",
         "loss": 0.7, "epoch": 3, "global_step": 30, "epoch_num": 10},
        {"task_id": task_id, "seq": 3202, "ts": 1_700_003_010.0, "type": "step",
         "loss": 0.5, "epoch": 6, "global_step": 60, "epoch_num": 10},
    ])

    r = test_client.get(f"{_URL}/{task_id}/status", headers=auth_headers)
    assert r.status_code == 200, f"/status 应 200，实际 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["status"] == "running"
    assert data["progress"] == 60, (
        f"progress 应由事件行推算为 60（epoch 6/10），实际 {data['progress']}；"
        f"simple 任务无容器 train.log，不能依赖日志解析")
    # status 端点保持轻量契约：不下发 hyperparams / metrics_log
    assert "hyperparams" not in data and "metrics_log" not in data


def test_detail_metrics_log_materialized(test_client, auth_headers, simple_task_id):
    """/detail 对 simple 任务补全 metrics_log（物化行），保持 detail 契约一致。"""
    r = test_client.get(f"{_URL}/{simple_task_id}/detail", headers=auth_headers)
    assert r.status_code == 200, f"/detail 应 200，实际 {r.status_code}: {r.text}"
    data = r.json()["data"]
    rows = data.get("metrics_log")
    assert rows, "simple 任务 detail 的 metrics_log 应补全为事件物化行"
    seqs = [row["seq"] for row in rows if isinstance(row.get("seq"), int)]
    assert 3001 in seqs and 3003 in seqs, f"物化行应包含已插入事件，实际 seq={seqs}"
