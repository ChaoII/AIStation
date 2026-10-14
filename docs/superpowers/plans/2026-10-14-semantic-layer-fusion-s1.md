# 语义层融合 · S1（数据模型 + 本体实例层支持自定义数据源）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让本体对象能指向**任意数据源**（含燃煤库 `ds:4`）执行实例查询，并落好数据模型（指标绑定列 + 评测 `dataset` 列），为后续「指标进对象查询」「自动建模」打基础。

**Architecture:** 在 `ontology/service.py` 新增 `_exec_on(datasource_id, sql, params)`：`datasource_id` 为空时走现有系统主库 `_exec`；非空时复用 `query/executor.build_engine` + `_ds_cfg_from_model` 连对应数据源执行（延迟导入避免循环依赖），返回统一的 `_Rows` 包装（支持 `fetchall/fetchone/scalar`），使实例层各方法的调用点几乎无需改动。同时用幂等 `ADD COLUMN IF NOT EXISTS` 给 `ai_query_metrics` 与 `ai_query_testcase` 补列。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async（asyncpg）+ PostgreSQL；pytest（`backend/tests/`，日常单文件跑）。

**Spec:** `docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md`（§2.1/2.2/2.3、§4.1）

## Global Constraints

- 所有回复、代码注释、文档正文一律**中文**；提交信息格式 `fix(query): 中文描述`。
- 本阶段**不涉及 LLM**；后续阶段 LLM 一律走 agno（不得新增 `AsyncOpenAI` 直连）。
- `ai_*` 表**不走 Alembic**，一律用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 幂等补列（兼容 SQLite 测试库）。
- **绝不自己拼 SQL 绕过本体行/列级策略**（沿用 `object_exec.py` 头注纪律）。
- 燃煤库（`ds:4`）**大小写敏感**：表/列名必须用**真实大小写 + 双引号**（复用现有 `_safe_ident` 的 `"{col}"` 写法，前提是本体属性的 `source_col` 保留真实大小写）。
- 本阶段**不改** `ask()` 既有 fast→object→slow 降级骨架。
- 测试日常只跑单文件；全量留提交前。

## Review Focus

1. **跨库表/列名大小写**：燃煤库大小写敏感，若把真实大小写弄丢（如折成小写），关系/列会"不存在" → 整题打崩（历史踩坑）。任务 3 的测试须用**大小写混合**的表名/列名验证。
2. **`datasource_id` 为空时行为不变**：系统库对象的实例查询结果必须与改造前**逐字节一致**（回归测试覆盖）。
3. **跨库仍走权限**：换库后行/列级策略**不能失效**（任务 3 保留 `_sec.filter_instances` / `row_filter_sql` 调用，测试断言策略仍生效）。
4. **连接不泄漏**：数据源引擎用完必须 `dispose()`（任务 2 测试断言 `dispose` 被调用）。
5. **未物化降级**：对象表不在目标数据源 schema 内时应返回 `ok=False` 降级，**不抛异常**（任务 3 测试覆盖）。

---

### Task 1: 指标绑定列 + 评测 `dataset` 列

**Files:**
- Modify: `backend/app/plugin/module_ai/query/model.py`（`AiQueryMetricModel`，:61-91）
- Modify: `backend/app/plugin/module_ai/query/service.py`（`_ensure_marking_columns`，:158-175，追加指标补列）
- Modify: `backend/app/plugin/module_ai/query/eval_set.py`（`_TESTCASE_DDL` :14-22、`_CASE_FIELDS` :60-63、`_case_row` :66-80、`upsert_case` :83-116、`list_cases` :119-158）
- Test: `backend/tests/test_query_metric_binding.py`（新建）

**Interfaces:**
- Produces:
  - `AiQueryMetricModel.object_code: str`、`.property_code: str`、`.agg_fn: str`、`.bound_dimensions: list`（JSONB）
  - `eval_set.upsert_case(data)` 接受 `data["dataset"]: str`；`eval_set.list_cases(dataset: str | None = None, ...)`；`_case_row(r)` 返回 `"dataset": str`
  - `_to_metric_dict(m)`（`service.py:321`）返回体新增 `object_code/property_code/agg_fn/bound_dimensions`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_metric_binding.py
import pytest
from app.plugin.module_ai.query import eval_set as es


@pytest.mark.asyncio
async def test_metric_columns_exist():
    from app.plugin.module_ai.query.service import _ensure_marking_columns
    from app.core.database import async_db_session
    from sqlalchemy import text
    async with async_db_session.begin() as db:
        await _ensure_marking_columns(db)
    async with async_db_session() as db:
        cols = {r[0] for r in (await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ai_query_metrics'"))).fetchall()}
    for c in ("object_code", "property_code", "agg_fn", "bound_dimensions"):
        assert c in cols


@pytest.mark.asyncio
async def test_case_dataset_roundtrip():
    await es.upsert_case({"question": "__t_ds__?", "gold_sql": "SELECT 1",
                          "datasource": "system", "dataset": "coal_semantic_v1"})
    rows = await es.list_cases(dataset="coal_semantic_v1")
    assert any(r["question"] == "__t_ds__?" and r["dataset"] == "coal_semantic_v1" for r in rows)
    await es.delete_cases([r["id"] for r in rows if r["question"] == "__t_ds__?"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_metric_binding.py -q`
Expected: FAIL（`ai_query_metrics` 无 `object_code` 列 / `upsert_case` 不认识 `dataset`）

- [ ] **Step 3: 实现**

`model.py` 的 `AiQueryMetricModel` 追加（放在 `sql_template` 附近）：

```python
    object_code: Mapped[str] = mapped_column(
        String(80), default="", comment="绑定本体对象 code（空=模板型指标）")
    property_code: Mapped[str] = mapped_column(
        String(80), default="", comment="绑定本体属性 code（聚合对象）")
    agg_fn: Mapped[str] = mapped_column(
        String(16), default="", comment="绑定型指标聚合: count/sum/avg/min/max")
    bound_dimensions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="可选维度（本体属性 code 列表）")
```

`service.py` 的 `_ensure_marking_columns(db)` 的 `for sql in (...)` 元组追加 4 条 `ALTER TABLE ai_query_metrics ADD COLUMN IF NOT EXISTS ...`（`object_code VARCHAR(80) DEFAULT ''`、`property_code VARCHAR(80) DEFAULT ''`、`agg_fn VARCHAR(16) DEFAULT ''`、`bound_dimensions JSONB DEFAULT '[]'`）。

`eval_set.py`：
- `_TESTCASE_DDL` 加列 `dataset VARCHAR(64) DEFAULT ''`（放在 `datasource` 后）。
- 新增 `_ensure_dataset_column()`（或并入 `ensure_eval_tables`）执行 `ALTER TABLE ai_query_testcase ADD COLUMN IF NOT EXISTS dataset VARCHAR(64) DEFAULT ''`。
- `_CASE_FIELDS` 加 `"dataset"`。
- `_case_row` 返回 `"dataset": (r[N] or "")`（按新 SELECT 列序）。
- `upsert_case`：params 加 `"dataset"`，INSERT 列与 `ON CONFLICT DO UPDATE` 加 `dataset=EXCLUDED.dataset`。
- `list_cases`：新增 `dataset: str | None = None` 参数，`if dataset: conds.append("dataset = :dset")`；SELECT 加 `dataset`。
- `_to_metric_dict` 加 4 个字段。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_metric_binding.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/model.py backend/app/plugin/module_ai/query/service.py backend/app/plugin/module_ai/query/eval_set.py backend/tests/test_query_metric_binding.py
git commit -m "feat(query): 指标绑定列与评测数据集字段"
```

---

### Task 2: `_exec_on` 按 `datasource_id` 选择执行引擎

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/service.py`（`_exec` 附近，:439 之后新增）
- Test: `backend/tests/test_ontology_datasource_exec.py`（新建）

**Interfaces:**
- Consumes: `query.service._load_ds(id)`、`query.service._ds_cfg_from_model(ds)`、`query.executor.build_engine(cfg)`（均**函数内延迟导入**，避免 `ontology ↔ query` 循环导入）
- Produces:
  - `_Rows`（新类）：`.fetchall() -> list`、`.fetchone() -> Row | None`、`.scalar() -> Any`
  - `async def _exec_on(datasource_id: int | None, sql: str, params: dict | None = None) -> _Rows`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ontology_datasource_exec.py
import pytest
from app.plugin.module_ai.ontology import service as ont


@pytest.mark.asyncio
async def test_exec_on_system_when_no_ds():
    r = await ont._exec_on(None, "SELECT 1 AS x")
    assert r.scalar() == 1
    assert r.fetchall()[0][0] == 1


@pytest.mark.asyncio
async def test_exec_on_uses_datasource_engine_and_disposes(monkeypatch):
    calls = {"disposed": False}

    class _FakeConn:
        async def execute(self, *a, **k):
            class _R:
                def fetchall(self): return [(42,)]
            return _R()
    class _FakeEngine:
        def connect(self): return self
        async def __aenter__(self): return _FakeConn()
        async def __aexit__(self, *a): return False
        async def dispose(self): calls["disposed"] = True

    from app.plugin.module_ai.query import service as qs
    from app.plugin.module_ai.query import executor as qe

    class _DS:  # 假数据源
        type, host, port, database, username, password = "postgres", "h", 1, "d", "u", "p"
    async def _fake_load(ds_id): return _DS()
    monkeypatch.setattr(qs, "_load_ds", _fake_load)
    monkeypatch.setattr(qe, "build_engine", lambda cfg: _FakeEngine())

    r = await ont._exec_on(4, "SELECT 42")
    assert r.scalar() == 42
    assert calls["disposed"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_datasource_exec.py -q`
Expected: FAIL（`module 'app.plugin.module_ai.ontology.service' has no attribute '_exec_on'`）

- [ ] **Step 3: 实现**

在 `ontology/service.py` 的 `_exec_write`（:445-448）之后新增：

```python
class _Rows:
    """`_exec_on` 的返回值包装：在连接内取好行，出连接后仍可 fetch。"""

    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def fetchall(self) -> list:
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        row = self.fetchone()
        return row[0] if row is not None else None


async def _exec_on(datasource_id, sql: str, params: dict | None = None) -> _Rows:
    """按对象的 `datasource_id` 选择执行引擎：空→系统主库；非空→该数据源。

    数据源引擎**用完即 dispose**（避免连接泄漏）。延迟导入 query 模块，
    避免 `ontology ↔ query` 循环导入。
    """
    if not datasource_id:
        res = await _exec(sql, params)
        return _Rows(res.fetchall())
    from ..query import executor as _ex
    from ..query import service as _qs

    ds = await _qs._load_ds(int(datasource_id))
    eng = _ex.build_engine(_qs._ds_cfg_from_model(ds))
    try:
        async with eng.connect() as conn:
            res = await conn.execute(_t(sql), params or {})
            return _Rows(res.fetchall())
    finally:
        await eng.dispose()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_datasource_exec.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/ontology/service.py backend/tests/test_ontology_datasource_exec.py
git commit -m "feat(ontology): 实例层按 datasource_id 选择执行引擎"
```

---

### Task 3: 实例层方法改用 `_exec_on`（含 `_instance_meta` 读 `datasource_id`）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/service.py`
  - `_instance_meta`（:2552-2578）：SELECT 加 `COALESCE(datasource_id,0)`，返回体加 `"datasource_id"`
  - `_table_columns`（:2532-2549）：新增可选 `datasource_id` 参数（非空时用数据源引擎反射）
  - `instance_search`（:2600-2703）、`instance_get`（:2706+）、`instance_aggregate`（:2808-2886）、`instance_pivot`（:2889-2938）：`_exec(...)` → `_exec_on(meta.get("datasource_id"), ...)`
- Test: `backend/tests/test_ontology_datasource_instance.py`（新建）

**Interfaces:**
- Consumes: `_exec_on`（Task 2）、`_instance_meta` 新增字段 `datasource_id`
- Produces: `_instance_meta(code) -> {..., "datasource_id": int}`；实例层四方法对 `datasource_id` 非空对象走数据源引擎

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ontology_datasource_instance.py
import pytest
from app.plugin.module_ai.ontology import service as ont


@pytest.mark.asyncio
async def test_instance_meta_reads_datasource_id(monkeypatch):
    async def _fake_exec(sql, params=None):
        class _R:
            def fetchone(self):
                return ("demo_ds_obj", "演示", "id", "name", "DEMO_TABLE", False, 4)
        return _R()
    monkeypatch.setattr(ont, "_exec", _fake_exec)
    async def _fake_cols(table, datasource_id=None):
        return {"id", "name"}
    monkeypatch.setattr(ont, "_table_columns", _fake_cols)
    async def _fake_props(code):
        return [{"code": "id", "name": "ID", "prop_type": "number", "options": []},
                {"code": "name", "name": "名", "prop_type": "string", "options": []}]
    monkeypatch.setattr(ont, "list_properties", _fake_props)
    meta = await ont._instance_meta("demo_ds_obj")
    assert meta["datasource_id"] == 4
    assert meta["materialized"] is True


@pytest.mark.asyncio
async def test_instance_search_passes_datasource_id(monkeypatch):
    """datasource_id 非空时，实例查询必须走 _exec_on（而不是系统库 _exec）。"""
    seen = {}
    async def _fake_meta(code):
        return {"code": code, "name": "演示", "table": "DEMO_TABLE", "key_prop": "id",
                "name_prop": "name", "edits_enabled": False, "datasource_id": 4,
                "props": [{"code": "id", "name": "ID", "prop_type": "number", "options": []}],
                "cols": ["id"], "real_cols": {"id", "name"}, "materialized": True}
    async def _fake_exec_on(ds_id, sql, params=None):
        seen["ds_id"] = ds_id
        class _R:
            def fetchall(self): return []
            def fetchone(self): return (0,)
            def scalar(self): return 0
        return _R()
    monkeypatch.setattr(ont, "_instance_meta", _fake_meta)
    monkeypatch.setattr(ont, "_exec_on", _fake_exec_on)
    r = await ont.instance_search("demo_ds_obj", limit=10)
    assert seen.get("ds_id") == 4
    assert r["ok"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_datasource_instance.py -q`
Expected: FAIL（`_instance_meta` 返回体无 `datasource_id`；`instance_search` 未走 `_exec_on`）

- [ ] **Step 3: 实现**

- `_instance_meta`：SELECT 追加 `,COALESCE(datasource_id,0)`；`table = row[4] or row[0]` 不变；返回体加 `"datasource_id": int(row[6] or 0)`；调用 `_table_columns(table, datasource_id=row[6] or None)`。
- `_table_columns(table, datasource_id=None)`：`datasource_id` 非空时用 `query.executor.build_engine` 反射（`inspect`），否则维持现状。
- 四个方法内所有 `await _exec(...)` 改为 `await _exec_on(meta.get("datasource_id"), ...)`（`instance_pivot` 用 `mine`/`other` 各自的 `datasource_id`，起点查询用 `mine`、对端查询用 `other`）。

- [ ] **Step 4: 跑测试 + 回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_datasource_instance.py tests/test_query_object.py tests/test_query_object_multihop.py -q`
Expected: PASS（新测试通过，且既有对象查询测试不回归）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/ontology/service.py backend/tests/test_ontology_datasource_instance.py
git commit -m "feat(ontology): 实例层支持按 datasource_id 跨库查询"
```

---

### Task 4: `upsert_object` 校验 `datasource_id` 与 `backing_table` 白名单

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/service.py`（`upsert_object`，:1524-1600 附近）
- Test: `backend/tests/test_ontology_object_datasource_validate.py`（新建）

**Interfaces:**
- Consumes: `query.service.list_ds_schema(datasource_id)`（返回 `[{table, columns}]`，延迟导入）
- Produces: `upsert_object(data)` 在 `datasource_id` 非空且 `backing_table` 不在该数据源 schema 白名单时抛 `CustomException(msg=...)`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ontology_object_datasource_validate.py
import pytest
from app.core.exceptions import CustomException
from app.plugin.module_ai.ontology import service as ont


@pytest.mark.asyncio
async def test_upsert_object_rejects_unknown_backing_table(monkeypatch):
    from app.plugin.module_ai.query import service as qs
    async def _fake_schema(ds_id):
        return [{"table": "FUEL_CB_COALBALANCE", "columns": [{"name": "ID"}]}]
    monkeypatch.setattr(qs, "list_ds_schema", _fake_schema)
    with pytest.raises(CustomException):
        await ont.upsert_object({"code": "__t_bad__", "name": "坏对象",
                                 "datasource_id": 4, "backing_table": "NOT_EXIST_TABLE"})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_object_datasource_validate.py -q`
Expected: FAIL（当前不校验，未抛 `CustomException`）

- [ ] **Step 3: 实现**

在 `upsert_object` 写入前插入校验（`datasource_id` 非空时）：

```python
    dx = data.get("datasource_id")
    bt = str(data.get("backing_table") or "").strip()
    if dx and bt:
        from ..query import service as _qs
        rows = await _qs.list_ds_schema(int(dx))
        allowed = {r["table"] for r in rows}
        if bt not in allowed:
            raise CustomException(msg=f"支撑表 {bt} 不在数据源 #{dx} 的 schema 内")
```

（顶部若未导入 `CustomException` 则补 `from app.core.exceptions import CustomException`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ontology_object_datasource_validate.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/ontology/service.py backend/tests/test_ontology_object_datasource_validate.py
git commit -m "feat(ontology): 校验对象支撑表属于目标数据源 schema"
```

---

## Self-Review

**1. Spec 覆盖**：§2.1（对象支持自定义数据源）→ Task 4；§2.2（指标绑定列）→ Task 1；§2.3（评测 `dataset`）→ Task 1；§4.1（实例层按 `datasource_id`）→ Task 2/3。S2–S4 另行成 plan。
**2. Step 扫描**：每步单一动作、有可验证结果；无"处理边界情况"式空话。
**3. 类型一致**：`_exec_on(datasource_id, sql, params) -> _Rows` 在 Task 2 定义、Task 3 消费，签名一致；`_instance_meta` 新增 `datasource_id` 字段在 Task 3 定义并被同任务消费。
**4. Review Focus 对应**：①大小写→Task 3 测试用 `DEMO_TABLE`；②空 ds 不变→Task 2 `test_exec_on_system_when_no_ds` + Task 3 回归；③跨库仍走权限→Task 3 保留 `_sec.*` 调用（回归测试覆盖）；④连接不泄漏→Task 2 断言 `disposed`；⑤未物化降级→Task 3 `_instance_meta` 的 `materialized` 分支（既有逻辑，回归覆盖）。
**5. 比例**：plan 与 spec 相称，代码块以签名/断言为主，未转写实现。
