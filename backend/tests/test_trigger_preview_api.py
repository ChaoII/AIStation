"""Task A7：触发预览接口 + 列表行 `needs_review` + A3 审查遗留收口。

三层覆盖：

1. 统一层 `TriggerUtil.preview` / `TriggerUtil.needs_review` 的契约
   （纯逻辑，`PYTEST_NO_APP=1` 可快速跑）；
2. A3 遗留：日字段「覆盖全集」（`*` / `*/1` / `1-31`）不得被判成「日/周同时指定」；
3. 四个模块各一条 `POST .../trigger/preview`（含 brief 逐字用例）与列表 `needs_review` 标注。

接口路径（插件容器前缀 `/ai`、`/train`、`/task` + 各自 router 前缀）：

- AI 工作台 `/api/v1/ai/workspace/trigger/preview`
- AI 工作流 `/api/v1/ai/workflows/trigger/preview`
- 模型训练 `/api/v1/train/trigger/preview`
- 定时任务节点 `/api/v1/task/cronjob/node/trigger/preview`
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import pytest

from app.utils.trigger_util import TriggerUtil

WORKSPACE_PREVIEW = "/api/v1/ai/workspace/trigger/preview"
WORKFLOW_PREVIEW = "/api/v1/ai/workflows/trigger/preview"
TRAIN_PREVIEW = "/api/v1/train/trigger/preview"
NODE_PREVIEW = "/api/v1/task/cronjob/node/trigger/preview"
PREVIEW_URLS = [WORKSPACE_PREVIEW, WORKFLOW_PREVIEW, TRAIN_PREVIEW, NODE_PREVIEW]

#: 预览响应的固定四字段（契约）
PREVIEW_KEYS = {"valid", "reason", "describe", "next_run"}


# ============================================================ 统一层：preview 契约


def test_preview_valid_cron_returns_describe_and_next_run():
    """合法表达式：人话描述 + 下次运行时间（`Asia/Shanghai` 墙钟时间，可直接展示）。"""
    data = TriggerUtil.preview("cron", "0 9 * * 1")
    assert set(data) == PREVIEW_KEYS
    assert data["valid"] is True
    assert data["reason"] == ""
    assert "周一" in data["describe"]
    assert data["next_run"]
    # 输出格式与 date 参数一致（YYYY-MM-DD HH:mm:ss），前端无需再格式化
    datetime.strptime(data["next_run"], "%Y-%m-%d %H:%M:%S")


def test_preview_invalid_cron_returns_readable_reason():
    """非法表达式：`valid=False` + 可读原因 + 无下次运行时间（接口 200，不 500）。"""
    data = TriggerUtil.preview("cron", "0 0 9 L * *")
    assert set(data) == PREVIEW_KEYS
    assert data["valid"] is False
    assert "L" in data["reason"]  # 原因来自统一层，指明具体字段问题
    assert data["next_run"] is None


def test_preview_unifies_validate_tuple_and_exception_forms():
    """双形态收敛：`validate` 返回元组、`describe` 抛 `CustomException`，调用方只见一种形态。"""
    data = TriggerUtil.preview("monthly", None)
    assert data["valid"] is False
    assert "未知的触发类型" in data["reason"]
    assert data["describe"] == "" and data["next_run"] is None


@pytest.mark.parametrize(
    ("trigger", "args", "hint"),
    [
        ("cron", "0 9 31 6 *", "永远不会触发"),  # cron 永不触发
        ("date", "2000-01-01 00:00:00", "过去时间"),  # date 已过期
    ],
)
def test_preview_distinguishes_two_no_next_run_semantics(trigger, args, hint):
    """`next_run is None` 的两种语义给**不同**提示，不笼统写「表达式非法」。"""
    data = TriggerUtil.preview(trigger, args)
    assert data["valid"] is False
    assert hint in data["reason"]
    assert "非法" not in data["reason"]


def test_preview_supports_interval_and_now():
    interval = TriggerUtil.preview("interval", {"hours": 2, "minutes": 30})
    assert interval["valid"] is True
    assert "2 小时" in interval["describe"] and interval["next_run"]

    now = TriggerUtil.preview("now", None)
    assert now["valid"] is True
    assert now["describe"] and now["next_run"]


@pytest.mark.parametrize(
    ("trigger", "args"),
    [
        ("cron", ""),
        ("cron", None),
        ("cron", "0 9 * * 5-1"),
        ("interval", {"hours": 0}),
        ("interval", "not-json"),
        ("date", "2026-13-45 99:99:99"),
        (None, "0 9 * * *"),
    ],
)
def test_preview_never_raises_on_dirty_payloads(trigger, args):
    """接口层直接回显：任何脏数据都收敛成 `valid=False` + `reason`，不得抛异常（500）。"""
    data = TriggerUtil.preview(trigger, args)
    assert set(data) == PREVIEW_KEYS
    assert data["valid"] is False and data["reason"]
    assert data["next_run"] is None


# ============================================================ A3 遗留：日字段「覆盖全集」


@pytest.mark.parametrize("day", ["*", "*/1", "1-31"])
def test_validate_cron_day_covers_full_month_is_not_day_weekday_conflict(day):
    """`0 9 1-31 * mon` / `0 9 */1 * mon` 语义等于「每天 + 周一」，不得判非法。"""
    ok, reason = TriggerUtil.validate("cron", f"0 9 {day} * mon")
    assert ok is True, reason


@pytest.mark.parametrize("day", ["*", "*/1", "1-31"])
def test_preview_day_covers_full_month_describes_weekday(day):
    """描述与实际触发一致：日字段覆盖全集时按「周」描述，不写成「每月 1-31 日」。"""
    data = TriggerUtil.preview("cron", f"0 9 {day} * mon")
    assert data["valid"] is True
    assert "周一" in data["describe"]


@pytest.mark.parametrize("expr", ["0 9 15 * mon", "0 9 1-15 * mon"])
def test_validate_cron_still_rejects_real_day_weekday_conflict(expr):
    """真正受限的日字段仍判非法（放宽只针对「覆盖全集」，不是把规则删掉）。"""
    ok, reason = TriggerUtil.validate("cron", expr)
    assert ok is False and "只指定其一" in reason


# ============================================================ 统一层：needs_review


@pytest.mark.parametrize(
    ("trigger", "args", "expected"),
    [
        # ① 迁移跳过 / 未配置（trigger_args 为空）
        ("cron", None, True),
        ("cron", "", True),
        ("cron", "   ", True),
        (None, None, True),
        # ② 有表达式但按新校验不通过
        ("cron", "0 0 9 L * *", True),  # 遗留 Quartz 6 段
        ("cron", "0 0 9 15W * *", True),
        ("cron", "0 9 31 6 *", True),  # 永不触发的日/月组合
        ("cron", "0 9 1 * mon", True),  # 日/周真正冲突
        ("interval", {"hours": 0}, True),
        # 正常行不误标
        ("cron", "0 9 * * mon", False),
        ("cron", "0 9 1-31 * mon", False),  # 日字段覆盖全集（A3 遗留）
        ("interval", {"minutes": 30}, False),
        ("now", None, False),  # `now` 按契约本就没有参数
    ],
)
def test_needs_review(trigger, args, expected):
    assert TriggerUtil.needs_review(trigger, args) is expected


def test_needs_review_never_raises_on_dirty_args():
    """列表接口逐行标注：单行脏数据不得让整个列表 500（异常按「需人工确认」处理）。"""
    assert TriggerUtil.needs_review("cron", {"unexpected": "object"}) is True
    assert TriggerUtil.needs_review("interval", "not-json") is True


# ============================================================ 接口：四模块 thin route


def test_trigger_preview_endpoint(test_client, auth_headers):
    """brief Step 1 逐字用例：AI 工作流的预览接口。"""
    r = test_client.post(
        WORKFLOW_PREVIEW,
        json={"trigger": "cron", "trigger_args": "0 9 * * 1"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["valid"] is True and "周一" in data["describe"] and data["next_run"]

    bad = test_client.post(
        WORKFLOW_PREVIEW,
        json={"trigger": "cron", "trigger_args": "0 0 9 L * *"},
        headers=auth_headers,
    )
    assert bad.json()["data"]["valid"] is False and bad.json()["data"]["reason"]


@pytest.mark.parametrize("url", PREVIEW_URLS)
def test_trigger_preview_routes_of_all_modules(test_client, auth_headers, url):
    """四个模块各一条 thin route：同一入参必须给出同一份（统一层）结果。"""
    r = test_client.post(
        url, json={"trigger": "interval", "trigger_args": {"hours": 1}}, headers=auth_headers
    )
    assert r.status_code == 200, f"{url} → {r.status_code} {r.text}"
    data = r.json()["data"]
    assert set(data) == PREVIEW_KEYS
    assert data["valid"] is True
    assert "1 小时" in data["describe"] and data["next_run"]


@pytest.mark.parametrize("url", PREVIEW_URLS)
def test_trigger_preview_returns_200_for_invalid_expression(test_client, auth_headers, url):
    """非法表达式走 `valid=false`（200），不落到 400/500 —— 供前端实时预览。"""
    r = test_client.post(
        url, json={"trigger": "cron", "trigger_args": "0 9 31 6 *"}, headers=auth_headers
    )
    assert r.status_code == 200, f"{url} → {r.status_code} {r.text}"
    assert r.json()["data"]["valid"] is False


@pytest.mark.parametrize("url", PREVIEW_URLS)
def test_trigger_preview_requires_auth(test_client, url):
    """预览同样受鉴权保护（未带 token → 401/403，不得 200）。"""
    r = test_client.post(
        url,
        json={"trigger": "cron", "trigger_args": "0 9 * * *"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert r.status_code in (401, 403), r.text


# ============================================================ 列表接口：needs_review 标注


def _insert_legacy_workspace_cron(name: str) -> int:
    """直接落一条「有表达式但新校验不通过」的工作台定时任务（写入接口会拒绝，模拟存量数据）。"""

    async def _run() -> int:
        from app.core.database import async_db_session
        from app.plugin.module_ai.workspace.model import AiWorkspaceCronModel

        async with async_db_session.begin() as db:
            row = AiWorkspaceCronModel(name=name, trigger="cron", trigger_args="0 0 9 L * *")
            db.add(row)
            await db.flush()
            return row.id

    return asyncio.run(_run())


def test_workspace_cron_list_flags_both_kinds_of_rows(test_client, auth_headers):
    """工作台定时任务列表：① 空表达式（迁移跳过）与 ② 新校验不通过，都标 `needs_review`。"""
    skipped = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={"name": f"pytest-A7-空表达式-{uuid.uuid4().hex[:6]}", "cron": "", "enabled": False},
        headers=auth_headers,
    )
    assert skipped.status_code == 200, skipped.text
    skipped_id = skipped.json()["data"]["id"]

    legacy_id = _insert_legacy_workspace_cron(f"pytest-A7-遗留表达式-{uuid.uuid4().hex[:6]}")

    healthy = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": f"pytest-A7-正常表达式-{uuid.uuid4().hex[:6]}",
            "cron": "0 9 * * mon",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert healthy.status_code == 200, healthy.text
    healthy_id = healthy.json()["data"]["id"]

    items = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers).json()["data"][
        "items"
    ]
    by_id = {row["id"]: row for row in items}
    assert by_id[skipped_id]["needs_review"] is True
    assert by_id[legacy_id]["needs_review"] is True
    assert by_id[healthy_id]["needs_review"] is False


def _insert_train_schedules() -> dict[str, int]:
    """直接落三条定时训练计划：遗留表达式 / 空表达式 / 正常表达式。"""

    async def _run() -> dict[str, int]:
        from app.core.database import async_db_session
        from app.plugin.module_train.schedule_model import TrainScheduleModel

        rows = {
            "legacy": TrainScheduleModel(
                name="pytest-A7-训练-遗留",
                dataset_id=1,
                framework="torchkiln",
                trigger="cron",
                trigger_args="0 0 9 L * *",
            ),
            "empty": TrainScheduleModel(
                name="pytest-A7-训练-空",
                dataset_id=1,
                framework="torchkiln",
                trigger="cron",
                trigger_args=None,
            ),
            "healthy": TrainScheduleModel(
                name="pytest-A7-训练-正常",
                dataset_id=1,
                framework="torchkiln",
                trigger="cron",
                trigger_args="0 9 * * mon",
            ),
        }
        async with async_db_session.begin() as db:
            db.add_all(list(rows.values()))
            await db.flush()
            return {key: row.id for key, row in rows.items()}

    return asyncio.run(_run())


def test_train_schedule_list_flags_both_kinds_of_rows(test_client, auth_headers):
    ids = _insert_train_schedules()
    data = test_client.get("/api/v1/train/schedule/list", headers=auth_headers).json()["data"]
    by_id = {row["id"]: row for row in data}
    assert by_id[ids["legacy"]]["needs_review"] is True
    assert by_id[ids["empty"]]["needs_review"] is True
    assert by_id[ids["healthy"]]["needs_review"] is False


def _insert_task_nodes() -> dict[str, int]:
    """直接落两个定时任务节点：遗留 Quartz 表达式 / 立即执行（`now` 无参数）。"""

    async def _run() -> dict[str, int]:
        from app.core.database import async_db_session
        from app.plugin.module_task.cronjob.node.model import NodeModel

        suffix = uuid.uuid4().hex[:8]
        rows = {
            "legacy": NodeModel(
                name="pytest-A7-节点-遗留",
                code=f"a7_legacy_{suffix}",
                func="print('a7 legacy')",
                trigger="cron",
                trigger_args="0 0 9 L * *",
            ),
            "now": NodeModel(
                name="pytest-A7-节点-立即",
                code=f"a7_now_{suffix}",
                func="print('a7 now')",
                trigger="now",
                trigger_args=None,
            ),
        }
        async with async_db_session.begin() as db:
            db.add_all(list(rows.values()))
            await db.flush()
            return {key: row.id for key, row in rows.items()}

    return asyncio.run(_run())


def test_task_node_list_flags_legacy_but_not_now(test_client, auth_headers):
    """节点列表：遗留表达式标 `needs_review`；`now` 无参数是契约，不误标。"""
    ids = _insert_task_nodes()
    data = test_client.get("/api/v1/task/cronjob/node/list", headers=auth_headers).json()["data"]
    by_id = {row["id"]: row for row in data["items"]}
    assert by_id[ids["legacy"]]["needs_review"] is True
    assert by_id[ids["now"]]["needs_review"] is False
