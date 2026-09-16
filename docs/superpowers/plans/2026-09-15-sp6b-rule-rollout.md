# SP6-b 规则灰度实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让告警规则支持「生效时间段 + 比例灰度 + 相机白/黑名单」，并保证灰度跳过可解释、缺省零行为变化。

**Architecture:** `AlarmRule` 新增 `rollout` JSONB；新增纯函数 `rule_active_now(...)` 在**规则层**做 gating（不改叶子求值器）；`process_detection_callback` 遍历规则时先 gating、跳过者不观测不评估不落库。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic；Vue 3 + Element Plus + TypeScript + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-15-sp6b-rule-rollout-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；格式 `feat(video): …` / `feat(ui): …` / `test(ui): …`。
- 只 `git add` 本任务列出文件；**禁止 `git add -A`**。
- 后端：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增后端依赖**。
- 前端：`pnpm run type-check` 0 新增；禁止新增依赖。
- **缺省零行为变化**：`rollout` 缺省 `{}` → 始终生效。
- gating 只改**规则层**；`_match_conditions` / `explain_conditions` / 叶子契约**不得改动**。
- 分桶必须用 `zlib.crc32`（跨进程稳定），**禁止** Python 内置 `hash()`。
- 非法/缺失灰度配置 **fail-open**（按生效处理），避免规则静默失效。

---

### Task 1: 数据模型 + schema + 校验 + 迁移

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/model.py`
- Modify: `backend/app/api/v1/module_video/alarm/schema.py`
- Modify: `backend/app/api/v1/module_video/alarm/service.py`
- Create: Alembic 迁移（CLI 生成）
- Test: `backend/tests/test_rule_rollout_config.py`

**Interfaces:**
- Produces: `AlarmRuleModel.rollout: dict`（默认 `{}`）；`rollout` 校验（percent 0-100、名单为相机 id 列表、白黑互斥）。

- [ ] **Step 1: 写失败测试**

```python
"""规则灰度配置校验测试。"""
import pytest


def _base(**extra):
    body = {"name": "灰度规则", "alarm_type": "DET_ZONE", "severity": "WARNING", "status": True,
            "camera_id": 1}
    body.update(extra)
    return body


@pytest.mark.parametrize("rollout", [
    {"percent": -1}, {"percent": 101}, {"percent": "x"},
    {"whitelist": [1], "blacklist": [1]},          # 交集非空
    {"whitelist": "1"},                            # 非列表
])
def test_invalid_rollout_rejected(test_client, auth_headers, rollout):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers,
                            json=_base(rollout=rollout))
    assert resp.status_code == 400


def test_valid_rollout_accepted_and_persisted(test_client, auth_headers):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers,
                            json=_base(rollout={"percent": 30, "whitelist": [2], "blacklist": [3]}))
    assert resp.status_code == 200, resp.text
    rid = resp.json()["data"]["id"]
    row = next(x for x in test_client.get("/api/v1/video/alarm/rule/list",
                                          headers=auth_headers).json()["data"]["items"] if x["id"] == rid)
    assert row["rollout"] == {"percent": 30, "whitelist": [2], "blacklist": [3]}


def test_default_rollout_is_empty(test_client, auth_headers):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json=_base())
    assert resp.json()["data"]["rollout"] == {}
```

> 视频路由限流 5/10s：参数化用例需错开（变 `X-Forwarded-For`）或合并请求，避免 429。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

- `alarm/model.py` 新增：

```python
    rollout: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}",
                                          comment="灰度配置: {percent, whitelist, blacklist}")
```

- `alarm/schema.py`：`AlarmRuleCreate/Update/Out` 增加 `rollout: dict = Field(default_factory=dict, description="灰度配置")`。
- `alarm/service.py` 新增校验（与既有作用域校验同一处调用，按**合并后结果态**）：

```python
def _validate_rollout(rollout: dict | None) -> None:
    """灰度配置校验：percent 0-100；名单为相机 id 列表且互斥。非法 → 400。"""
    if not rollout:
        return
    if not isinstance(rollout, dict):
        raise CustomException(msg="灰度配置非法：必须为对象")
    percent = rollout.get("percent")
    if percent is not None:
        if isinstance(percent, bool) or not isinstance(percent, int) or not (0 <= percent <= 100):
            raise CustomException(msg="灰度配置非法：percent 必须为 0-100 的整数")
    wl, bl = rollout.get("whitelist"), rollout.get("blacklist")
    for name, lst in (("whitelist", wl), ("blacklist", bl)):
        if lst is None:
            continue
        if not isinstance(lst, list) or any(
            isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in lst
        ):
            raise CustomException(msg=f"灰度配置非法：{name} 必须为相机 id 正整数列表")
    if wl and bl and set(wl) & set(bl):
        raise CustomException(msg="灰度配置非法：白名单与黑名单不得同时包含同一相机")
```

- [ ] **Step 4: 生成并执行迁移**

```bash
cd backend && uv run main.py revision --env=dev && uv run main.py upgrade --env=dev
```
确认迁移只新增 `video_alarm_rules.rollout`（JSONB，`server_default '{}'`）。

- [ ] **Step 5: 测试 + 全量回归** → 聚焦通过；`uv run pytest -q` 全绿
- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/alarm/model.py backend/app/api/v1/module_video/alarm/schema.py backend/app/api/v1/module_video/alarm/service.py backend/tests/test_rule_rollout_config.py backend/alembic/versions/<新迁移>.py
git commit -m "feat(video): 告警规则新增灰度配置 rollout（百分比/白黑名单）"
```

---

### Task 2: gating 纯函数 `rule_active_now`

**Files:**
- Create: `backend/app/api/v1/module_video/inference/gating.py`
- Test: `backend/tests/test_rule_active_now.py`

**Interfaces:**
- Produces: `rule_active_now(schedule, rollout, camera_id, now, *, rule_id=None) -> tuple[bool, str]`

- [ ] **Step 1: 写失败测试**（覆盖 spec §3.2 全部原因分支）

```python
"""规则灰度 gating 纯函数测试。"""
from app.api.v1.module_video.inference.gating import rule_active_now

NOW = 1_800_000_000.0   # 固定时间，避免 wall clock


def test_default_is_active():
    assert rule_active_now(None, None, 1, NOW, rule_id=1) == (True, "all")
    assert rule_active_now({}, {}, 1, NOW, rule_id=1) == (True, "all")


def test_blacklist_skips_and_whitelist_forces():
    r = {"percent": 0, "whitelist": [7], "blacklist": [8]}
    assert rule_active_now(None, r, 8, NOW, rule_id=1)[0] is False      # 黑名单
    assert rule_active_now(None, r, 7, NOW, rule_id=1) == (True, "whitelist")  # 白名单忽略 percent=0
    assert rule_active_now(None, r, 9, NOW, rule_id=1)[0] is False      # percent=0


def test_percent_bounds():
    assert rule_active_now(None, {"percent": 100}, 5, NOW, rule_id=1) == (True, "rollout_all")
    assert rule_active_now(None, {"percent": 0}, 5, NOW, rule_id=1) == (False, "rollout_zero")


def test_bucket_is_stable_and_deterministic():
    r = {"percent": 50}
    first = rule_active_now(None, r, 42, NOW, rule_id=9)
    for _ in range(20):
        assert rule_active_now(None, r, 42, NOW, rule_id=9) == first
    # 不同 rule_id 的分桶相互独立（至少一个不同）
    pairs = {(rule_active_now(None, r, c, NOW, rule_id=rid)[0])
             for rid in range(5) for c in range(20)}
    assert pairs == {True, False}


def test_schedule_window_gates():
    # 全天（空 slots）生效；不在窗口 → 跳过
    assert rule_active_now({}, None, 1, NOW, rule_id=1)[0] is True
    assert rule_active_now(None, None, 1, NOW, rule_id=1)[0] is True


def test_invalid_inputs_fail_open():
    for bad in ({"percent": "x"}, {"percent": -5}, {"percent": 999},
                {"whitelist": "1"}, "not-a-dict", 123):
        assert rule_active_now(None, bad, 1, NOW, rule_id=1)[0] is True
```

> 时间段用例：需按既有 schedule 结构（`[{day,start_hour,end_hour}]`）构造"当前必定不在窗口"的配置（用 `now` 推导的 `day/hour` 取反）。实现者先阅读 `edge/orchestrator.py` 中 schedule 的产出与边缘 `aistation::Schedule` 的解析，**云端 gating 与边缘语义保持一致**。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
"""规则灰度 gating：时间段 → 黑名单 → 白名单 → 比例（稳定哈希分桶）。

设计要点：任何非法/缺失输入一律 fail-open（视为生效），避免灰度配置错误导致
规则静默失效；分桶用 zlib.crc32（跨进程稳定），不可用 Python 内置 hash()。
"""
import logging
import zlib
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _schedule_active(schedule, now: float) -> bool:
    """时间段是否命中；空/非法视为全天生效（fail-open）。"""
    # 复用既有云端/边缘一致的 schedule 结构 [{day, start_hour, end_hour}]
    ...


def _bucket_hit(rule_id, camera_id, percent: int) -> bool:
    key = f"{rule_id}:{camera_id}".encode()
    return (zlib.crc32(key) % 100) < percent


def rule_active_now(schedule, rollout, camera_id, now, *, rule_id=None) -> tuple[bool, str]:
    ...
```

- [ ] **Step 4: 测试** → 通过
- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/inference/gating.py backend/tests/test_rule_active_now.py
git commit -m "feat(video): 规则灰度 gating 纯函数（时间段/白黑名单/比例分桶）"
```

---

### Task 3: 接入规则评估

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_rule_rollout_eval.py`

**Interfaces:**
- Consumes: `rule_active_now`（Task 2）。
- Produces：被灰度跳过的规则不评估；返回体新增 `rule_skipped_list: [{"rule_id","reason"}]`。

- [ ] **Step 1: 写失败测试**（复用 `test_temporal_leaves_e2e.py` 的假 DB 手法，本文件专用最小假会话）

```python
"""灰度接入评估链路的集成测试。"""
# 用例：
# 1) percent=0 的规则 → 不产生告警，返回 rule_skipped_list 含该规则与 reason="rollout_zero"
# 2) 同相机另一条 percent=100 规则 → 正常告警（互不影响）
# 3) 白名单相机在 percent=0 下仍告警（whitelist 强制）
# 4) 组规则按相机分桶：组内相机 A（命中桶）产生告警、相机 B（未命中）不产生
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

在规则遍历处（SP6-a 引入的循环）插入 gating：

```python
        active, reason = rule_active_now(
            getattr(rule, "schedule_json", None), getattr(rule, "rollout", None),
            camera_id, event_now, rule_id=rule.id,
        )
        if not active:
            log.info(f"规则 {rule.id} 灰度跳过（{reason}）: camera={camera_id}")
            skipped.append({"rule_id": rule.id, "reason": reason})
            continue
```

并把 `skipped` 放入返回体 `rule_skipped_list`。**不观测、不评估、不落库**被跳过的规则。

- [ ] **Step 4: 测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_rule_rollout_eval.py -q` → 通过
Run: `cd backend && uv run pytest -q` → 全绿（缺省 config 下行为不变）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/tests/test_rule_rollout_eval.py
git commit -m "feat(video): 规则评估接入灰度 gating（跳过不观测不落库）"
```

---

### Task 4: 前端灰度配置区块

**Files:**
- Modify: `frontend/src/views/module_video/alarm/components/RuleEditor.vue`
- Modify: `frontend/src/views/module_video/alarm/index.vue`
- Modify: `frontend/src/api/module_video/alarm.ts`

- [ ] **Step 1: RuleEditor 增加「灰度」区块**

- 生效时间段：参考 `frontend/src/components/Train/SchedulePanel.vue` 的既有交互与数据结构（**复用其组件或同一数据结构**，不要自造新的 schedule 编辑器）；空=全天。
- 比例：`el-slider` 0-100 + 数值显示（0=不生效，100=全量）。
- 白/黑名单：两个 `el-select multiple`（相机列表）；提交前校验交集为空（有交集则提示且不提交）。
- v-model 负载增加 `rollout: {percent, whitelist, blacklist}` 与 `schedule_json`。

- [ ] **Step 2: 列表/详情摘要**

`index.vue` 展示灰度摘要，如「30%」「白名单 3 台」「09:00-18:00」；无灰度则不显示。

- [ ] **Step 3: 校验** → `cd frontend && pnpm run type-check`（0 新增）；仅本任务文件 lint 干净
- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/module_video/alarm.ts frontend/src/views/module_video/alarm/components/RuleEditor.vue frontend/src/views/module_video/alarm/index.vue
git commit -m "feat(ui): 规则编辑器支持灰度配置（时间段/比例/白黑名单）"
```

---

### Task 5: e2e + 视觉核对

**Files:** `frontend/e2e/sp6b-rule-rollout.spec.ts`、`docs/superpowers/runbooks/sp6b-visual.md` + 截图

- [ ] 配置灰度（比例 30 + 白名单 1 台 + 时间段）→ 保存 → 列表摘要可见 → 重开回填一致；`pnpm run e2e -- sp6b-rule-rollout` 通过；截图 + `vision-recognition` 核对。
- [ ] 提交 `test(ui): 规则灰度配置 e2e 与视觉核对`

---

### Task 6: 真机对照

- [ ] 同相机两条规则：A=`percent=0`（不告警）、B=`percent=100`（告警）；再验白名单强制（`percent=0` + 白名单含该相机 → 告警）；
- [ ] 断言 `rule_skipped_list` 含 A 且 reason 正确；还原环境；结论写入 `.superpowers/sdd/sp6b-task-6-report.md`。

---

### Task 7: 总回归

- [ ] 后端 `uv run pytest -q` + `uv run ruff check`；前端 `pnpm run type-check && pnpm run lint && pnpm run e2e`（环境性 429 抖动需隔离复跑确认）；
- [ ] 报告写入 `.superpowers/sdd/sp6b-task-7-report.md`。

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 `rollout` 列 + 校验 + 迁移 | Task 1 |
| §3.2 gating 纯函数（优先级/原因/`crc32`/fail-open） | Task 2 |
| §3.3 接入评估（跳过不观测不落库 + `rule_skipped_list`） | Task 3 |
| §3.4 前端灰度区块 + 摘要 | Task 4 |
| §3.5 视觉约束与截图核对 | Task 5 |
| §4 验收（单测/e2e/截图/真机/回归） | Task 1-3 / 5 / 6 / 7 |
| §5 风险（静默失效/哈希稳定/组规则语义/时间段对齐/缺省不变） | Task 2（fail-open + 稳定性测试）、Task 1（缺省 `{}`）、Task 2（与边缘 schedule 对齐）、Task 3（全量回归） |
| §6 兼容性（缺省不变、schedule_json 死字段修正提示） | Task 1（默认 `{}`）+ 发布说明提示 |

**类型一致性：** `rule_active_now(schedule, rollout, camera_id, now, *, rule_id=None)`（Task 2 定义）与 Task 3 调用一致；`rollout` 键 `percent/whitelist/blacklist`（Task 1 schema、Task 2 读取、Task 4 前端提交）三处一致；`rule_skipped_list` 元素 `{"rule_id","reason"}`（Task 3 定义）与 Task 6 断言一致。

**占位符扫描：** Task 1/3 含完整关键代码；Task 2 的函数骨架给出签名、原因取值与关键实现（`crc32` 分桶、fail-open），并要求先读 `edge/orchestrator.py` 对齐 schedule 语义（非 TODO，而是明确的调研前置）；Task 4-7 含契约、命令与验收标准。
