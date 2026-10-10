# 问数召回服务 · 阶段 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把问数的 schema linking 从「分级短路 + 字典序截断」改成「多路并行召回 + RRF 融合 + 阈值 + 按分数取 top_k」，并让召回单元带中文语义。

**Architecture:** 新增 `recall.py` 承载「单元构建 + 四路召回通道 + RRF 融合」的纯逻辑（便于单测）；`service.py` 只做编排（DDL、配置、trace、替换 `_semantic_tables_uncached`）。召回单元来自「本体语义层 + 资产元数据 + 指标/术语」，落 `ai_query_recall_units` 表。

**Tech Stack:** Python 3.13、SQLAlchemy 2.0 async、PostgreSQL + pgvector（生产/开发）、SQLite（测试，**无 pgvector**）、pytest。

**Spec:** `docs/superpowers/specs/2026-10-10-query-recall-service-design.md`

## Global Constraints

- 后端命令在 `backend/` 下用 `uv run`；测试 `uv run pytest`。
- **不改 `ask` / `stream` 的对外接口与返回结构**；`_semantic_tables_uncached(question, schema, metrics, terms) -> list[str]` 的签名与返回类型保持不变。
- 新增配置项默认值必须保证**不配置也能工作**（`recall_enabled=true`、`recall_top_k=12`、`recall_min_score=0`、权重见 spec §4.8）。
- **测试环境是 SQLite，没有 pgvector**：向量通道必须**可降级**（失败返回空列表 + 告警日志），其余通道照常工作；单测不得依赖 PG 或外部嵌入服务。
- 嵌入统一走 `app.plugin.module_ai.knowledge.embedding.embed_texts(texts, model_id=None) -> list[list[float]]`（失败时自带确定性回退）。
- 配置统一用 `service.py:5020-5042` 的 `_cfg()/_cfg_bool()/_cfg_int()/_cfg_float()`。
- 表 DDL 幂等，沿用 `_ensure_concept_table` 的写法（`async_db_session.begin()` + `CREATE TABLE IF NOT EXISTS`）。
- 注释/文档/提交信息一律中文；提交信息 `type(scope): 中文描述`。

## Review Focus

以下是 spec 隐含、但**不会被主流程单测自然覆盖**的失败模式；每一条都在下面指定的任务里配了测试：

1. **单元表为空（尚未重建）** → 召回必须仍能靠关键词/本体/实体通道工作，不能整体失效。（Task 6）
2. **问题与所有单元都无关** → 必须回退「核心业务表」而非返回空集合（空集合会让 prompt 无表可用）。（Task 6）
3. **同一问题连续两次调用** → 结果必须完全一致（确定性）。（Task 6）
4. **pgvector 不可用**（SQLite / 扩展缺失） → 向量通道降级为空，其余通道照常。（Task 4、Task 6）
5. **同一张表被多路命中** → RRF 应累加权重，而不是产生重复表项。（Task 1）

---

### Task 1: RRF 融合器（纯函数）

**Files:**
- Create: `backend/app/plugin/module_ai/query/recall.py`
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `fuse_rrf(channels: dict[str, list[str]], weights: dict[str, float] | None = None, k: int = 60) -> list[tuple[str, float]]`
    返回按分数降序的 `(表名, 分数)`；同分时按表名字典序稳定排序（保证确定性）。
  - 默认权重常量 `DEFAULT_WEIGHTS = {"vector": 1.0, "keyword": 0.8, "ontology": 1.2, "entity": 0.6}`

- [ ] **Step 1: 写失败测试**

```python
from app.plugin.module_ai.query.recall import DEFAULT_WEIGHTS, fuse_rrf


def test_rrf_single_channel_preserves_order():
    out = fuse_rrf({"keyword": ["a", "b", "c"]})
    assert [t for t, _ in out] == ["a", "b", "c"]


def test_rrf_multi_channel_accumulates_not_duplicates():
    out = fuse_rrf({"keyword": ["a", "b"], "ontology": ["b", "a"]})
    names = [t for t, _ in out]
    assert names == ["a", "b"]          # 无重复
    assert out[0][1] > 0


def test_rrf_ontology_weight_beats_keyword_at_equal_rank():
    out = fuse_rrf({"ontology": ["x"], "keyword": ["y"]})
    assert [t for t, _ in out] == ["x", "y"]   # ontology 权重 1.2 > keyword 0.8


def test_rrf_ignores_empty_and_unknown_channels():
    out = fuse_rrf({"keyword": ["a"], "vector": [], "nope": ["z"]})
    assert [t for t, _ in out] == ["a"]


def test_rrf_is_deterministic_on_ties():
    a = fuse_rrf({"keyword": ["b", "a"]})
    b = fuse_rrf({"keyword": ["b", "a"]})
    assert a == b
    assert DEFAULT_WEIGHTS["ontology"] > DEFAULT_WEIGHTS["keyword"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: FAIL — `ModuleNotFoundError: app.plugin.module_ai.query.recall`

- [ ] **Step 3: 实现 `fuse_rrf`**

`recall.py`：纯函数，无 IO。`score(t) = Σ_c weights.get(c, 0) / (k + rank_c(t))`（`rank` 从 1 起）；
未知通道权重取 `0`（即忽略）；输出前按 `(-score, table)` 排序保证确定性。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/recall.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): RRF 多路召回融合器"
```

---

### Task 2: 语义单元构建器（把三份资产变成可检索文本）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/recall.py`
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: `ontology/semantic.py` 的 `semantic_context(include_properties=True)`、`concepts()`、`object_table_map()`；问数的 `list_metrics` / `list_terms` / 资产列表。
- Produces:
  - `build_table_unit(table: str, meta: dict, columns: list[dict], kind: str = "table") -> dict`
    （`kind="ds_table"` 时用于外部数据源表，模板同表单元）
  - `build_object_unit(obj: dict, props: list[dict], rels: list[dict]) -> dict`
  - `build_metric_unit(m: dict) -> dict` / `build_term_unit(t: dict) -> dict`
  - `build_concept_unit(c: dict) -> dict`（概念名/描述/同义词/涉及表）
  - 统一返回 `{"kind": str, "ref": str, "text": str, "meta": {"tables": [str], ...}}`
  - **`fewshot` 单元的构建推迟到阶段 5（闭环）**，本阶段不建。

- [ ] **Step 1: 写失败测试**

```python
from app.plugin.module_ai.query.recall import (
    build_metric_unit, build_object_unit, build_table_unit, build_term_unit,
)


def test_table_unit_text_carries_chinese_metadata():
    u = build_table_unit(
        "FUEL_CB_COALBALANCE",
        {"alias": "燃煤采购结算主表", "domain": "燃煤", "description": "存煤款结算"},
        [{"column_name": "COALMONEY", "description": "煤款金额"}],
    )
    assert u["kind"] == "table" and u["ref"] == "FUEL_CB_COALBALANCE"
    assert u["meta"]["tables"] == ["FUEL_CB_COALBALANCE"]
    for token in ("燃煤采购结算主表", "燃煤", "存煤款结算", "COALMONEY", "煤款金额"):
        assert token in u["text"]


def test_object_unit_text_carries_aliases_synonyms_and_relations():
    u = build_object_unit(
        {"code": "sales_order", "name": "销售订单", "table": "demo_sales",
         "aliases": ["订单", "销售单"], "synonyms": "销售额,成交额"},
        [{"code": "amount", "name": "销售额"}],
        [{"source": "demo_sales", "target": "demo_customer",
          "source_field": "customer_id", "target_field": "id", "card": "many_to_one"}],
    )
    assert u["kind"] == "object"
    assert u["meta"]["tables"] == ["demo_sales"]
    for token in ("销售订单", "订单", "销售单", "销售额", "demo_sales", "demo_customer"):
        assert token in u["text"]


def test_metric_and_term_units_are_minimal_but_complete():
    m = build_metric_unit({"key": "sales_amount", "name": "销售额", "sql_template": "SELECT 1", "unit": "元"})
    t = build_term_unit({"term": "产量", "metric_key": "output_count", "field_path": "t.qty"})
    assert m["kind"] == "metric" and "销售额" in m["text"] and "元" in m["text"]
    assert t["kind"] == "term" and "产量" in t["text"] and "output_count" in t["text"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_table_unit'`

- [ ] **Step 3: 实现四个构建函数**

按 spec §4.2 的模板拼 `text`；`meta["tables"]` 必须是**该单元对应的真实表**（表单元=自身；对象/属性单元=对象的支撑表；关系单元=源+目标表）。
模板用「｜」分隔字段，便于人读与检索。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/recall.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): 召回单元构建器（中文名/别名/同义词/关系）"
```

---

### Task 3: 单元表 + 重建（幂等，SQLite 无向量列时降级）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`（新增 `_ensure_recall_units_table` / `rebuild_recall_units`）
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: Task 2 的构建函数；`embed_texts`；`async_db_session`。
- Produces:
  - `AiQueryService._ensure_recall_units_table() -> None`（幂等 DDL）
  - `AiQueryService.rebuild_recall_units() -> dict` → `{"units": int, "embedded": int, "version": int}`
  - 表 `ai_query_recall_units(kind, ref, text, meta JSONB, embedding vector(2560), version BIGINT, is_deleted, created_time, updated_time)`，`UNIQUE(kind, ref)`

- [ ] **Step 1: 写失败测试**

```python
import asyncio


def test_rebuild_is_idempotent_and_upserts():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        await S._ensure_recall_units_table()
        first = await S.rebuild_recall_units()
        second = await S.rebuild_recall_units()
        assert first["units"] > 0
        assert second["units"] == first["units"]      # 幂等：不重复膨胀
        from sqlalchemy import text
        from app.core.database import async_db_session
        async with async_db_session() as db:
            n = (await db.execute(text("SELECT count(*) FROM ai_query_recall_units"))).scalar()
        assert n == first["units"]

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py::test_rebuild_is_idempotent_and_upserts -q`
Expected: FAIL — `AttributeError: type object 'AiQueryService' has no attribute '_ensure_recall_units_table'`

- [ ] **Step 3: 实现**

- `_ensure_recall_units_table`：`CREATE TABLE IF NOT EXISTS`（沿用 `_ensure_concept_table` 写法）。**`embedding` 列只在 PG 上创建**：`DATABASE_TYPE == "postgres"` 时带 `vector(2560)`，否则不建该列（SQLite 无 pgvector）。
- `rebuild_recall_units`：收集单元（资产表/字段 + 本体对象/属性/关系 + 指标/术语 + 概念）→ `upsert`（`ON CONFLICT (kind, ref) DO UPDATE`）→ PG 上调用 `embed_texts` 写 `embedding`，SQLite 上跳过（`embedded=0`）。
- 写入 `version = int(time.time())`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): 语义单元表与重建（幂等，无 pgvector 时降级）"
```

---

### Task 4: 向量通道（PG 直查 pgvector；不可用时降级）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/recall.py`（查询 SQL 构造，纯字符串）
- Modify: `backend/app/plugin/module_ai/query/service.py`（`_recall_vector` 执行）
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: Task 3 的表；`embed_texts`。
- Produces:
  - `AiQueryService._recall_vector(question: str, top_n: int) -> list[str]`（按相似度降序的**去重表名**；不可用时返回 `[]`）

- [ ] **Step 1: 写失败测试**

```python
def test_vector_channel_degrades_without_pgvector():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        # 测试库是 SQLite，没有 pgvector → 必须优雅降级为空列表，且不抛异常
        assert await S._recall_vector("各框架下的训练模型数量", 8) == []

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py::test_vector_channel_degrades_without_pgvector -q`
Expected: FAIL — `AttributeError: ... has no attribute '_recall_vector'`

- [ ] **Step 3: 实现**

`_recall_vector`：`recall_enabled` 关或非 PG 或无 embedding 列 → 直接 `return []`；
否则 `qvec = (await embed_texts([question]))[0]` → 执行
`SELECT meta->'tables' AS t FROM ai_query_recall_units WHERE is_deleted=false ORDER BY embedding <=> :q LIMIT :n`
→ 展平 `tables`、去重、保序。整段 `try/except` 包住并 `log.warning`（沿用 `_pgv_search` 的降级风格）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（10 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/recall.py backend/app/plugin/module_ai/query/service.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): 向量召回通道（PG 直查 pgvector，可降级）"
```

---

### Task 5: 关键词 / 本体强信号 / 实体 三路通道

**Files:**
- Modify: `backend/app/plugin/module_ai/query/recall.py`
- Modify: `backend/app/plugin/module_ai/query/service.py`
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: `_relevant_tables`（关键词+中文注释打分）、`semantic_context`、`object_table_map`、`_cfg_entity_map`。
- Produces:
  - **纯函数（`recall.py`，接收显式数据，便于单测）**：
    - `recall_keyword(question, schema, metrics, terms) -> list[str]`（按分数降序）
    - `recall_ontology(question, objects, table_map) -> list[str]`（顺序：别名命中 > 同义词命中 > 属性名命中 > 对象名命中）
    - `recall_entity(question, entity_map, schema) -> list[str]`
  - **服务薄包装（`service.py`，负责取数据后调上面的纯函数，供 Task 6 编排调用）**：
    - `AiQueryService._recall_keyword(question) -> list[str]`
    - `AiQueryService._recall_ontology(question) -> list[str]`
    - `AiQueryService._recall_entity(question) -> list[str]`
    （与 Task 4 的 `_recall_vector(question, top_n)` 统一为四个 `_recall_*` 包装，Task 6 只依赖这四个。）

- [ ] **Step 1: 写失败测试**

```python
from app.plugin.module_ai.query.recall import recall_ontology


def test_ontology_channel_orders_alias_above_object_name():
    objects = [
        {"code": "sales_order", "name": "销售订单", "aliases": ["订单"], "synonyms": "", "table": "demo_sales"},
        {"code": "camera", "name": "摄像头", "aliases": [], "synonyms": "", "table": "video_cameras"},
    ]
    table_map = {"demo_sales": "sales_order", "video_cameras": "camera"}
    # 「订单」是别名命中，「摄像头」是对象名命中 → 别名必须排在前面
    assert recall_ontology("订单和摄像头各多少", objects, table_map) == ["demo_sales", "video_cameras"]
    # 只出现对象名时也能召回（权重低，但不丢）
    assert recall_ontology("摄像头有多少", objects, table_map) == ["video_cameras"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: FAIL — `ImportError: cannot import name 'recall_ontology'`

- [ ] **Step 3: 实现三路**

- `recall_keyword`：复用 `_relevant_tables` 的打分（表名 6 / 中文注释 5 / 列名 3 / 片段 1），按分数降序返回表名（**不再截断**，交给 RRF）。
- `recall_ontology`：三级命中分档（别名 > 同义词 > 属性名 > 对象名），同档按对象顺序稳定排序；**保留对象名档**（旧实现为防噪声只用别名且限 3 张，现在靠权重+RRF 控制，不再硬限）。
- `recall_entity`：`_cfg_entity_map` 命中即返回（顺序稳定）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（12 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/recall.py backend/app/plugin/module_ai/query/service.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): 关键词/本体强信号/实体三路召回通道"
```

---

### Task 6: 编排改写 —— 并行四路 + RRF + 阈值 + 按分数 top_k

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`（`_semantic_tables_uncached` 约 6244-6367）
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: Task 1/4/5 的全部产物；`_cfg_*`。
- Produces: `AiQueryService._semantic_tables_uncached(question, schema=None, metrics=None, terms=None) -> list[str]`（**签名与返回类型不变**）。

- [ ] **Step 1: 写失败测试**

```python
def test_recall_takes_topk_by_score_not_alphabetical(monkeypatch):
    """决定性：按分数取 top_k，而不是 sorted() 的字典序。旧实现会给 aaa_early。"""
    async def _run():
        from app.plugin.module_ai.query import service as S

        async def _vec(cls, q, n):
            return []

        async def _kw(cls, q):
            return ["zzz_late", "aaa_early"]

        async def _ont(cls, q):
            return ["zzz_late"]

        async def _ent(cls, q):
            return []

        for name, fn in (("_recall_vector", _vec), ("_recall_keyword", _kw),
                         ("_recall_ontology", _ont), ("_recall_entity", _ent)):
            monkeypatch.setattr(S.AiQueryService, name, classmethod(fn))
        monkeypatch.setattr(
            S.AiQueryService, "_cfg_int",
            classmethod(lambda cls, cfg, key, default: 1 if key == "recall_top_k" else default),
        )

        out = await S.AiQueryService._semantic_tables_uncached(
            "x", {"zzz_late": [], "aaa_early": []}, [], []
        )
        assert out[0] == "zzz_late"

    asyncio.run(_run())


def test_recall_falls_back_to_core_tables_when_nothing_matches():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        out = await S._semantic_tables_uncached("今天天气怎么样", None, None, None)
        assert out, "完全无匹配时必须回退核心业务表，不能返回空"

    asyncio.run(_run())


def test_recall_is_deterministic_across_calls():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        q = "每个摄像头各产生多少条告警"
        a = await S._semantic_tables_uncached(q, None, None, None)
        b = await S._semantic_tables_uncached(q, None, None, None)
        assert a == b

    asyncio.run(_run())


def test_recall_survives_empty_unit_table():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S
        from app.core.database import async_db_session
        from sqlalchemy import text

        async with async_db_session.begin() as db:
            await db.execute(text("DELETE FROM ai_query_recall_units"))
        out = await S._semantic_tables_uncached("在线摄像头有多少", None, None, None)
        assert "video_cameras" in out, "单元表为空时仍须靠关键词/本体通道召回"

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: `test_recall_takes_topk_by_score_not_alphabetical` FAIL（旧实现 `sorted({...})[:1]` 返回 `aaa_early`）

- [ ] **Step 3: 实现**

把 `_semantic_tables_uncached` 主体替换为：
1. 四路并行取候选：`vector` / `keyword` / `ontology` / `entity`（`asyncio.gather`，各自 try/except）；
2. `fuse_rrf(channels, weights)`，权重来自 `_cfg_float(cfg, "recall_w_*")`；
3. 过滤 `score >= recall_min_score` → 取前 `recall_top_k`；
4. 为空 → 回退核心业务表（`video_alarm_records/video_cameras/...`）；
5. **保留** KG/AGE 扩表（`:6349-6366`）作为补充，但**不参与计分**（放在截断之后追加，且受 top_k 上限约束）；
6. **删除** `if not tables:` 短路与 `sorted(tables)[:top_k]`。

`recall_enabled=false` 时退回旧实现（保留旧代码路径，便于灰度回滚）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（16 passed）

- [ ] **Step 5: 全量回归**

Run: `cd backend && uv run pytest -q`
Expected: 与基线一致（仅 3 个既有 Alembic 失败）

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/tests/test_query_recall.py
git commit -m "refactor(ai-query): 召回改为并行四路+RRF融合+阈值（去掉短路与字典序截断）"
```

---

### Task 7: 配置项 seed + rebuild/probe 端点

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`（`_cfg` 默认值 seed，约 4994 附近）
- Modify: `backend/app/plugin/module_ai/query/controller.py`
- Test: `backend/tests/test_query_recall.py`

**Interfaces:**
- Consumes: Task 3 的 `rebuild_recall_units`。
- Produces:
  - 配置键（默认值）：`recall_enabled=true`、`recall_top_k=12`、`recall_min_score=0`、
    `recall_w_vector=1.0`、`recall_w_keyword=0.8`、`recall_w_ontology=1.2`、`recall_w_entity=0.6`、`recall_trace_enabled=true`
  - `POST /api/v1/ai/query/recall/rebuild` → `SuccessResponse(data={"units": int, ...})`
  - `GET /api/v1/ai/query/recall/probe?question=...` → `SuccessResponse(data={"final": [...], "channels": {...}})`

- [ ] **Step 1: 写失败测试**

```python
def test_recall_config_defaults_seeded():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        cfg = await S._cfg()
        assert cfg["recall_enabled"] == "true"
        assert int(cfg["recall_top_k"]) == 12

    asyncio.run(_run())


def test_probe_endpoint_returns_final_tables(test_client, auth_headers):
    r = test_client.get(
        "/api/v1/ai/query/recall/probe",
        params={"question": "在线摄像头有多少"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert "final" in r.json()["data"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: FAIL — `KeyError: 'recall_enabled'` / 404

- [ ] **Step 3: 实现**

配置默认值加进 `_cfg` 的 seed 字典；controller 加两个路由（权限沿用 `module_ai:query:ask`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_query_recall.py -q`
Expected: PASS（18 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/app/plugin/module_ai/query/controller.py backend/tests/test_query_recall.py
git commit -m "feat(ai-query): 召回配置项与 rebuild/probe 端点"
```

---

### Task 8: Recall@k 评测 + 阶段 1 量化验收

**Files:**
- Create: `backend/app/plugin/module_ai/query/recall_eval.py`
- Test: 无（脚本，靠运行验证）

**Interfaces:**
- Consumes: `NL2SQL_GOLDEN`（98 题，含 `gold` SQL）、`_semantic_tables_uncached`。
- Produces: `python -m app.plugin.module_ai.query.recall_eval --k=8` 输出 `Recall@8` 与逐题缺失表。

- [ ] **Step 1: 实现脚本**

从每题 `gold` SQL 用正则抽表名（`FROM/JOIN\s+([a-z_][a-z0-9_]*)`）并与 schema 求交作为 ground truth；对每题调 `_semantic_tables_uncached`（**不调 LLM**）算命中率。

- [ ] **Step 2: 跑基线（改前对照）**

先 `git stash` 本次改动 → 运行脚本记录基线 → 恢复。
Run: `uv run python -m app.plugin.module_ai.query.recall_eval --k=8`
Expected: 输出基线 `Recall@8`（记录数字）

- [ ] **Step 3: 跑改后**

Run: `uv run python -m app.plugin.module_ai.query.recall_eval --k=8`
Expected: `Recall@8` **高于基线**；逐题缺失表里不再出现「已被召回却丢失」的表

- [ ] **Step 4: 跑完整基准（需后端 + LLM）**

Run: `uv run python -m app.plugin.module_ai.query.benchmark --nl2sql`
Expected: 结果精度 **≥97%**（基线 94.9%）；专项题「各框架下的训练模型数量」通过；P50 不劣化

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/recall_eval.py
git commit -m "test(ai-query): Recall@k 召回评测脚本与阶段1量化结果"
```
