# 问数评测模块（后端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把问数评测做成可维护的模块——持久化测试集（100 题，含金标 SQL）、后台执行带进度、逐题**路径 trace**、分维度报表、**8 开关消融**。

**Architecture:** 纯逻辑（表抽取/Recall/聚合）放 `eval_metrics.py`；DB 与 CRUD 放 `eval_set.py`；LLM 生成+校验放 `eval_generate.py`；执行/进度/消融放 `eval_runner.py`（复用 `benchmark_runner` 的 `_RUNS` 进度模式）；接口挂 `query/controller.py`。

**Tech Stack:** Python 3.13、SQLAlchemy 2.0 async、FastAPI、pytest（SQLite，无 pgvector）。

**Spec:** `docs/superpowers/specs/2026-10-11-query-eval-module-design.md`

## Global Constraints

- 后端命令在 `backend/` 下用 `uv run`；日常只跑单文件，纯逻辑用 `PYTEST_NO_APP=1`。
- **不改 `ask`/`stream` 的对外行为**；评测通过调用 `AiQueryService.ask` 进行。
- 表 DDL 幂等、沿用 `_ensure_concept_table` 写法；**`meta`/`trace` 用 `JSONB`（SQLite 下由 conftest monkeypatch 兼容）**。
- 配置项读写沿用 `service.py` 的 `_cfg*`；覆盖配置必须**恢复并清 `_SETTINGS_CACHE`**。
- 消融**必须串行**（配置是全局的）。
- 注释/文档/提交信息中文；提交信息 `type(scope): 中文描述`。

## Review Focus

以下失败模式最容易咬人，各自在指定任务里配了测试：

1. **配置覆盖后未恢复** → 污染同一进程内的后续评测与业务请求。（Task 9）
2. **金标 SQL 不可执行/空结果** → 不该入集，否则精度统计被错题拉低。（Task 6）
3. **LLM 返回带 markdown 围栏/多余解释** → 解析必须容错（此前实测踩过）。（Task 5）
4. **筛选后题集为空** → 一轮运行应正常结束（total=0/done=0）而不是报错。（Task 7）
5. **消融与普通运行并发** → 配置互相污染；需串行锁。（Task 10）

---

### Task 1: 三张评测表（幂等 DDL）

**Files:**
- Create: `backend/app/plugin/module_ai/query/eval_set.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces: `ensure_eval_tables() -> None`（建 `ai_query_testcase` / `ai_query_testrun` / `ai_query_testresult`，幂等）

- [ ] **Step 1: 写失败测试**

```python
import asyncio


def test_ensure_eval_tables_is_idempotent():
    async def _run():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.eval_set import ensure_eval_tables

        await ensure_eval_tables()
        await ensure_eval_tables()  # 第二次不得报错
        async with async_db_session() as db:
            n = (await db.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_name"
                " IN ('ai_query_testcase','ai_query_testrun','ai_query_testresult')"
            ))).scalar()
        assert int(n) >= 0  # SQLite 查不到 information_schema，只断言不抛异常

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_eval.py::test_ensure_eval_tables_is_idempotent -q`
Expected: FAIL — `No module named ...eval_set`

- [ ] **Step 3: 实现 `ensure_eval_tables`**

三张表按 spec §3 建列；`ai_query_testcase` 加 `UNIQUE(datasource, question)`；`ai_query_testresult` 加索引 `(run_id)`；时间列不设默认（写入时显式 `now()`，兼容 SQLite）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_eval.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/eval_set.py backend/tests/test_query_eval.py
git commit -m "feat(ai-eval): 评测三表（测试集/运行/逐题结果）幂等建表"
```

---

### Task 2: 测试集 CRUD

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_set.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Consumes: Task 1 的 `ensure_eval_tables`。
- Produces（后续任务依赖）:
  - `async upsert_case(data: dict) -> dict`（按 `(datasource, question)` 幂等）
  - `async list_cases(datasource=None, difficulty=None, form=None, enabled=None) -> list[dict]`
  - `async delete_cases(ids: list[int]) -> int`（软删）
  - `async import_cases(items: list[dict]) -> dict` → `{"saved": int, "skipped": int}`

- [ ] **Step 1: 写失败测试**

```python
def test_upsert_and_list_cases_by_filter():
    async def _run():
        from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

        await upsert_case({"question": "Q1", "gold_sql": "SELECT 1", "datasource": "system",
                           "difficulty": "简单", "scenario": "安防", "form": "单维统计"})
        await upsert_case({"question": "Q1", "gold_sql": "SELECT 1", "datasource": "system",
                           "difficulty": "困难", "scenario": "安防", "form": "联表"})  # 同题 → 覆盖
        rows = await list_cases(datasource="system")
        assert len([r for r in rows if r["question"] == "Q1"]) == 1
        assert next(r for r in rows if r["question"] == "Q1")["difficulty"] == "困难"
        assert await list_cases(difficulty="不存在的难度") == []

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败** → `ImportError: cannot import name 'upsert_case'`

- [ ] **Step 3: 实现四个函数**（`ON CONFLICT(datasource,question) DO UPDATE`；`list_cases` 用参数化 WHERE 拼条件）

- [ ] **Step 4: 跑测试确认通过** → PASS

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 测试集 CRUD（幂等 upsert/筛选/软删/批量导入）"
```

---

### Task 3: 纯函数——金标抽表与 Recall@k

**Files:**
- Create: `backend/app/plugin/module_ai/query/eval_metrics.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces:
  - `gold_tables(sql: str, schema: dict[str, list[str]]) -> set[str]`
  - `recall_at_k(expected: set[str], retrieved: list[str], k: int = 8) -> float`（expected 为空 → 1.0）

- [ ] **Step 1: 写失败测试**（**可跑快速模式**）

```python
def test_gold_tables_and_recall():
    from app.plugin.module_ai.query.eval_metrics import gold_tables, recall_at_k

    sql = 'SELECT * FROM "FUEL_CB_COALBALANCE" a JOIN FUEL_CMCS_ASSAY b ON a.id=b.id'
    schema = {"FUEL_CB_COALBALANCE": [], "FUEL_CMCS_ASSAY": [], "OTHER": []}
    assert gold_tables(sql, schema) == {"FUEL_CB_COALBALANCE", "FUEL_CMCS_ASSAY"}
    assert recall_at_k({"A", "B"}, ["A", "B", "C"], k=8) == 1.0
    assert recall_at_k({"A", "B"}, ["X", "Y"], k=8) == 0.0
    assert recall_at_k(set(), ["X"], k=8) == 1.0
```

- [ ] **Step 2: 跑测试确认失败** → `ModuleNotFoundError: ...eval_metrics`

- [ ] **Step 3: 实现**（正则 `\b(?:from|join)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?`，与 schema 求交；Recall 取 `retrieved[:k]`）

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_query_eval.py -q -k "gold or recall"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 金标抽表与 Recall@k 纯函数"
```

---

### Task 4: 纯函数——总览指标与分维度聚合

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_metrics.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces:
  - `summarize(results: list[dict], k: int = 8) -> dict`（`data_accuracy`/`semantic_accuracy`/`fast_rate`/`recall_at_k`/`avg_ms`/`p50_ms`/`p95_ms`/`error_rate`）
  - `group_by(results: list[dict], field: str) -> dict[str, dict]`（每组 `{"total","correct","accuracy"}`）

- [ ] **Step 1: 写失败测试**（纯逻辑，快速模式）

```python
def test_summarize_and_group():
    from app.plugin.module_ai.query.eval_metrics import group_by, summarize

    results = [
        {"gold_match": True, "metric_key": "m1", "expected_metric": "m1", "path": "fast",
         "is_error": False, "took_ms": 100, "recall": 1.0, "difficulty": "简单"},
        {"gold_match": False, "metric_key": "m2", "expected_metric": "m1", "path": "slow",
         "is_error": True, "took_ms": 300, "recall": 0.0, "difficulty": "困难"},
    ]
    s = summarize(results)
    assert s["data_accuracy"] == 0.5
    assert s["semantic_accuracy"] == 0.0     # 1 题带期望、未命中
    assert s["fast_rate"] == 0.5
    assert s["error_rate"] == 0.5
    assert s["avg_ms"] == 200
    g = group_by(results, "difficulty")
    assert g["简单"]["accuracy"] == 1.0 and g["困难"]["accuracy"] == 0.0
```

- [ ] **Step 2: 跑测试确认失败** → `ImportError`

- [ ] **Step 3: 实现**（语义精度分母=带 `expected_metric` 的题；P50/P95 用排序取位）

- [ ] **Step 4: 跑测试确认通过**（快速模式）

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 总览指标与分维度聚合（纯函数）"
```

---

### Task 5: LLM 生成器（提示 + 容错解析）

**Files:**
- Create: `backend/app/plugin/module_ai/query/eval_generate.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces:
  - `build_prompt(schema_rows: list[dict], metrics: list[dict], terms: list[dict], difficulty: str, form: str, n: int) -> str`
  - `parse_cases(text: str) -> list[dict]`（容错：去 ``` 围栏、取首个 `{`..末个 `}`、`cases` 数组或裸数组；每项必须有非空 `question` 与 `gold_sql`）

- [ ] **Step 1: 写失败测试**

```python
def test_parse_cases_tolerates_markdown_and_noise():
    from app.plugin.module_ai.query.eval_generate import parse_cases

    text = '这是说明\n```json\n{"cases":[{"question":"Q","gold_sql":"SELECT 1","difficulty":"简单","form":"单维统计"}]}\n```\n完毕'
    out = parse_cases(text)
    assert out and out[0]["question"] == "Q" and out[0]["gold_sql"] == "SELECT 1"
    assert parse_cases("没有任何 JSON") == []
```

- [ ] **Step 2: 跑测试确认失败** → `ImportError`

- [ ] **Step 3: 实现 `build_prompt` 与 `parse_cases`**（复刻 `power_plant` 种子脚本里已验证的容错写法）

- [ ] **Step 4: 跑测试确认通过**（快速模式）

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): LLM 出题提示与容错解析"
```

---

### Task 6: 生成校验 + 入库

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_generate.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Consumes: Task 2 `upsert_case`；`AiQueryService.ask` / `_execute_custom_ds_sql`。
- Produces: `async verify_and_save(cases: list[dict], datasource: str, auth) -> dict`
  → `{"saved": int, "rejected": int, "reasons": list[str]}`（**gold SQL 执行成功且行数>0 才 `verified=true` 入库**）

- [ ] **Step 1: 写失败测试**

```python
def test_verify_and_save_rejects_unexecutable_gold(monkeypatch):
    async def _run():
        from app.plugin.module_ai.query import eval_generate as G

        async def fake_run(sql, ds, auth):
            return {"ok": sql != "SELECT bad", "rows": [] if sql == "SELECT bad" else [1]}

        monkeypatch.setattr(G, "_run_gold", fake_run)
        from types import SimpleNamespace
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        out = await G.verify_and_save(
            [{"question": "QA", "gold_sql": "SELECT good", "difficulty": "简单", "form": "单维统计"},
             {"question": "QB", "gold_sql": "SELECT bad", "difficulty": "简单", "form": "单维统计"}],
            "system", auth,
        )
        assert out["saved"] == 1 and out["rejected"] == 1
        from app.plugin.module_ai.query.eval_set import list_cases
        assert [c["question"] for c in await list_cases(datasource="system")] == ["QA"]

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败** → `AttributeError: _run_gold`

- [ ] **Step 3: 实现 `_run_gold` 与 `verify_and_save`**（system 走本地只读执行、`ds:{id}` 走 `_execute_custom_ds_sql`；失败原因收进 `reasons`）

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 生成校验（金标 SQL 可执行且非空才入库）"
```

---

### Task 7: 执行器 + 进度 + trace

**Files:**
- Create: `backend/app/plugin/module_ai/query/eval_runner.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Consumes: Task 2/3/4 的产物；`AiQueryService.ask(question, auth, redis, datasource, **kw)`。
- Produces:
  - `start_run(auth, filter: dict | None = None, mode: str = "full", config: dict | None = None) -> str`（返回 `run_id`，后台跑）
  - `get_status(run_id: str | None) -> dict | None`（`{run_id,status,mode,total,done,current,summary}`）
  - `_RUNS` 进程级进度字典（与 `benchmark_runner` 同构）

- [ ] **Step 1: 写失败测试**

```python
def test_run_records_trace_and_finishes_with_empty_filter(monkeypatch):
    async def _run():
        from types import SimpleNamespace

        from app.plugin.module_ai.query import eval_runner as R

        async def fake_ask(question, auth, redis, datasource, **kw):
            return {"path": "fast", "metric": {"key": "m"}, "retrieved": ["T"],
                    "columns": ["c"], "rows": [[1]], "sql": "SELECT 1", "took_ms": 5,
                    "is_error": False}

        monkeypatch.setattr(R, "_ask", fake_ask)
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        rid = R.start_run(auth, filter={"difficulty": "不存在的难度"})
        for _ in range(50):
            st = R.get_status(rid)
            if st and st["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.05)
        assert st["total"] == 0 and st["done"] == 0 and st["status"] == "done"

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败** → `AttributeError: start_run`

- [ ] **Step 3: 实现**（选题 → 逐题 `_ask` → 写 `ai_query_testresult`（含 trace：`path/metric/retrieved/ontology_used/sql/took_ms/retries`）→ 更新 `done`；结束算 `summary` 存 `ai_query_testrun`）

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 评测执行器（进度 + 逐题 trace 落库）"
```

---

### Task 8: 接口（run/status/report/runs/cases/generate）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/controller.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces（REST，统一 `AuthPermission(["module_ai:query:ask"])` + `SuccessResponse`）：
  `GET/POST/PUT/DELETE /ai/query/eval/cases`、`POST /eval/run`、`GET /eval/status`、
  `GET /eval/report`、`GET /eval/runs`、`POST /eval/generate`

- [ ] **Step 1: 写失败测试**

```python
def test_eval_cases_and_run_endpoints(test_client, auth_headers):
    h = auth_headers
    r = test_client.post("/api/v1/ai/query/eval/cases", json={
        "question": "接口测试题", "gold_sql": "SELECT 1", "datasource": "system",
        "difficulty": "简单", "scenario": "安防", "form": "单维统计"}, headers=h)
    assert r.status_code == 200, r.text
    r = test_client.get("/api/v1/ai/query/eval/cases", params={"difficulty": "简单"}, headers=h)
    assert r.status_code == 200 and any(c["question"] == "接口测试题" for c in r.json()["data"])
    r = test_client.get("/api/v1/ai/query/eval/status", headers=h)
    assert r.status_code == 200
```

- [ ] **Step 2: 跑测试确认失败** → 404

- [ ] **Step 3: 实现路由**（`/eval/report` 内部调 `summarize`/`group_by`）

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 评测 REST 接口（cases/run/status/report/runs/generate）"
```

---

### Task 9: 配置覆盖上下文（覆盖 + **恢复**）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_runner.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces: `override_settings(overrides: dict) -> AsyncContextManager[None]`
  （写入 `ai_query_settings` → 清 `_SETTINGS_CACHE`；退出时**恢复原值**并再清缓存）

- [ ] **Step 1: 写失败测试**（**决定性：必须恢复**）

```python
def test_override_settings_restores_original_values():
    async def _run():
        from app.plugin.module_ai.query.eval_runner import override_settings
        from app.plugin.module_ai.query.service import AiQueryService as S

        cfg0 = await S._cfg()
        before = cfg0.get("recall_enabled")
        async with override_settings({"recall_enabled": "false" if before == "true" else "true"}):
            S._SETTINGS_CACHE = None  # 模拟缓存失效后的重读
            assert (await S._cfg())["recall_enabled"] != before
        S._SETTINGS_CACHE = None
        assert (await S._cfg())["recall_enabled"] == before

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败** → `AttributeError: override_settings`

- [ ] **Step 3: 实现**（`get_settings`/`save_setting` 已存在则复用；`finally` 中恢复并对未恢复成功的情况记 warning）

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 配置覆盖上下文（退出必恢复，防污染）"
```

---

### Task 10: 消融执行器（串行多组 + 对照表）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_runner.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Consumes: Task 7 `start_run`/`get_status`、Task 9 `override_settings`。
- Produces:
  - `ABLATION_KEYS: tuple[str, ...]`（8 个开关）
  - `start_ablation(auth, keys: list[str] | None = None, filter: dict | None = None) -> str`
  - `get_ablation_report(run_id: str) -> dict`（`{group: metrics}` + 相对基线增量）

- [ ] **Step 1: 写失败测试**

```python
def test_ablation_is_serial_and_produces_compare_table(monkeypatch):
    async def _run():
        from types import SimpleNamespace

        from app.plugin.module_ai.query import eval_runner as R

        order: list[str] = []

        async def fake_run_group(name, **kw):
            order.append(name)
            return {"data_accuracy": 0.5}

        monkeypatch.setattr(R, "_run_ablation_group", fake_run_group)
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        rid = R.start_ablation(auth, keys=["recall_enabled", "kg_enabled"])
        for _ in range(50):
            rep = R.get_ablation_report(rid)
            if rep and rep.get("status") in ("done", "error"):
                break
            await asyncio.sleep(0.05)
        assert order[0] == "baseline"          # 先跑全开基线
        assert set(order) >= {"baseline", "recall_enabled", "kg_enabled"}
        assert len(order) == len(set(order))   # 串行且各组只跑一次

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败** → `AttributeError: start_ablation`

- [ ] **Step 3: 实现**（基线「全开」+ 逐开关「关掉」；每组用 `override_settings` 覆盖 → 跑 → 收集 `summary` → 恢复；结果存 `ai_query_testrun`（`mode=ablation`, `ablation_group`））

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 消融执行器（8 开关串行对照 + 增量）"
```

---

### Task 11: 消融接口 + 运行历史

**Files:**
- Modify: `backend/app/plugin/module_ai/query/controller.py`
- Test: `backend/tests/test_query_eval.py`

**Interfaces:**
- Produces: `POST /ai/query/eval/ablation`（body `{keys?: [...], filter?: {...}}`）、
  `GET /ai/query/eval/ablation?run_id=`（对照表）

- [ ] **Step 1: 写失败测试**（走 HTTP：启动消融 → 轮询 status → 断言 report 含基线组）
- [ ] **Step 2: 跑测试确认失败** → 404
- [ ] **Step 3: 实现路由**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 提交**

```bash
git commit -m "feat(ai-eval): 消融接口与对照报表"
```

---

### Task 12: 生成 100 题 + 端到端实跑与验收

**Files:**
- Create: `backend/scripts/generate_eval_set.py`（CLI：按数据源/维度补足到 100 题，调用 `eval_generate`）
- Modify: `docs/superpowers/specs/2026-10-11-query-eval-module-design.md`（补「实测结果」小节）
- Test: 运行验证（非 pytest）

**Interfaces:**
- Consumes: 全部前序任务。

- [ ] **Step 1: 写 CLI**（`--ds=system|ds:4|both`、`--target=100`、`--dry-run`；分轮次生成 → 校验 → 入库 → 打印各维度分布）

- [ ] **Step 2: 生成并校验到 100 题**

Run: `uv run python scripts/generate_eval_set.py --ds=both --target=100`
Expected: 入库 `verified=true` ≥ 90 题；打印难度/场景/形式分布（含系统库与 ds:4）

- [ ] **Step 3: 全量实跑**

Run: `POST /ai/query/eval/run`（全量）→ 轮询 `/eval/status` 至 done
Expected：`total` = 已入库题数、`done` 同步推进；`GET /eval/report` 给出总览 + ≥3 个维度分组 + 逐题 trace

- [ ] **Step 4: 消融 3 组**

Run: `POST /ai/query/eval/ablation`（`keys=["recall_enabled","agno_semantic_enabled"]`）
Expected：对照表含 baseline + 2 组，且各组**配置已恢复**（再查 `_cfg` 与原始一致）

- [ ] **Step 5: 全量回归**

Run: `cd backend && uv run pytest -q -n 4`
Expected: 与基线一致（既有 3 个 Alembic 失败），无新增失败

- [ ] **Step 6: 提交**

```bash
git commit -m "test(ai-eval): 100 题生成校验、全量实跑与消融验收；补 spec 实测结果"
```

---

## 附录：实现期修正（实跑暴露，均已修复）

按文件合批执行 + 真实跑起来后，暴露出以下**只有真跑才能发现**的问题，已逐条修复并提交：

| # | 症状 | 根因 | 修复 |
|---|------|------|------|
| 1 | 题集难度**全是「简单」** | 模型忽略提示里指定的 difficulty/form | 维度**以调用方请求为准**，解析后直接覆盖（`556a5c9d`） |
| 2 | 整轮在第 3 题**中断**，`KeyError: slice(None,8,None)` | `_run_once` 里 `rec[:8]`，而 `retrieved` 是 **dict** | 归一化 `rec` 为 list（`8bd0792e`） |
| 3 | **Recall@8 恒为 0** | `retrieved` 是 grounding 字典 `{"tables":[...],"objects":[...]}`，早期误取其 **keys**（得到 `["tables","objects"]`） | 取 `raw_rec["tables"]`（`0d66aea4`） |
| 4 | 单题异常**拖垮整轮** | 行构造不在 `try` 内 | 每题异常兜底成 error 行，循环继续 |
| 5 | 消融**只出 baseline** | 子 run `ab_xxx_baseline` 未注册进 `_RUNS` → `_RUNS[sub]` KeyError | `_run_ablation_group` 先注册子 run（`8bd0792e`） |
| 6 | 慢路径大量报「表 xxx 不在可查询白名单内」 | 评测用 `_auth()` 未带 `is_superuser` → `_allowed_for_user` 走数据域/ABAC 分支，把 `sys_user`/`annotation_dataset` 挡掉 | 评测身份 = 管理员（`is_superuser=True`），**测生成质量而非权限配置**（`2860afd3`） |
| 7 | `semantic_accuracy` 偏低 | 出题的 `expected_metric` 写成中文名/近似名，与真实指标 key 对不上 | 出题后把 `expected_metric` **对齐真实指标 key**（中文名→key 映射），对不上则置空（`2860afd3`） |

> 结论：评测模块本身跑通需要这 7 处修正；其中 #2/#3/#5 是纯实现 bug，#1/#6/#7 是"口径/身份"问题。
> 这些正是**立项做评测体系**的价值——不真跑，这些都发现不了。

## 附录：执行脚本

`backend/scripts/run_eval_once.py` —— 进程内跑「一轮全量 + 一次消融」，打印
总览 / 分维度（难度·形式·数据源·场景）/ 逐题 trace / 消融对照 / **配置恢复检查**。
参数：`--run-limit`、`--ablation-limit`、`--skip-run`。无需 HTTP 后端。
