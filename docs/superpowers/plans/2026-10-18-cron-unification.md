# 定时任务统一（触发类型 / cron 口径 / 调度入口 / UI）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把全平台"定时任务"统一成一套触发模型（cron/间隔/单次/立即）、一套 5 段标准 cron 口径、一套中心调度、一个 `TriggerEditor` UI。

**Architecture:** 新增统一层 `app/utils/trigger_util.py::TriggerUtil`（规范化/校验/描述/触发器构造/下次运行时间，全部按触发类型分派，校验与调度同源）；`app/core/ap_scheduler.py` 成为唯一调度入口并新增"业务作业"注册 API；AI 与训练的自建轮询删除、改注册到中心 APScheduler；前端新增 `TriggerEditor` 组件替换四处旧输入。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + APScheduler 3.11（`AsyncIOScheduler` + `SQLAlchemyJobStore`）+ Alembic（手写迁移）；Vue 3 + Element Plus + `@vue-js-cron/element-plus` 3.2.2。

**Spec:** `docs/superpowers/specs/2026-10-18-cron-unification-design.md`

## Global Constraints

- **cron 唯一格式**：5 段标准 crontab `分 时 日 月 周`；周字段 `0`/`7`=周日，接受 `mon…sun`（大小写不敏感）。
- **周字段映射**（交 APScheduler 前必须转换，修 D1）：`0|7|sun→sun`、`1|mon→mon`、`2|tue`、`3|wed`、`4|thu`、`5|fri`、`6|sat`；**区间展开为显式名称列表**（`1-5→mon,tue,wed,thu,fri`、`0-6→sun,mon,tue,wed,thu,fri,sat`）；列表 `1,3→mon,wed`。
- **周字段不支持 `/` 步长**（`*/2`、`mon/2` 一律报错）；**跨周区间**（`start > end`，如 `fri-mon`、`6-0`）一律报错并提示改用列表。
- **必须判非法**：`L`、`15W`、`1#2`、`?`、7 段（带年）、6 段（**含秒位为 0**——唯一合法形式就是 5 段；6 段秒位为 0 的宽容转换只存在于迁移路径 `normalize_legacy`）。
- **必须判合法**：`0 9 * * 7`（标准 crontab 的周日）。
- **触发类型**：`cron` / `interval` / `date` / `now`，四个入口（系统定时任务节点、AI 工作台、AI 工作流、训练调度）全部支持。
- **interval 参数**：JSON `{"weeks":0,"days":0,"hours":2,"minutes":30,"seconds":0}`（全 0 → 报错）。
- **date 参数**：`"YYYY-MM-DD HH:mm:ss"`（过去时间 → 报错）。
- **now 参数**：`null` → 注册 `DateTrigger(now + 2s)` 一次性作业。
- **时区**：一律 `Asia/Shanghai`（与中心调度器一致）；`date` 按该时区解释。
- **调度参数**：业务作业 `coalesce=True`、`misfire_grace_time=60`、`max_instances=1`。
- **迁移不做静默语义改写**：无法等值转换的旧值 → 跳过并写迁移日志。
- **UI 约束**：只用 Element Plus 原生组件 + `--el-*` 变量；不自造主题外壳；正文 14px / 次要 12px；弹窗宽度 500/600px 且位于页面根元素内（单根）；删除/停用二次确认。
- **不引入** `cronstrue`（描述由后端 `TriggerUtil.describe` 产出）。
- **测试命令**：单文件 `backend/.venv/Scripts/python.exe -m pytest tests/test_x.py -q`；提交前全量 `uv run pytest -q -n 4`。
- **提交信息**中文，格式 `fix(train): …` / `feat(ai): …`。

## Review Focus

规格没写、但用户一定会碰到的 5 类输入/场景（每类都在对应任务里加了测试）：

1. **旧 6 段秒位非 0 的数据迁移被跳过 → 任务静默停止**：必须在迁移日志里逐条记录，且列表接口把这类行标为"表达式需人工确认"，不能悄悄不跑（Task A6、A7）。
2. **单次(`date`)填了过去时间** → 必须报错（不能存下却不执行）；`now` 才是"立即执行"（Task A3）。
3. **间隔全 0**（`0 天 0 时 0 分 0 秒`）→ 必须报错，否则产生无效/死循环作业（Task A3）。
4. **删除或禁用任务后作业残留 → 幽灵触发**：`remove_business_job` / `sync_business_jobs` 必须幂等，删后 `scheduler.get_job(job_key)` 为 `None`（Task B1）。
5. **时区**：`date` 与 `cron` 必须按 `Asia/Shanghai` 解释，容器 TZ 不同时不得偏移（Task A2、A3）。

---

## 阶段 A：触发与 cron 口径统一

### Task A1: `TriggerUtil` 的 cron 规范化与校验

**Files:**
- Create: `backend/app/utils/trigger_util.py`
- Test: `backend/tests/test_trigger_util.py`

**Interfaces:**
- Produces: `TriggerUtil.normalize_cron(expr: str) -> str`、`TriggerUtil.validate_cron(expr: str) -> tuple[bool, str]`
  （返回 `(是否合法, 可读原因)`；合法时原因为 `""`）

- [ ] **Step 1: 写失败测试**

```python
import pytest

from app.utils.trigger_util import TriggerUtil


def test_normalize_cron_maps_weekday_numbers_to_names():
    assert TriggerUtil.normalize_cron("0 9 * * 1") == "0 9 * * mon"
    assert TriggerUtil.normalize_cron("0 9 * * 0") == "0 9 * * sun"
    assert TriggerUtil.normalize_cron("0 9 * * 7") == "0 9 * * sun"
    # 区间展开为显式列表（避免两套库对名称区间解释相反）
    assert TriggerUtil.normalize_cron("0 9 * * 1-5") == "0 9 * * mon,tue,wed,thu,fri"
    assert TriggerUtil.normalize_cron("0 9 * * 0-6") == "0 9 * * sun,mon,tue,wed,thu,fri,sat"
    # 7 与 0 同为周日：区间按原始数字 0..7 判定，展开后去重
    assert TriggerUtil.normalize_cron("0 9 * * 5-7") == "0 9 * * fri,sat,sun"
    assert TriggerUtil.normalize_cron("0 9 * * 0-7") == "0 9 * * sun,mon,tue,wed,thu,fri,sat"
    assert TriggerUtil.normalize_cron("0 9 * * 1,3,5") == "0 9 * * mon,wed,fri"
    assert TriggerUtil.normalize_cron("0  9   *  *  SUN ") == "0 9 * * sun"
    # 数值字段等值区间收敛为单值（与周字段 1-1→mon 对称）
    assert TriggerUtil.normalize_cron("0 9 5-5 * *") == "0 9 5 * *"


@pytest.mark.parametrize("expr", [
    "0 0 9 L * *", "0 0 9 15W * *", "0 0 9 * * 1#2", "0 0 9 ? * *",
    "0 0 9 * * * 2030", "30 * * * * *", "0 0 9 * * *",
    "0 9 * * */2", "0 9 * * mon/2", "0 9 * * 5-1", "0 9 * * 6-0",
    "0 9 * * 7-1", "0 9 * * fri-mon", "0 9 * * 5-5/1",
    "0 9 * * 9", "0 9 * *", "0 9 * * 1 2 3",
])
def test_validate_cron_rejects(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is False and reason


@pytest.mark.parametrize("expr", [
    "0 9 * * *", "0 9 * * 7", "*/15 * * * *", "0 9 1,15 * *", "0 9 * * mon-fri",
    "0 9 * * 5-7", "0 9 * * 0-7", "0 9 5-5 * *",
])
def test_validate_cron_accepts(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is True and reason == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q`
Expected: FAIL（`ModuleNotFoundError: app.utils.trigger_util`）

- [ ] **Step 3: 实现 `app/utils/trigger_util.py`**

`TriggerUtil` 用类方法；`_WEEKDAY_MAP` 覆盖 `0..7` 与 `mon..sun`（大小写不敏感）；字段校验按范围表
（分 0-59 / 时 0-23 / 日 1-31 / 月 1-12 / 周 `0-7|名称`），支持 `*`、`a-b`、`a,b,c`、`*/n`、`a-b/n`；
周字段出现 `/` 直接判非法并给出原因（"周字段不支持步长"）；`?`、`L`、`W`、`#`、7 段、6 段秒位非 0 各有专属原因文案。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/trigger_util.py backend/tests/test_trigger_util.py
git commit -m "feat(cron): TriggerUtil 统一 cron 规范化与校验（标准 5 段 + 周字段映射）"
```

### Task A2: cron 触发器构造、描述与下次运行时间（锁死 D1）

**Files:**
- Modify: `backend/app/utils/trigger_util.py`
- Test: `backend/tests/test_trigger_util.py`

**Interfaces:**
- Consumes: `TriggerUtil.normalize_cron` / `validate_cron`（Task A1）
- Produces: `TriggerUtil.to_cron_trigger(expr: str) -> CronTrigger`、`TriggerUtil.next_run(trigger: str, args, base=None) -> datetime | None`、`TriggerUtil.describe_cron(expr: str) -> str`

**A1 遗留小项（任务审查的 Minor 与 ⚠️，随本任务一并收口）:**
- ⚠️ **下游可构造性**（审查无法从 A1 diff 判断）：本任务必须加一条**扫描式测试**——A1 判合法的表达式（含 `5-7`/`0-7`/`5-5`/`mon-fri`/`1,3,5` 等，至少 20 条参数化）规范化后**必须能被 `CronTrigger` 构造且被 `croniter` 解析**（这同时取代 A1 报告里那个未入库的临时探针）。
- Minor：`validate_cron` 的宽 `except Exception` 收窄为只捕 `ValueError`（避免掩盖真实 bug），必要时 `logging.exception` 留痕。
- Minor：`*,mon` / `1,*` 这类**通配与列表混写**归一为 `*`（见规格 §4.1）。
- Minor：测试对关键反例（`L`/`15W`/`1#2`/`?`/7 段）断言**原因具体性**（`in` 断言关键短语），而不只是"原因非空"。
- Minor：补步长写法的覆盖：`5-5/1`（等值区间带步长 → 非法）、`1/2`（单值带步长 → 非法）。

- [ ] **Step 1: 写失败测试**（口径一致性 + 时区）

```python
from datetime import datetime

import pytest
from croniter import croniter

from app.utils.trigger_util import TriggerUtil

BASE = datetime(2026, 10, 18, 12, 0)  # 2026-10-18 是周日

#: 标准 crontab 语义下的期望下次触发（用于交叉验证，写死避免自证）
EXPECTED = {
    "0 9 * * 1": datetime(2026, 10, 19, 9, 0),
    "0 9 * * 5": datetime(2026, 10, 23, 9, 0),
    "0 9 * * 0": datetime(2026, 10, 25, 9, 0),
    "0 9 * * 7": datetime(2026, 10, 25, 9, 0),
    "0 9 * * 1-5": datetime(2026, 10, 19, 9, 0),
}


@pytest.mark.parametrize("expr", list(EXPECTED))
def test_next_run_is_standard_crontab_semantics(expr):
    """统一层的下次触发必须符合标准 crontab（锁死 D1：1=周一、0/7=周日）。"""
    ours = TriggerUtil.next_run("cron", expr, BASE)
    assert ours.replace(tzinfo=None) == EXPECTED[expr]


@pytest.mark.parametrize("expr", ["0 9 * * 1", "0 9 * * 5", "0 9 * * 1-5"])
def test_next_run_matches_croniter(expr):
    """交叉验证：与 croniter（标准 crontab 实现）同一时刻。"""
    ours = TriggerUtil.next_run("cron", expr, BASE)
    theirs = croniter(expr, BASE).get_next(datetime)
    assert ours.replace(tzinfo=None) == theirs


def test_cron_trigger_is_asia_shanghai():
    trig = TriggerUtil.to_cron_trigger("0 9 * * mon")
    assert str(trig.timezone) == "Asia/Shanghai"


def test_describe_cron_is_chinese():
    assert "周一" in TriggerUtil.describe_cron("0 9 * * 1")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q -k "next_run or describe or shanghai"`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 实现**

`to_cron_trigger` 用 `normalize_cron` 后的 5 段拆成 `minute/hour/day/month/day_of_week` 传给 `CronTrigger(...)`，
并显式 `timezone="Asia/Shanghai"`；`next_run` 内部用 `to_cron_trigger(...).get_next_fire_time(None, base or now)`；
`describe_cron` 输出中文（"每周一 09:00"、"每天 09:00"、"每小时第 15 分"），周期语义用简单查表实现，不引入新依赖。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/trigger_util.py backend/tests/test_trigger_util.py
git commit -m "feat(cron): 统一触发器构造/描述/下次运行时间（周字段按标准映射，锁死口径一致性）"
```

### Task A3: interval / date / now 三种触发类型

**Files:**
- Modify: `backend/app/utils/trigger_util.py`
- Test: `backend/tests/test_trigger_util.py`

**Interfaces:**
- Produces: `TriggerUtil.normalize(trigger: str, args) -> tuple[str, object]`、`TriggerUtil.validate(trigger: str, args) -> tuple[bool, str]`、`TriggerUtil.describe(trigger: str, args) -> str`、`TriggerUtil.to_trigger(trigger: str, args) -> BaseTrigger`（`trigger` 非法时抛 `CustomException`）

**A2 遗留裁决（随本任务一并落地）:**
- **永不触发的日/月组合判非法**：`validate("cron", ...)` 除语法外还要做**可调度性检查**——在有限窗口
  （如 4 年）内用 `to_trigger` 找不到下次触发即非法，原因写"该日/月组合永远不会触发（如 6 月 31 日）"。
  测试：`0 9 31 6 *`、`0 9 30 2 *` 判非法；`0 9 29 2 *`（闰年 2/29）判**合法**。
  同时 `next_run` **不得抛异常**：捕获后返回 `None`（A7 的预览据此给出"永不触发"提示，不 500）。
- **「日」与「周」同时为非 `*` 判非法**：APScheduler 取 AND、Vixie/croniter 取 OR（实测
  `0 9 1 * mon` 两边不同），实现间语义不一致。测试：`0 9 1 * mon` 判非法且原因含"只指定其一"；
  `0 9 1 * *`、`0 9 * * mon` 判合法。

- [ ] **Step 1: 写失败测试**（含 Review Focus 2、3、5）

```python
from datetime import datetime, timedelta

import pytest

from app.core.exceptions import CustomException
from app.utils.trigger_util import TriggerUtil


def test_interval_normalize_fills_defaults():
    t, args = TriggerUtil.normalize("interval", {"hours": 2, "minutes": 30})
    assert t == "interval"
    assert args == {"weeks": 0, "days": 0, "hours": 2, "minutes": 30, "seconds": 0}


def test_interval_all_zero_is_invalid():
    ok, reason = TriggerUtil.validate("interval", {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0})
    assert ok is False and "至少" in reason


def test_date_in_the_past_is_invalid():
    past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    ok, reason = TriggerUtil.validate("date", past)
    assert ok is False and "过去" in reason


def test_date_future_is_valid_and_asia_shanghai():
    future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    ok, reason = TriggerUtil.validate("date", future)
    assert ok is True and reason == ""
    trig = TriggerUtil.to_trigger("date", future)
    assert str(trig.timezone) == "Asia/Shanghai"


def test_now_has_no_args_and_fires_once_soon():
    ok, reason = TriggerUtil.validate("now", None)
    assert ok is True and reason == ""
    trig = TriggerUtil.to_trigger("now", None)
    assert trig.run_date - datetime.now(trig.run_date.tzinfo) < timedelta(seconds=10)


def test_unknown_trigger_type_raises():
    with pytest.raises(CustomException):
        TriggerUtil.to_trigger("weekly", None)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q -k "interval or date or now or unknown"`
Expected: FAIL

- [ ] **Step 3: 实现**

`normalize/validate/describe/to_trigger` 按 `trigger` 分派；`interval` 用 `IntervalTrigger(weeks, days, hours, minutes, seconds, timezone="Asia/Shanghai")`；
`date` 用 `DateTrigger(run_date=..., timezone="Asia/Shanghai")`，解析 `"%Y-%m-%d %H:%M:%S"`；
`now` 用 `DateTrigger(run_date=now+2s)`；`describe` 输出"每 2 小时 30 分一次"、"2026-10-20 09:00 执行一次"、"保存后立即执行一次"。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/trigger_util.py backend/tests/test_trigger_util.py
git commit -m "feat(cron): 统一 interval/date/now 三类触发的规范化、校验与构造"
```

### Task A4: `ap_scheduler` 改走统一层，删除旧校验器

**Files:**
- Modify: `backend/app/core/ap_scheduler.py`（`add_cron_job` 约 1010-1065、`add_interval_job` 约 1065-1105）
- Delete: `backend/app/utils/cron_util.py`；`backend/app/utils/time_util.py` 中的 `validate_cron_expression`
- Modify: `backend/app/plugin/module_task/cronjob/node/service.py:230`
- Test: `backend/tests/test_trigger_util.py`（新增契约测试）

**Interfaces:**
- Consumes: `TriggerUtil.to_trigger` / `validate`（Task A3）
- Produces: `SchedulerUtil.add_cron_job(...)` / `add_interval_job(...)` / `add_date_job(...)` 接受新契约（interval 为 JSON）

- [ ] **Step 1: 写失败测试**（断言"旧口径已消失 + 解析必须走统一层"）

```python
def test_legacy_validators_are_gone():
    """A4：旧校验器必须删除，避免两套口径并存。"""
    import pytest as _pytest

    with _pytest.raises(ImportError):
        import app.utils.cron_util  # noqa: F401


def test_add_cron_job_parses_via_trigger_util(monkeypatch, test_client):
    """A4：add_cron_job 的解析必须走 TriggerUtil（用 spy 断言，不依赖作业能否注册成功）。"""
    from types import SimpleNamespace

    from app.core import ap_scheduler
    from app.utils.trigger_util import TriggerUtil

    seen: dict = {}
    real = TriggerUtil.to_trigger

    def _spy(trigger, args, **kw):
        seen["trigger"], seen["args"] = trigger, args
        return real(trigger, args)

    monkeypatch.setattr(TriggerUtil, "to_trigger", staticmethod(_spy))
    node = SimpleNamespace(id=1, code="t", name="t", trigger="cron", trigger_args="0 9 * * 1",
                           jobstore="default", executor="default", func="app.core.logger:log")
    try:
        ap_scheduler.SchedulerUtil.add_cron_job(node)
    except Exception:  # noqa: BLE001 只断言解析路径，作业注册失败与本测试无关
        pass
    assert seen.get("trigger") == "cron" and seen.get("args") == "0 9 * * 1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q -k ap_scheduler`
Expected: FAIL（`cron_util` 仍在、`CronUtil` 引用旧口径）

- [ ] **Step 3: 实现**

`add_cron_job` → `TriggerUtil.to_trigger("cron", expr)`；`add_interval_job` → `TriggerUtil.to_trigger("interval", json.loads(args))`（兼容旧「秒 分 时 天 周」字符串：先按旧格式解析再转 JSON，并在日志里提示）；`add_date_job` → `TriggerUtil.to_trigger("date", run_date)`；
删除 `cron_util.py` 与 `time_util.validate_cron_expression`；`node/service.py:230` 的校验改为 `TriggerUtil.validate(trigger, trigger_args)`。

- [ ] **Step 4: 跑测试 + 相关模块回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py tests/test_torchkiln_task_status.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -u backend/app/core/ap_scheduler.py backend/app/utils backend/app/plugin/module_task/cronjob/node/service.py backend/tests/test_trigger_util.py
git commit -m "refactor(cron): ap_scheduler 与节点校验改走 TriggerUtil，删除旧校验器"
```

### Task A5: AI 与训练三处写入路径改造

**Files:**
- Modify: `backend/app/plugin/module_ai/workspace/service.py`（`_compute_next_run`、增改校验）
- Modify: `backend/app/plugin/module_ai/workflow/service.py`（3 处 `from_crontab`：1002-1008、1121-1123）
- Modify: `backend/app/plugin/module_train/schedule_service.py`（76-85 的 `croniter` 使用）
- Test: `backend/tests/test_trigger_util.py`

**Interfaces:**
- Consumes: `TriggerUtil.normalize/validate/next_run`（Task A1-A3）
- Produces: 三处写入均落"规范化后的 5 段 cron"；下次运行时间一律来自 `TriggerUtil.next_run`

**A6 遗留（随本任务一并修）:**
- `backend/tests/test_train_schedule.py:23` 用旧构造参数 `cron_expr=` 已失败 → 改为
  `trigger="cron", trigger_args="0 2 * * 0"`（该测试文件不在 A6 清单内，由本任务负责）。

- [ ] **Step 1: 写失败测试**（针对**调用方**行为，不是 helper 本身）

```python
def test_workflow_schedule_next_run_is_monday(test_client, auth_headers):
    """工作流定时调度：0 9 * * 1-5 的下次运行必须是周一（修 D5，改前会显示周二）。"""
    test_client.post("/api/v1/ai/workflows/1/schedule", headers=auth_headers,
                     json={"cron": "0 9 * * 1-5", "enabled": True})
    d = test_client.get("/api/v1/ai/workflows/1/schedule", headers=auth_headers).json()["data"]
    assert d["cron"] == "0 9 * * mon,tue,wed,thu,fri"   # 写入即规范化（区间展开为列表）
    assert "Mon" in d["next_run"] or "周一" in str(d)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py -q -k workflow_schedule_next_run`
Expected: FAIL（写入未规范化 / next_run 为周二）

- [ ] **Step 3: 实现**

三处：写入前 `TriggerUtil.normalize/validate`（非法 → `CustomException(msg=reason)`）；把 `from_crontab` 与
`_compute_next_run` 换成 `TriggerUtil.next_run`；删除 `workspace/service.py` 的自算实现。

- [ ] **Step 4: 跑相关回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_util.py tests/test_ai_apps.py tests/test_ai_agents.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/workspace/service.py backend/app/plugin/module_ai/workflow/service.py backend/app/plugin/module_train/schedule_service.py backend/tests/test_trigger_util.py
git commit -m "refactor(ai,train): 定时任务写入与下次运行时间统一走 TriggerUtil（修周字段错位）"
```

### Task A6: 手写 Alembic 迁移（新增 trigger/trigger_args + 规范化回填 + 删旧列）

**Files:**
- Create: `backend/app/alembic/versions/<rev>_unify_trigger_columns.py`
- Modify: `backend/app/plugin/module_ai/workspace/model.py`、`backend/app/plugin/module_ai/workflow/model.py`、`backend/app/plugin/module_train/schedule_model.py`
- Test: `backend/tests/test_trigger_migration.py`

**Interfaces:**
- Produces: 三表具备 `trigger VARCHAR(16) NOT NULL DEFAULT 'cron'` 与 `trigger_args TEXT NULL`

- [ ] **Step 1: 写失败测试**（含 Review Focus 1）

```python
def test_migration_helper_normalizes_and_skips_unsafe(test_client):
    """迁移助手：5 段规范化；6 段秒位非 0 / 7 段带年 → 跳过并返回日志。"""
    from app.utils.trigger_migration import normalize_legacy

    assert normalize_legacy("0 9 * * 1") == ("cron", "0 9 * * mon", None)
    assert normalize_legacy("0 0 9 * * *") == ("cron", "0 9 * * *", None)
    trig, args, skip = normalize_legacy("30 * * * * *")
    assert skip and "秒" in skip
    trig, args, skip = normalize_legacy("0 0 9 * * * 2030")
    assert skip and "年" in skip
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_migration.py -q`
Expected: FAIL（`app.utils.trigger_migration` 不存在）

- [ ] **Step 3: 实现**

新增 `app/utils/trigger_migration.py::normalize_legacy(value) -> (trigger, args, skip_reason)`；
手写迁移：三表 `add_column('trigger')` / `add_column('trigger_args')` → 逐行回填（可等值转换的写回，
其余记 `print` 日志）→ `drop_column('cron' / 'cron_expr')`；`downgrade()` 反向重建旧列并回填；
**插件表用 `sa.inspect(bind).has_table()` 判定后再操作**（空库重放兼容）；模型文件同步加列。

- [ ] **Step 4: 跑迁移与测试**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_migration.py -q`
Expected: PASS（测试库为 SQLite，DDL 失败会被跳过——断言以 helper 为主）

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/trigger_migration.py backend/app/alembic/versions backend/app/plugin/module_ai/workspace/model.py backend/app/plugin/module_ai/workflow/model.py backend/app/plugin/module_train/schedule_model.py backend/tests/test_trigger_migration.py
git commit -m "feat(cron): 三表统一 trigger/trigger_args 列（手写迁移，含规范化回填与降级）"
```

### Task A7: 触发预览接口（四模块各一条 thin route）

**Files:**
- Modify: `backend/app/plugin/module_ai/workspace/controller.py`、`.../workflow/controller.py`、`backend/app/plugin/module_train/controller.py`、`backend/app/plugin/module_task/cronjob/node/controller.py`
- Test: `backend/tests/test_trigger_preview_api.py`

**Interfaces:**
- Produces: `POST {各模块前缀}/trigger/preview`，请求 `{"trigger": "cron", "trigger_args": "0 9 * * 1"}`，
  响应 `SuccessResponse(data={"valid": bool, "reason": str, "describe": str, "next_run": str | None})`；
  统一层新增 `TriggerUtil.preview(trigger: str, args) -> dict`（返回上述四个字段）

**A3 审查遗留（随本任务一并收口）:**
- Minor：**「日/周同时非 `*`」的判定应按"是否覆盖全集"而非文本**——`0 9 1-31 * mon`、`0 9 */1 * mon`
  语义上等于"每天 + 周一"，现被判非法且提示自相矛盾（建议改写 `0 9 1-31 * *`）。改为：日字段为
  `*`/`*/1`/`1-31` 视为"覆盖全集"，只有**真正受限**时才触发该规则。补测试覆盖三种等价写法。
- Minor：`preview` 必须区分 `next_run is None` 的两种语义（cron 永不触发 vs date 已过期），
  在 `reason` 里分别给出可读提示（不能笼统"表达式非法"）。
- Minor：`validate` 返回 `(False, reason)` 而 `describe/to_trigger` 抛 `CustomException` 的**双形态**，
  在 `preview` 内统一适配（调用方只面对一种形态）。

- [ ] **Step 1: 写失败测试**

```python
def test_trigger_preview_endpoint(test_client, auth_headers):
    r = test_client.post("/api/v1/ai/workflows/trigger/preview",
                         json={"trigger": "cron", "trigger_args": "0 9 * * 1"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["valid"] is True and "周一" in data["describe"] and data["next_run"]

    bad = test_client.post("/api/v1/ai/workflows/trigger/preview",
                           json={"trigger": "cron", "trigger_args": "0 0 9 L * *"}, headers=auth_headers)
    assert bad.json()["data"]["valid"] is False and bad.json()["data"]["reason"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_trigger_preview_api.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现**

四个控制器各加一条路由（各自 `AuthPermission`，各自前缀），函数体只做一件事：
`return SuccessResponse(data=TriggerUtil.preview(trigger, trigger_args))`；
`TriggerUtil.preview` 在统一层实现（`validate` + `describe` + `next_run`），返回上述结构。
列表接口顺带把**两类**行标为需人工确认（`needs_review: bool`）：① 迁移时被跳过（`trigger_args` 为 NULL）；
② **`trigger_args` 非空但按新校验不通过**（如 5 段的 `0 9 31 6 *`、`0 9 1 * mon`）——否则会以"有表达式但调度不上"静默停摆。

- [ ] **Step 4: 跑测试 + 全量**

Run: `cd backend && uv run pytest -q -n 4`
Expected: PASS（全量）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/workspace/controller.py backend/app/plugin/module_ai/workflow/controller.py backend/app/plugin/module_train/controller.py backend/app/plugin/module_task/cronjob/node/controller.py backend/app/utils/trigger_util.py backend/tests/test_trigger_preview_api.py
git commit -m "feat(cron): 统一触发预览接口（四模块 thin route，后端产出描述与下次运行时间）"
```

---

## 阶段 B：调度入口统一

### Task B1: 中心调度器新增"业务作业"API

**Files:**
- Modify: `backend/app/core/ap_scheduler.py`
- Test: `backend/tests/test_business_scheduler.py`

**Interfaces:**
- Produces: `SchedulerUtil.register_business_trigger(job_key: str, trigger: str, trigger_args, func, args=(), replace=True) -> Job`、`SchedulerUtil.remove_business_job(job_key: str) -> bool`、`SchedulerUtil.sync_business_jobs() -> dict[str, int]`

- [ ] **Step 1: 写失败测试**（含 Review Focus 4）

```python
import asyncio


def test_register_and_remove_business_job_is_idempotent():
    from app.core.ap_scheduler import SchedulerUtil, scheduler

    async def _run():
        calls = []

        async def _job():
            calls.append(1)

        SchedulerUtil.register_business_trigger("t:1", "interval", {"minutes": 5}, _job)
        assert scheduler.get_job("t:1") is not None
        SchedulerUtil.register_business_trigger("t:1", "interval", {"minutes": 10}, _job)  # 幂等替换
        assert len(scheduler.get_jobs()) >= 1
        assert SchedulerUtil.remove_business_job("t:1") is True
        assert scheduler.get_job("t:1") is None          # 不留幽灵作业
        assert SchedulerUtil.remove_business_job("t:1") is False  # 再删不报错

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py -q`
Expected: FAIL（`AttributeError: register_business_trigger`）

- [ ] **Step 3: 实现**

用 `scheduler.add_job(func, trigger=TriggerUtil.to_trigger(...), id=job_key, replace_existing=replace,
coalesce=True, misfire_grace_time=60, max_instances=1)`；`remove_business_job` 捕获 `JobLookupError` 返回 `False`；
`sync_business_jobs` 遍历三表启用行注册、并删除 DB 已无对应行的业务作业（按 `job_key` 前缀过滤，不碰 `NodeModel` 作业）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/ap_scheduler.py backend/tests/test_business_scheduler.py
git commit -m "feat(scheduler): 中心调度器新增业务作业注册/移除/同步 API（幂等、无幽灵作业）"
```

### Task B2: AI 工作台定时任务并入中心调度器

**Files:**
- Modify: `backend/app/plugin/module_ai/workspace/service.py`（删 `cron_scheduler`）、`backend/app/scripts/init_app.py`（启动改 `sync_business_jobs`）
- Test: `backend/tests/test_business_scheduler.py`

**Interfaces:**
- Consumes: `SchedulerUtil.register_business_trigger/remove_business_job`（Task B1）
- Produces: 定时任务增改删/启停 → 作业同步；`next_run_time` 由作业回写

- [ ] **Step 1: 写失败测试**

```python
def test_workspace_cron_registers_business_job(test_client, auth_headers):
    """新建定时任务 → 中心调度器出现对应作业；禁用 → 作业移除。"""
    from app.core.ap_scheduler import scheduler

    r = test_client.post("/api/v1/ai/workspace/cron/create", headers=auth_headers, json={
        "name": "t-job", "cron": "0 9 * * mon", "target_type": "workflow", "target_id": 1, "enabled": True})
    cid = r.json()["data"]["id"]
    assert scheduler.get_job(f"ai_workspace_cron:{cid}") is not None

    test_client.post(f"/api/v1/ai/workspace/cron/{cid}/update", headers=auth_headers,
                     json={"enabled": False})
    assert scheduler.get_job(f"ai_workspace_cron:{cid}") is None

    test_client.request("DELETE", "/api/v1/ai/workspace/cron/delete", headers=auth_headers, json=[cid])


def test_workspace_cron_writes_next_run_back_from_job(test_client, auth_headers):
    """状态单一真源：行的 next_run_time 必须等于作业的 next_run_time（不再自算）。"""
    from app.core.ap_scheduler import scheduler

    r = test_client.post("/api/v1/ai/workspace/cron/create", headers=auth_headers, json={
        "name": "t-job2", "cron": "0 9 * * mon", "target_type": "workflow", "target_id": 1, "enabled": True})
    cid = r.json()["data"]["id"]
    job = scheduler.get_job(f"ai_workspace_cron:{cid}")
    d = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers).json()["data"]
    row = next(x for x in d if x["id"] == cid)
    assert str(job.next_run_time).startswith(str(row["next_run_time"])[:16])
    test_client.request("DELETE", "/api/v1/ai/workspace/cron/delete", headers=auth_headers, json=[cid])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py -q -k workspace`
Expected: FAIL（作业不存在）

- [ ] **Step 3: 实现**

增改删/启停处调用 `register_business_trigger`/`remove_business_job`；删除 `cron_scheduler` 轮询与
`init_app` 里的启动项；`init_app` 启动序列改为 `SchedulerUtil.sync_business_jobs(<本模块收集的作业列表>)`。

- [ ] **Step 4: 跑测试 + 回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py tests/test_ai_apps.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/workspace/service.py backend/app/scripts/init_app.py backend/tests/test_business_scheduler.py
git commit -m "refactor(ai): 工作台定时任务并入中心调度器，删除每分钟自建轮询"
```

### Task B3: AI 工作流定时调度并入

**Files:**
- Modify: `backend/app/plugin/module_ai/workflow/service.py`
- Test: `backend/tests/test_business_scheduler.py`

**Interfaces:**
- Consumes: Task B1 API
- Produces: `ai_workflow_schedule:{id}` 作业与调度行同步

- [ ] **Step 1: 写失败测试**

```python
def test_workflow_schedule_registers_business_job(test_client, auth_headers):
    from app.core.ap_scheduler import scheduler

    r = test_client.post("/api/v1/ai/workflows/1/schedule", headers=auth_headers,
                         json={"cron": "0 9 * * mon-fri", "enabled": True})
    assert r.status_code == 200, r.text
    assert scheduler.get_job("ai_workflow_schedule:1") is not None

    test_client.post("/api/v1/ai/workflows/1/schedule", headers=auth_headers,
                     json={"cron": "0 9 * * mon-fri", "enabled": False})
    assert scheduler.get_job("ai_workflow_schedule:1") is None
```

- [ ] **Step 2: 跑测试确认失败** → Run: 同 Task B2 命令，`-k workflow`；Expected: FAIL
- [ ] **Step 3: 实现**：`set_schedule` 处注册/移除作业；删除文件内自算 `next_run` 的循环逻辑
- [ ] **Step 4: 跑测试** → Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py -q`；Expected: PASS
- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/workflow/service.py backend/tests/test_business_scheduler.py
git commit -m "refactor(ai): 工作流定时调度并入中心调度器"
```

### Task B4: 训练调度并入

**Files:**
- Modify: `backend/app/plugin/module_train/schedule_service.py`、`backend/app/plugin/module_train/scheduler.py`
- Test: `backend/tests/test_business_scheduler.py`

**Interfaces:**
- Consumes: Task B1 API
- Produces: `train_schedule:{id}` 作业；训练调度不再用 `croniter` 判定到期

- [ ] **Step 1: 写失败测试**：断言创建训练调度后 `scheduler.get_job("train_schedule:{id}")` 存在、禁用后为 `None`（同 B2 结构）
- [ ] **Step 2: 跑测试确认失败** → Run: `-k train`；Expected: FAIL
- [ ] **Step 3: 实现**：调度行增改/启停同步作业；删除 `croniter` 到期判定与对应 `while True` 段（其余训练轮询保留）
- [ ] **Step 4: 跑测试 + 训练模块回归** → Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_business_scheduler.py tests/test_train_recovery.py -q`；Expected: PASS
- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_train/schedule_service.py backend/app/plugin/module_train/scheduler.py backend/tests/test_business_scheduler.py
git commit -m "refactor(train): 训练定时调度并入中心调度器，去掉 croniter 自建判定"
```

### Task B5: 调度行为显式化 + 多副本开关 + 真实触发验证

**Files:**
- Modify: `backend/app/config/setting.py`、`backend/app/core/ap_scheduler.py`、`backend/.env.dev`（示例项）
- Test: `backend/tests/test_business_scheduler.py`

**Interfaces:**
- Produces: 配置项 `SCHEDULER_ENABLED: bool = True`；`init_scheduler` 依据它决定是否 `start()`

- [ ] **Step 1: 写失败测试**

```python
def test_scheduler_enabled_flag_defaults_true():
    from app.config.setting import settings

    assert settings.SCHEDULER_ENABLED is True


def test_business_job_defaults():
    """业务作业必须显式带 coalesce/misfire/max_instances（避免默认 1 秒 misfire 丢跑）。"""
    from app.core.ap_scheduler import SchedulerUtil, scheduler

    async def _job():
        return None

    SchedulerUtil.register_business_trigger("t:defaults", "interval", {"minutes": 5}, _job)
    job = scheduler.get_job("t:defaults")
    assert job.coalesce is True
    assert job.misfire_grace_time == 60
    assert job.max_instances == 1
    SchedulerUtil.remove_business_job("t:defaults")
```

- [ ] **Step 2: 跑测试确认失败** → Expected: FAIL（`settings.SCHEDULER_ENABLED` 不存在）
- [ ] **Step 3: 实现**：新增配置项（`setting.py` 默认 True、`.env.dev` 注释示例）；`init_scheduler` 判断开关；确认作业级参数已显式传入
- [ ] **Step 4: 真实触发验证（手工，一次性）**：把某条定时任务 cron 改为"下一分钟"，观察日志出现执行记录与 `last_run_time` 回写；验证后改回
- [ ] **Step 5: 提交**

```bash
git add backend/app/config/setting.py backend/app/core/ap_scheduler.py backend/.env.dev backend/tests/test_business_scheduler.py
git commit -m "feat(scheduler): 调度行为显式化（coalesce/misfire/max_instances）+ SCHEDULER_ENABLED 开关"
```

---

## 阶段 C：统一 UI

### Task C1: 安装组件 + `TriggerEditor`（cron 类型）

**Files:**
- Modify: `frontend/package.json`（依赖）
- Create: `frontend/src/components/TriggerEditor/index.vue`
- Test: `frontend/e2e/trigger-editor.spec.ts`（后续任务扩展）

**Interfaces:**
- Produces: `<TriggerEditor v-model:trigger="t" v-model:trigger-args="a" @error="msg" />`

- [ ] **Step 1: 安装依赖（国内镜像）**

```bash
cd frontend && pnpm add @vue-js-cron/element-plus --registry=https://registry.npmmirror.com
```

- [ ] **Step 2: 写组件骨架**：`el-radio-group`（定时/间隔/单次/立即）+ 定时分支渲染 `CronElementPlus`（`:format="{ inherit: 'crontab' }"`、`v-model` 回写 cron 字符串、`@error` 上抛）
- [ ] **Step 3: 本地起前端并手测**：Run: `cd frontend && pnpm run type-check`；Expected: 无类型错误
- [ ] **Step 4: 提交**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/TriggerEditor/index.vue
git commit -m "feat(ui): 新增 TriggerEditor（定时分支用 @vue-js-cron/element-plus）"
```

### Task C2: `TriggerEditor` 四类型 + 实时预览 + 非法拦截（与 C3 合并验收）

> **预检 ruling（2026-10-18）**：本任务原计划独立验收，但组件没有"真实页面"可供 e2e 驱动。
> 决定：C2 只做组件实现 + `pnpm run type-check`；**交互与 e2e 一律在 C3（AI 工作台真实页面）验收**，
> 避免为测试造临时页面。C3 的验收即覆盖 C2 的四类型、预览与非法拦截。

**Files:**
- Modify: `frontend/src/components/TriggerEditor/index.vue`
- Modify: `frontend/src/api/module_ai/workspace.ts`（预览接口封装）

**Interfaces:**
- Consumes: Task A7 预览接口
- Produces: 组件内展示"人话描述 + 下次运行时间"；非法时 `@error` 有值

- [ ] **Step 1: 实现间隔/单次/立即三个分支**

间隔：`el-input-number` × weeks/days/hours/minutes/seconds；单次：`el-date-picker`（datetime，`value-format="YYYY-MM-DD HH:mm:ss"`）；
立即：一行说明文案（"保存后立即执行一次"）。`trigger`/`triggerArgs` 通过 `update:` 事件上抛。

- [ ] **Step 2: 接预览接口**

输入变化后防抖 300ms 调预览接口，展示 `describe` 与 `next_run`；`valid=false` 时 `emit("error", reason)`。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/TriggerEditor/index.vue frontend/src/api
git commit -m "feat(ui): TriggerEditor 支持四种触发类型 + 实时预览与非法拦截"
```

### Task C3: AI 工作台「新建定时任务」替换

**Files:**
- Modify: `frontend/src/views/module_ai/workspace/index.vue`（弹窗 176-205、列表展示）
- Test: `frontend/e2e/trigger-editor.spec.ts`

- [ ] **Step 1: 写 e2e**（同时覆盖 C2 的四类型/预览/非法拦截）

```ts
// 1) 定时：选"每周一 09:00" → 保存 → 列表出现描述与下次运行时间
// 2) 间隔：切"间隔"→ 填 2 小时 → 预览含"每 2 小时"
// 3) 单次：切"单次"→ 选未来时间 → 保存成功
// 4) 立即：切"立即"→ 保存成功（列表标"立即"）
// 5) 非法：填 0 0 9 L * * → 断言前端提示非法且保存按钮被拦
```
- [ ] **Step 2: 跑用例确认失败**；Expected: FAIL
- [ ] **Step 3: 实现**：`el-input` → `TriggerEditor`；保存体提交 `trigger`/`trigger_args`；列表列增加"触发方式/描述/下次运行"；"表达式需人工确认"的行用 `el-tag type="warning"` 标出（Review Focus 1）
- [ ] **Step 4: 跑用例确认通过 + 截图核对**（`e2e/trigger-workspace.png`）
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/workspace/index.vue frontend/e2e/trigger-editor.spec.ts
git commit -m "feat(ui): AI 工作台定时任务改用 TriggerEditor（含触发方式与下次运行展示）"
```

### Task C4: AI 工作流「定时调度」替换

**Files:**
- Modify: `frontend/src/views/module_ai/workflow/components/WorkflowEditor.vue`（853 行附近）
- Test: `frontend/e2e/trigger-editor.spec.ts`

- [ ] **Step 1: 写 e2e**：打开工作流编辑器 → 定时调度面板 → 选"每天 09:00" → 保存 → 断言回显为 `0 9 * * *`
- [ ] **Step 2: 跑用例确认失败**；Expected: FAIL
- [ ] **Step 3: 实现**：替换为 `TriggerEditor`；提交 `trigger`/`trigger_args`
- [ ] **Step 4: 跑用例确认通过 + 截图核对**
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/workflow/components/WorkflowEditor.vue frontend/e2e/trigger-editor.spec.ts
git commit -m "feat(ui): 工作流定时调度改用 TriggerEditor"
```

### Task C5: 训练调度面板替换

**Files:**
- Modify: `frontend/src/components/Train/SchedulePanel.vue`
- Test: `frontend/e2e/trigger-editor.spec.ts`

- [ ] **Step 1: 写 e2e**：打开训练调度面板 → 新建计划 → 选"间隔/每 2 小时" → 保存 → 列表显示"每 2 小时"
- [ ] **Step 2: 跑用例确认失败**；Expected: FAIL
- [ ] **Step 3: 实现**：替换旧输入与停更组件；提交新契约字段
- [ ] **Step 4: 跑用例确认通过 + 截图核对**
- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/Train/SchedulePanel.vue frontend/e2e/trigger-editor.spec.ts
git commit -m "feat(ui): 训练调度面板改用 TriggerEditor"
```

### Task C6: 系统定时任务节点页替换（删两套旧编辑器）

**Files:**
- Modify: `frontend/src/views/module_task/cronjob/node/index.vue`
- Delete: `frontend/src/components/IntervalTab/index.vue`
- Test: `frontend/e2e/trigger-editor.spec.ts`

- [ ] **Step 1: 写 e2e**：节点页新建 → 四种触发类型各存一次 → 断言都能保存且列表显示触发方式
- [ ] **Step 2: 跑用例确认失败**；Expected: FAIL
- [ ] **Step 3: 实现**：四个 `el-form-item` 分支 → 一个 `TriggerEditor`；删除 `IntervalTab` 与 `vue3CronPlus` 引用（含 `src/types/vue3-cron-plus.d.ts` 与 `package.json` 依赖）
- [ ] **Step 4: 跑用例确认通过 + 截图核对**
- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_task/cronjob/node/index.vue frontend/src/components/IntervalTab frontend/src/types frontend/package.json frontend/e2e/trigger-editor.spec.ts
git commit -m "feat(ui): 系统定时任务节点页统一为 TriggerEditor，删除 IntervalTab 与停更 Quartz 组件"
```

### Task C7: 四入口 e2e 汇总核对 + 全量回归

**Files:**
- Modify: `frontend/e2e/trigger-editor.spec.ts`

- [ ] **Step 1: 补一条"非法表达式被拦"的 e2e**：四处任选一处填 `0 0 9 L * *` → 断言前端提示非法且保存被拒（不落库）
- [ ] **Step 2: 跑四个入口的 e2e**：Run: `cd frontend && npx playwright test e2e/trigger-editor.spec.ts --project=chromium`；Expected: 全绿
- [ ] **Step 3: 截图核对四入口风格一致**（`e2e/trigger-*.png`，与既有页面并排看）
- [ ] **Step 4: 全量后端回归**：Run: `cd backend && uv run pytest -q -n 4`；Expected: 全部通过
- [ ] **Step 5: 提交**

```bash
git add frontend/e2e/trigger-editor.spec.ts
git commit -m "test(e2e): 四入口触发配置统一核对（含非法拦截）"
```
