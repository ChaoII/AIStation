# 问数 service.py 拆分实施计划（第一阶段）

> **For agentic workers:** 本计划按任务逐条执行，每完成一条勾选一个 `- [ ]`。步骤用 `- [ ]` 跟踪。

**目标：** 把 11,041 行、249 个方法的 `backend/app/plugin/module_ai/query/service.py` 按职责拆成独立模块，**行为与公开 API 零变化**，第一阶段先拆三块低耦合子系统。

**架构：** 把类方法按域搬进 mixin 类（`ActionsOps` / `AssetsOps` / `MetricsOps`），`AiQueryService` 改为继承它们；`cls` 仍是 `AiQueryService`，所以 `cls._cfg()`、`cls._execute_one()` 等跨域调用照旧解析。模块级纯函数/常量搬进 `core.py`，`service.py` 保留同名再导出，**全仓 700+ 处调用点不改一行**。

**技术栈：** Python 3.13 / FastAPI / SQLAlchemy 2.0 异步 / pytest / SQLite（测试）与 PostgreSQL（dev）

**Spec：** `docs/superpowers/specs/2026-11-06-query-permission-model-design.md`（权限部分不属本计划）

## 全局约束

- **零行为变化**：不重命名公开方法、不改签名、不改默认值、不改 SQL。
- **不改调用点**：`from .service import X` 与 `service.X` 必须继续可用（含 monkeypatch 场景）。
- 每个任务结束必须跑：目标测试 → `scripts/query_golden_smoke.py` → 提交（中文提交信息）。
- 单个新模块 ≤ 900 行；**不要**顺手重构逻辑（只搬移 + 必要的 import 调整）。
- 模块内不得 import `service`（循环导入）；跨模块共享的东西放 `core.py`。
- 测试里若有 `monkeypatch.setattr(qservice, "xxx")`，拆走后必须同步改 patch 目标，否则测试是假绿。

## Review Focus

1. **`cls` 语义**：mixin 里的 `cls` 必须是 `AiQueryService`；任何 `type(self)`/`__class__` 硬编码会拿到 mixin 类，跨域方法解析失败。
2. **monkeypatch 失效**：测试 patch `service.async_db_session` / `service._degrade` 时，代码若已搬到新模块，patch 不再命中（假绿）。每个搬移任务必须检查并修 patch 目标。
3. **模块级单例搬移**：`_DEGRADED` / `_SQL_CACHE` / `_BYPASS_CACHE` 搬走后，`reset_degraded()` / `bypass_caches()` / `sql_cache_clear()` 若仍改旧引用，计数与缓存会分叉。
4. **导入顺序**：`service.py` 顶部 import mixin，mixin 顶部 import `core`；任何 mixin 顶部再 import `service` 会 ImportError（部分初始化）。
5. **OpenAPI/路由不变**：`policy_api.py` 的 `from .service import ...` 与 `controller.py` 的 `AiQueryService.xxx` 必须全部照旧。

---

### Task 1: 基线快照（不改代码）

**Files:**
- Create: `docs/superpowers/plans/2026-11-08-query-service-split-baseline.md`

**Interfaces:**
- Consumes: 无
- Produces: 一组可对照的数字（用例数、耗时、冒烟结果），后续每个任务据此判断"是否变坏"。

- [x] **Step 1: 记录 query 相关用例基线**

Run: `cd backend && .\.venv\Scripts\python.exe -m pytest tests -k "query or ont or policy" -q`
Expected: 记录 `passed/failed/skipped` 三个数字与耗时；若出现既有失败，逐条记下用例名（作为"已知失败"，不许在拆分中增加）。

- [x] **Step 2: 记录三条冒烟基线**

Run: `.\.venv\Scripts\python.exe scripts\query_golden_smoke.py` → 期望末行 `全部通过`
Run: `.\.venv\Scripts\python.exe scripts\query_policy_smoke.py` → 期望 `权限网关冒烟通过 8/8`
Run: `cd frontend && node scripts\golden_path.mjs` → 期望 `全部通过`

- [x] **Step 3: 写基线文档并提交**

把三组数字写进 `2026-11-08-query-service-split-baseline.md`（含日期与命令），提交 `docs(query): service 拆分基线快照`。

---

### Task 2: 抽 `core.py` + `degraded.py`

**Files:**
- Create: `backend/app/plugin/module_ai/query/core.py`
- Create: `backend/app/plugin/module_ai/query/degraded.py`
- Modify: `backend/app/plugin/module_ai/query/service.py:1-250`（搬移 + 再导出）
- Test: `backend/tests/test_query_degraded.py`

**Interfaces:**
- Produces（`core.py`）：`clamp_rows(n) -> int`、`json_cell(v)`、`COMMENT_RE`、`FORBIDDEN_RE`、`MAX_ROWS`
- Produces（`degraded.py`）：`degrade(area, exc=None) -> None`、`degraded_status() -> dict`、`reset_degraded() -> None`
- Consumes: 无（两个模块都不 import service）

- [x] **Step 1: 跑目标测试确认现状**

Run: `pytest tests/test_query_degraded.py -q` → 期望全部通过（这是拆分前的护栏）。

- [x] **Step 2: 新建 `degraded.py` 并搬移**

把 `_DEGRADED` / `_DEGRADED_INFO` / `_DEGRADE_LOG_TIMES` / `_degrade` / `degraded_status` / `reset_degraded` 整体搬过去，函数改名为 `degrade`（无下划线，因为是新模块的公开接口）。

- [x] **Step 3: `service.py` 再导出，保住旧名字**

```python
from .degraded import degrade as _degrade, degraded_status, reset_degraded  # noqa: F401
```

`service.py` 内部 12 处 `_degrade(...)` 调用**不改**；`controller.py` 的 `from .service import degraded_status` 照旧。

- [x] **Step 4: 验证**

Run: `pytest tests/test_query_degraded.py tests/test_query_policy_api.py -q` → 全绿
Run: `scripts\query_golden_smoke.py` → `全部通过`
检查：`grep -rn "from .service import.*degraded" backend/app` 仍能命中旧路径。

- [x] **Step 5: 提交**

`refactor(query): 抽出 degraded 模块（service 保留再导出）`

---

### Task 3: 抽 `actions_ops.py`（动作 / 写回 / 审批）

**Files:**
- Create: `backend/app/plugin/module_ai/query/actions_ops.py`
- Modify: `backend/app/plugin/module_ai/query/service.py:3795-4043`（搬移）、`service.py` 类声明处（加基类）
- Test: `backend/tests/test_ontology_regressions.py`、`backend/tests/test_query_ddl_dialect.py`

**Interfaces:**
- Produces: `class ActionsOps:` 内含 `list_actions` / `upsert_action` / `execute_action` / `approve_action` / `reject_action` / `list_pending_actions` / `list_action_logs` / `_action_writable_for` / `_user_role_codes_by_id` / `_is_superuser`（签名与现在逐字一致）
- Consumes: `core.py`；不允许 import service

- [x] **Step 1: 跑目标测试确认现状**

Run: `pytest tests/test_ontology_regressions.py tests/test_query_ddl_dialect.py -q`

- [x] **Step 2: 原样搬移 10 个方法到 `ActionsOps`**

只调整缩进与 import；`cls.` 调用一律保留（它们在 `AiQueryService` 上解析）。

- [x] **Step 3: 让 `AiQueryService` 继承**

```python
class AiQueryService(ActionsOps):
```

- [x] **Step 4: 验证**

Run: `pytest tests/test_ontology_regressions.py tests/test_query_ddl_dialect.py -q` → 全绿
Run: `scripts\query_golden_smoke.py`、`scripts\query_policy_smoke.py` → 全通过
手工确认：`AiQueryService.list_actions.__self__ is AiQueryService`（classmethod 绑定仍是本类）。

- [x] **Step 5: 提交**

`refactor(query): 动作/写回方法搬进 ActionsOps mixin`

---

### Task 4: 抽 `assets_ops.py`（资产读 / 写 / 敏感扫描）

**Files:**
- Create: `backend/app/plugin/module_ai/query/assets_ops.py`
- Modify: `backend/app/plugin/module_ai/query/service.py:2348-2563`、`:2893-3159`（搬移）
- Test: `backend/tests/test_query_schema_marking.py`、`backend/tests/test_ontology_query_bridge.py`

**Interfaces:**
- Produces: `class AssetsOps:` 内含 `list_assets` / `_asset_dq_score` / `_asset_lineage_count` / `scan_sensitive` / `list_asset_columns` / `upsert_asset` / `batch_upsert_asset_meta` / `upsert_asset_column` / `draft_asset_descriptions`
- **不搬** `autopilot` / `generate_asset_descriptions`：它们被 `test_autopilot_generate_desc.py` 用 `monkeypatch.setattr(qservice, "async_db_session")` 打桩，留下可避免假绿。

- [x] **Step 1: 跑目标测试确认现状**

Run: `pytest tests/test_query_schema_marking.py tests/test_ontology_query_bridge.py -q`

- [x] **Step 2: 搬移 9 个方法到 `AssetsOps`（`AiQueryService(ActionsOps, AssetsOps)`）**

- [x] **Step 3: 检查危险 patch 是否失效**

Run: `pytest tests/test_autopilot_generate_desc.py -q` → 必须仍全绿；若失败，说明把不该搬的搬了，回退该方法。

- [x] **Step 4: 全量验证**

Run: `pytest tests -k "query or ont" -q` → 与 Task 1 基线逐项对比（失败数不得增加）
Run: `scripts\query_golden_smoke.py` → `全部通过`

- [x] **Step 5: 提交**

`refactor(query): 资产方法搬进 AssetsOps mixin`

---

### Task 5: 抽 `metrics_ops.py`（指标 / 术语）

**Files:**
- Create: `backend/app/plugin/module_ai/query/metrics_ops.py`
- Modify: `backend/app/plugin/module_ai/query/service.py:2146-2347`（搬移）
- Test: `backend/tests/test_query_metric_match.py`、`backend/tests/test_query_stream_metric.py`、`backend/tests/test_query_modeling_generate.py`

**Interfaces:**
- Produces: `class MetricsOps:` 内含 `list_metrics` / `upsert_metric` / `generate_modeling` / `promote_message_to_metric` / `list_terms` / `upsert_term`

- [x] **Step 1: 跑目标测试确认现状**
- [x] **Step 2: 搬移 6 个方法（`AiQueryService(ActionsOps, AssetsOps, MetricsOps)`）**
- [x] **Step 3: 验证 fast path 没受影响**

Run: `pytest tests/test_query_metric_match.py tests/test_query_stream_metric.py tests/test_query_modeling_generate.py -q`
Run: `pytest tests/test_query_fastpath_guard.py -q`（`_match_metric` 仍走 `cls.` 解析）

- [x] **Step 4: 提交**

`refactor(query): 指标/术语方法搬进 MetricsOps mixin`

---

### Task 6: 收口与记录

**Files:**
- Modify: `AGENTS.md`（问数小节加一行拆分进度）
- Create/Modify: `docs/superpowers/plans/2026-11-08-query-service-split.md`（本文件勾选完成项）

- [x] **Step 1: 全量回归**

Run: `pytest tests -q -n 4` → 与基线对比；已知 flaky `test_query_policy_context_app.py` 单独复跑。
Run: `scripts\query_golden_smoke.py`、`scripts\query_policy_smoke.py`、`frontend/scripts/golden_path.mjs`

- [x] **Step 2: 记录结果**

`service.py` 行数（拆分前 11,041 → 拆分后实测）、新增模块与行数、测试数字对比。

- [x] **Step 3: 提交**

`docs(query): 记录 service 拆分第一阶段结果`

---

## 后续阶段（本计划不执行，只登记）

- **第二阶段**：本体/概念/图谱方法（`_ont_*`、`list_objects`、`list_concepts`、`resolve_entity_object`）→ `ontology_ops.py`。
- **第三阶段**：问数主链路（`ask` / `ask_stream` / `_slow_path` / `_nl2sql` / `_build_schema_context` / `_execute_one`）→ `ask_ops.py`，风险最高，需要先补"同一问题前后输出一致"的对比断言。
- **第四阶段**：模块级纯函数（`validate_sql`、`_match_metric`、`_sql_cache_*`、`parse_time_range`）→ `sqlgate.py` / `metric_matching.py` / `sqlcache.py` / `timeparse.py`。`_execute_sql` 依赖 `AiQueryService._cfg()`，搬移时必须延迟 import。
