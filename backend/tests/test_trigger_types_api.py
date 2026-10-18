"""四种触发类型在三处写入口真正可用（Task A8，修 C4 发现的接口层缺口）。

**缺口**：前端（工作台 / 工作流 / 训练）已能产出统一契约的 `trigger` + `trigger_args`
（cron / interval / date / now），但三处请求 schema 只认旧的 `cron` / `cron_expr`——
非 cron 类型在**启用**时被 400（「请先配置触发时间」），在**未启用**时被静默丢弃
（Pydantic 默认 `extra='ignore'`，值根本进不了 service）。

本文件断言：

1. 四类型逐一写入 → 200；回读 `trigger` 与 `trigger_args` 形态正确
   （interval 反序列化回对象、date 为时间串、now 为 null）；
2. **字段优先规则**：`trigger` 显式提供时以它为准，非 cron 类型提交的 `cron: ""` /
   `cron_expr: ""` 不得被误判成「空表达式 + 启用」；
3. 回读新增的 `trigger_describe`（统一层人话描述，供列表「描述」列直接展示）；
4. 「空表达式 + 启用 → 400 / 空 + 禁用 → 允许」这条已落地语义**不回退**。

需要应用（`test_client`）的用例在 ``PYTEST_NO_APP=1`` 快速模式下自动 skip。
"""

import uuid

# `ap_scheduler` 与 `app.plugin.module_task` 存在**既有**循环导入（B1 已记录）：
# 先 import `module_task` 再 import `ap_scheduler` 才能成功。这里固定顺序。
import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
from app.core.ap_scheduler import SchedulerUtil
from app.plugin.module_ai.workflow.service import _job_key as _workflow_job_key
from app.plugin.module_ai.workspace.service import _job_key as _workspace_job_key
from app.plugin.module_train.schedule_service import train_schedule_job_key

#: 四类型用例：(trigger, 提交的 trigger_args, 回读期望)
#: interval 落库为 JSON 串、回读**反序列化回对象**（补齐缺省字段）；now 无参数（null）。
TRIGGER_CASES = [
    ("cron", "0 9 * * mon", "0 9 * * mon"),
    ("interval", {"hours": 2}, {"weeks": 0, "days": 0, "hours": 2, "minutes": 0, "seconds": 0}),
    ("date", "2999-01-01 09:00:00", "2999-01-01 09:00:00"),
    ("now", None, None),
]

#: 非 cron 类型时前端仍会带上旧字段（空串）：`trigger` 优先，空串不得被当成「空表达式」
_LEGACY_EMPTY = ""


def _name(tag: str) -> str:
    return f"pytest-A8-{tag}-{uuid.uuid4().hex[:6]}"


def _create_workflow(test_client, auth_headers) -> int:
    """建一个最小可运行的工作流（start → end）。"""
    r = test_client.post(
        "/api/v1/ai/workflows/create",
        json={
            "name": _name("工作流"),
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


# ============================================================ 工作流：PUT /{id}/schedule


def test_workflow_schedule_accepts_four_trigger_types(test_client, auth_headers):
    """四种触发类型都能保存并原样回读（修 C4 发现的接口缺口）。"""
    wid = _create_workflow(test_client, auth_headers)
    url = f"/api/v1/ai/workflows/{wid}/schedule"
    try:
        for trigger, args, expect in TRIGGER_CASES:
            payload = {
                "trigger": trigger,
                "trigger_args": args,
                # 兼容字段：仅 cron 类型带表达式，其余类型带空串（C4 前端的行为）
                "cron": args if trigger == "cron" else _LEGACY_EMPTY,
                "enabled": True,
            }
            r = test_client.put(url, json=payload, headers=auth_headers)
            assert r.status_code == 200, (trigger, r.text)

            d = test_client.get(url, headers=auth_headers).json()["data"]
            assert d["trigger"] == trigger, (trigger, d)
            assert d["trigger_args"] == expect, (trigger, d["trigger_args"])
            assert d["trigger_describe"], (trigger, d)  # 新增：统一层人话描述
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=[wid], headers=auth_headers
        )
        SchedulerUtil.remove_business_job(_workflow_job_key(wid))


def test_workflow_schedule_empty_trigger_semantics_unchanged(test_client, auth_headers):
    """空表达式语义不回退：`trigger` 与旧字段都缺省 + 启用 → 400；+ 禁用 → 允许。"""
    from app.plugin.module_ai.workflow.service import _EMPTY_TRIGGER_MSG

    wid = _create_workflow(test_client, auth_headers)
    url = f"/api/v1/ai/workflows/{wid}/schedule"
    try:
        on = test_client.put(url, json={"enabled": True}, headers=auth_headers)
        assert on.status_code == 400, on.text
        assert on.json()["msg"] == _EMPTY_TRIGGER_MSG

        off = test_client.put(url, json={"enabled": False}, headers=auth_headers)
        assert off.status_code == 200, off.text
        d = off.json()["data"]
        assert d["enabled"] is False
        assert d["next_run_time"] is None
        assert not d["trigger_describe"], d  # 未配置 → 无法描述

        # 显式提交「非法的 cron 参数」：原因来自统一层（可读），而不是 500
        bad = test_client.put(
            url,
            json={"trigger": "cron", "trigger_args": "0 9 * * 5-1", "enabled": True},
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text
        assert "跨周" in bad.json()["msg"]
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=[wid], headers=auth_headers
        )
        SchedulerUtil.remove_business_job(_workflow_job_key(wid))


# ============================================================ 工作台：POST /cron/create


def test_workspace_cron_accepts_four_trigger_types(test_client, auth_headers):
    """工作台定时任务：四类型都能新建并原样回读（非 cron 类型带的 `cron: ""` 不误报 400）。"""
    created: list[int] = []
    try:
        for trigger, args, expect in TRIGGER_CASES:
            r = test_client.post(
                "/api/v1/ai/workspace/cron/create",
                json={
                    "name": _name("工作台"),
                    "description": "",
                    "trigger": trigger,
                    "trigger_args": args,
                    # 兼容字段：非 cron 类型前端仍会带空串（旧接口语义）
                    "cron": args if trigger == "cron" else "",
                    "target_type": "workflow",
                    "target_id": 0,
                    "enabled": True,
                },
                headers=auth_headers,
            )
            assert r.status_code == 200, (trigger, r.text)
            cron_id = r.json()["data"]["id"]
            created.append(cron_id)

            items = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers).json()[
                "data"
            ]["items"]
            row = next(x for x in items if x["id"] == cron_id)
            assert row["trigger"] == trigger, (trigger, row)
            assert row["trigger_args"] == expect, (trigger, row["trigger_args"])
            assert row["trigger_describe"], (trigger, row)
            # 非 cron 类型的兼容字段必须为空（旧前端不会把 interval 误读成 cron）
            assert row["cron"] == (expect if trigger == "cron" else ""), (trigger, row)
    finally:
        for cron_id in created:
            test_client.request(
                "DELETE",
                "/api/v1/ai/workspace/cron/delete",
                json=cron_id,
                headers=auth_headers,
            )
            SchedulerUtil.remove_business_job(_workspace_job_key(cron_id))


def test_workspace_cron_update_accepts_trigger_fields(test_client, auth_headers):
    """工作台编辑：只传 `trigger` + `trigger_args`（不带旧 `cron`）也能改触发配置。"""
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": _name("工作台编辑"),
            "trigger": "cron",
            "trigger_args": "0 9 * * mon",
            "cron": "0 9 * * mon",
            "target_type": "workflow",
            "target_id": 0,
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    cron_id = r.json()["data"]["id"]
    try:
        upd = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cron_id}",
            json={"trigger": "interval", "trigger_args": {"minutes": 30}, "cron": ""},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        d = upd.json()["data"]
        assert d["trigger"] == "interval", d
        assert d["trigger_args"] == {
            "weeks": 0,
            "days": 0,
            "hours": 0,
            "minutes": 30,
            "seconds": 0,
        }, d
        assert d["trigger_describe"], d

        # `trigger` 显式提供时以它为准：即便同时带了旧字段 `cron: ""`（非 cron 类型前端的行为），
        # 也不得被判成「空表达式」（400）或把触发配置改回 cron
        upd2 = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cron_id}",
            json={"trigger": "interval", "trigger_args": {"hours": 1}, "cron": "", "enabled": True},
            headers=auth_headers,
        )
        assert upd2.status_code == 200, upd2.text
        d2 = upd2.json()["data"]
        assert d2["trigger"] == "interval" and d2["trigger_args"]["hours"] == 1, d2
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cron_id, headers=auth_headers
        )
        SchedulerUtil.remove_business_job(_workspace_job_key(cron_id))


# ============================================================ 训练：POST /schedule/create


def test_train_schedule_accepts_four_trigger_types(test_client, auth_headers):
    """定时训练计划：四类型都能新建并原样回读（非 cron 类型带的 `cron_expr: ""` 不误报 400）。"""
    created: list[int] = []
    try:
        for trigger, args, expect in TRIGGER_CASES:
            r = test_client.post(
                "/api/v1/train/schedule/create",
                json={
                    "name": _name("训练"),
                    "dataset_id": 1,
                    "framework": "torchkiln",
                    "hyperparams": {},
                    "trigger": trigger,
                    "trigger_args": args,
                    # 兼容字段：非 cron 类型前端仍会带空串
                    "cron_expr": args if trigger == "cron" else "",
                },
                headers=auth_headers,
            )
            assert r.status_code == 200, (trigger, r.text)
            sid = r.json()["data"]["id"]
            created.append(sid)

            rows = test_client.get("/api/v1/train/schedule/list", headers=auth_headers).json()[
                "data"
            ]
            row = next(x for x in rows if x["id"] == sid)
            assert row["trigger"] == trigger, (trigger, row)
            assert row["trigger_args"] == expect, (trigger, row["trigger_args"])
            assert row["trigger_describe"], (trigger, row)
            # 兼容字段：仅 cron 有值
            assert row["cron_expr"] == (expect if trigger == "cron" else ""), (trigger, row)
    finally:
        if created:
            test_client.request(
                "DELETE", "/api/v1/train/schedule/delete", json=created, headers=auth_headers
            )
        for sid in created:
            SchedulerUtil.remove_business_job(train_schedule_job_key(sid))


# ============================================================ A8 修正轮 I-1：`now` 行的部分更新


def _create_workspace_now_cron(test_client, auth_headers) -> int:
    """建一条 `trigger="now"`（立即执行）的启用中定时任务，返回 id。"""
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": _name("now 部分更新"),
            "description": "",
            "trigger": "now",
            "trigger_args": None,
            # 兼容字段：非 cron 类型前端仍会带空串
            "cron": "",
            "target_type": "workflow",
            "target_id": 0,
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    created = r.json()["data"]
    assert created["trigger"] == "now" and created["trigger_args"] is None, created
    return created["id"]


def test_workspace_cron_now_row_partial_update_keeps_trigger(test_client, auth_headers):
    """I-1：`now` 行（`trigger_args` 落 NULL）**只改 name** 必须 200，且触发配置不变。

    `now` 按契约**本就没有参数**，`trigger_args` 为 NULL ≠「未配置」；旧守卫按「请求后的行状态」
    判定（`row.enabled and not row.trigger_args`），会把这种部分更新误报成 400「请先配置触发时间」。
    """
    from app.plugin.module_ai.workspace.service import _EMPTY_TRIGGER_MSG

    cron_id = _create_workspace_now_cron(test_client, auth_headers)
    try:
        new_name = _name("now 部分更新改后")
        upd = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cron_id}",
            json={"name": new_name},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["msg"] != _EMPTY_TRIGGER_MSG
        d = upd.json()["data"]
        assert d["name"] == new_name, d
        # 触发配置不被部分更新清掉/改掉
        assert d["trigger"] == "now", d
        assert d["trigger_args"] is None, d
        assert d["trigger_describe"] == "保存后立即执行一次", d
        assert d["enabled"] is True, d

        # 显式切「启用」同样不得被误拦：`now` 不是「未配置」
        re_enable = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cron_id}",
            json={"enabled": True},
            headers=auth_headers,
        )
        assert re_enable.status_code == 200, re_enable.text
        d2 = re_enable.json()["data"]
        assert d2["trigger"] == "now" and d2["trigger_args"] is None, d2

        # 守卫本身不回退：显式提交「cron + 空参数 + 启用」仍被 400 挡下
        empty_on = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{cron_id}",
            json={"trigger": "cron", "trigger_args": "", "cron": "", "enabled": True},
            headers=auth_headers,
        )
        assert empty_on.status_code == 400, empty_on.text
        assert empty_on.json()["msg"] == _EMPTY_TRIGGER_MSG, empty_on.text
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workspace/cron/delete", json=cron_id, headers=auth_headers
        )
        SchedulerUtil.remove_business_job(_workspace_job_key(cron_id))


def test_train_schedule_rejects_enabled_empty_trigger(test_client, auth_headers):
    """定时训练计划默认启用：`trigger` 与旧字段都缺省 → 可读 400（不回退已落地语义）。"""
    from app.plugin.module_train.schedule_service import _EMPTY_TRIGGER_MSG

    r = test_client.post(
        "/api/v1/train/schedule/create",
        json={
            "name": _name("训练空表达式"),
            "dataset_id": 1,
            "framework": "torchkiln",
            "hyperparams": {},
            "trigger": "cron",
            "trigger_args": "",
            "cron_expr": "",
        },
        headers=auth_headers,
    )
    # `trigger` 显式提供了 cron 但参数为空 → 400；空表达式一律用统一的「请先配置触发时间」文案
    # （与三处已落地的空表达式用例同一口径），且不落库
    assert r.status_code == 400, r.text
    assert r.json()["msg"] == _EMPTY_TRIGGER_MSG, r.text

    r2 = test_client.post(
        "/api/v1/train/schedule/create",
        json={
            "name": _name("训练缺省触发"),
            "dataset_id": 1,
            "framework": "torchkiln",
            "hyperparams": {},
        },
        headers=auth_headers,
    )
    assert r2.status_code == 400, r2.text
    assert r2.json()["msg"] == _EMPTY_TRIGGER_MSG
