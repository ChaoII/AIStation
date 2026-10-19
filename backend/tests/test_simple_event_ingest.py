"""TorchKiln 简单模式事件接收端点测试（简单模式 bridge · Task 4）。

覆盖 ``POST /api/v1/train/internal/events`` 的四组行为（不 mock ``insert_event``，
真实走 SQLite 临时库；仅 monkeypatch ``publish_metric`` 与回调令牌）：

1. 鉴权 fail-closed：未配置令牌 / 缺 header / 错误 token → 一律 401；
2. 合法事件：201 + ``publish_metric`` 收到与 ``_row_from_event`` 同结构的行；
3. 幂等：同 ``(task_id, seq)`` 第二次回调仍 201，但不重复落库、不重复 publish；
4. 限流豁免：快速连发 70 个合法请求不触发 429（依赖
   ``settings.RATE_LIMIT_PATH_OVERRIDES`` 对该路径的独立限额）。

参考 ``tests/test_train_metric_events_model.py``：同步测试 + ``asyncio.run`` 包
async 代码；需要应用（``test_client`` 启动 app 已建表），**不要** ``PYTEST_NO_APP=1``。

task_id/seq 区间约定：本文件自建独立任务（不与 Task 3 测试共享任务），seq 从
1000 起——同会话共享同一临时库，避免 ``(task_id, seq)`` 唯一键跨文件冲突。
"""
import asyncio

import pytest
from sqlalchemy import func, select

from app.config.setting import settings
from app.core.database import async_db_session
from app.plugin.module_train.model import TrainFramework, TrainMetricEvent, TrainTask

#: 测试用共享令牌（经 monkeypatch 写入 settings）
_TOKEN = "test-token"
#: 请求头名（与端点实现约定一致）
_TOKEN_HEADER = "X-Torchkiln-Token"
#: 端点完整路径（插件容器前缀 /train）
_URL = "/api/v1/train/internal/events"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def task_id(test_client):
    """建一条真实训练任务，返回其 id（满足事件表 task_id 外键约束）。"""

    async def _create():
        async with async_db_session() as db:
            task = TrainTask(
                name="simple-event-ingest-test-task",
                framework=TrainFramework.TORKILN,
                dataset_id=1,
                docker_image="torchkiln:0.1.0",
            )
            db.add(task)
            await db.commit()
        return task.id

    return _run(_create())


def _step_body(task_id: int, seq: int) -> dict:
    """一个最小合法 step 事件（字段平铺）。"""
    return {
        "task_id": task_id,
        "seq": seq,
        "ts": 1_700_000_000.0 + seq,
        "type": "step",
        "loss": 0.5,
        "epoch": 1,
    }


def test_receiver_auth_fail_closed(test_client, monkeypatch, task_id):
    """鉴权三态：未配置令牌 / 缺 header / 错误 token → 一律 401（fail-closed）。"""
    body = _step_body(task_id, seq=1002)

    # 态一：令牌未配置（空）→ 即使请求体合法也必须 401
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", "")
    r = test_client.post(_URL, json=body)
    assert r.status_code == 401, f"未配置令牌应 401 fail-closed，实际 {r.status_code}: {r.text}"

    # 态二：已配置但请求缺 header → 401
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)
    r = test_client.post(_URL, json=body)
    assert r.status_code == 401, f"缺 token header 应 401，实际 {r.status_code}: {r.text}"

    # 态三：token 不匹配 → 401
    r = test_client.post(_URL, json=body, headers={_TOKEN_HEADER: "wrong-token"})
    assert r.status_code == 401, f"错误 token 应 401，实际 {r.status_code}: {r.text}"


def test_receiver_ingest_and_publish(test_client, monkeypatch, task_id):
    """合法 step 事件：201 + publish_metric 收到 ``_kind=='step'`` 的行且字段透传。"""
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)
    published = []
    # 控制器端点在函数体内延迟 import publish_metric，patch 模块属性即可命中
    monkeypatch.setattr(
        "app.plugin.module_train.torchkiln_executor.publish_metric",
        lambda tid, row: published.append((tid, row)),
    )

    r = test_client.post(_URL, json=_step_body(task_id, seq=1000), headers={_TOKEN_HEADER: _TOKEN})
    assert r.status_code == 201, f"合法事件应 201，实际 {r.status_code}: {r.text}"
    assert published, "新插入的事件应触发 publish_metric 扇出"
    assert published[0][0] == task_id
    row = published[0][1]
    assert row["_kind"] == "step", f"行 _kind 应为 step，实际 {row.get('_kind')}"
    assert row["seq"] == 1000
    assert row["loss"] == 0.5, "step 字段应原样透传进行"
    assert row["epoch"] == 1


def test_duplicate_seq_not_reingested(test_client, monkeypatch, task_id):
    """同一 ``(task_id, seq)`` 第二次回调：仍 201，但不重复落库、不重复 publish。"""
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)
    published = []
    monkeypatch.setattr(
        "app.plugin.module_train.torchkiln_executor.publish_metric",
        lambda tid, row: published.append((tid, row)),
    )

    body = _step_body(task_id, seq=1100)
    r1 = test_client.post(_URL, json=body, headers={_TOKEN_HEADER: _TOKEN})
    r2 = test_client.post(_URL, json=body, headers={_TOKEN_HEADER: _TOKEN})
    assert r1.status_code == 201 and r2.status_code == 201, (
        f"重复回调也应返回 201（幂等），实际 {r1.status_code}/{r2.status_code}")
    assert len(published) == 1, f"重复 seq 不应二次扇出，实际 publish {len(published)} 次"

    # DB 中该 (task_id, seq) 仅 1 行
    async def _count():
        async with async_db_session() as db:
            return (await db.execute(
                select(func.count()).select_from(TrainMetricEvent).where(
                    TrainMetricEvent.task_id == task_id,
                    TrainMetricEvent.seq == 1100,
                )
            )).scalar_one()

    assert _run(_count()) == 1, "重复 seq 在事件表只允许一行"


def test_env_event_rendered(test_client, monkeypatch, task_id):
    """env 事件：行 ``_kind=='env'``，gpu/cpu/mem/disk/net 嵌套结构不摊平、原样透传。"""
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)
    published = []
    monkeypatch.setattr(
        "app.plugin.module_train.torchkiln_executor.publish_metric",
        lambda tid, row: published.append((tid, row)),
    )

    body = {
        "task_id": task_id,
        "seq": 1200,
        "ts": 1_700_001_200.0,
        "type": "env",
        "gpu": [{"id": 0, "util": 50.0, "mem_reserved_mb": 1024,
                 "mem_allocated_mb": 512, "mem_total_mb": 16384,
                 "temp_c": 40.0, "power_w": 60.0}],
        "cpu": 12.5,
        "cpu_per_core": [1.0, 2.0, 3.0, 4.0],
        "mem": {"used_mb": 8192, "total_mb": 32768},
        "disk": {"read_mb_s": 10.0, "write_mb_s": 20.0, "free_mb": 500000},
        "net": {"rx_mb_s": 5.0, "tx_mb_s": 2.5},
    }
    r = test_client.post(_URL, json=body, headers={_TOKEN_HEADER: _TOKEN})
    assert r.status_code == 201, f"env 事件应 201，实际 {r.status_code}: {r.text}"
    assert published, "env 事件应触发 publish_metric 扇出"
    row = published[0][1]
    assert row["_kind"] == "env"
    assert row["seq"] == 1200
    assert "gpu" in row and isinstance(row["gpu"], list), "gpu 应为嵌套列表（不摊平）"
    assert row["cpu"] == 12.5
    assert row["mem"] == {"used_mb": 8192, "total_mb": 32768}
    assert row["disk"] == {"read_mb_s": 10.0, "write_mb_s": 20.0, "free_mb": 500000}
    assert row["net"] == {"rx_mb_s": 5.0, "tx_mb_s": 2.5}


def test_internal_not_rate_limited(test_client, monkeypatch, task_id):
    """限流豁免：10 秒内连发 70 个合法请求全部 201（train 模块默认仅 60 次/10s）。"""
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)
    published = []
    monkeypatch.setattr(
        "app.plugin.module_train.torchkiln_executor.publish_metric",
        lambda tid, row: published.append((tid, row)),
    )

    for i in range(70):
        r = test_client.post(_URL, json=_step_body(task_id, seq=2000 + i),
                             headers={_TOKEN_HEADER: _TOKEN})
        assert r.status_code == 201, (
            f"第 {i + 1} 个请求被限流或失败：{r.status_code} {r.text}"
            f"——检查 settings.RATE_LIMIT_PATH_OVERRIDES 是否豁免了该内部路径")
