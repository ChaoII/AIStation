# Agent 嵌入能力补齐（RAG 检索链路 v2）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AIStation 知识库链路升级为「向量索引真实、embedding 可观测、解析够用、可后台执行、可评测」的 v2，并修复全部正确性缺陷。

**Architecture:** `AiKnowledgeService` 保留为薄门面（对外签名不变），内部拆为 `parsing / chunking / embeddings / search / tasks / eval` 六个单一职责单元；检索统一走 `search()` 管线（召回 → 融合 → 过滤 → rerank → 上下文组装 → 埋点）。PG 走 `halfvec(2560)+HNSW` 与 `jiebacfg+GIN`，非 PG 走 Python 余弦与 grep 回退。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2；PostgreSQL 18 + pgvector 0.8.6 + pg_jieba + Apache AGE；agno `OpenAILikeEmbedder`；`mcp` SDK（MinerU）；`newspaper4k` / `python-docx` / `openpyxl` / `tiktoken`；Vue 3 + Element Plus。

**Spec:** `docs/superpowers/specs/2026-10-19-agent-embedding-rag-v2-design.md`

**分支：** `feat/agent-embedding-rag-v2`（worktree `ce637a/agent-embedding`，基于 `main@3cc318dd`）

## Global Constraints

- 回复、代码注释、提交信息一律中文；提交格式 `fix(ai): 中文描述` / `feat(ai): 中文描述`。
- 不新增第三方依赖：MinerU 用已有 `mcp`，网页正文用 `newspaper4k`，HTML 清洗用 `bleach`，token 用 `tiktoken`，向量用 `pgvector`。
- AI 调用只走 agno（`OpenAILikeEmbedder`）；禁止平行 LLM/embedding 实现。
- 数据库迁移手写 alembic（禁用 `autogenerate`）；存量库靠 `extensions.py` 幂等补列/建索引/建表。
- 测试默认跑在 SQLite（`conftest.py` 强制 `DATABASE_TYPE=sqlite`）：**任何 PG 专有路径必须有 SQLite 回退**；PG 断言用 `pytest.mark.skipif` 单独文件。
- 纯逻辑测试加 `PYTEST_NO_APP=1`（约 2s）；集成测试直接 `uv run pytest tests/<file> -q`。
- 前端只用 Element Plus 原生组件与 `--el-*` 变量；进度只更新对应行（禁止整表轮询刷新）；删除类操作二次确认。
- 所有新增/修改接口必须有 `AuthPermission` 校验；前端按钮配 `v-hasPerm`（字符串表达式，带内层单引号）。

## Review Focus

以下 5 类输入/故障最容易被实现者忽略，每类都必须在对应任务里被测试钉住：

1. **非 PG 环境（SQLite/MySQL）**：`halfvec` / `to_tsvector('jiebacfg')` 不存在 → 检索必须回退 Python 余弦与 grep，不能 500（任务 14）。
2. **嵌入服务超时/不可用**：任务必须 `failed` 且错误可见，不得静默写入空向量或全零向量（任务 7、12）。
3. **分块编辑 / 标注增删后索引不同步**：`search_text`、向量、`content_hash` 必须经同一写入路径更新，否则检索命中旧内容（任务 5、18）。
4. **任务取消 / 进程重启**：`running` 僵尸任务必须能被重置；取消后不得继续写入分块（任务 10、11）。
5. **旧调用方传参**：agent / 助手 / 工作流以位置参数调用 `search(kb_ids, query, top_k)`，新增参数必须全部为可选关键字（任务 18）。

---

## 工作流 WS1：正确性修复与索引真实化

### Task 1: RAG 参数配置

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/config.py`
- Test: `backend/tests/test_ai_rag_config.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class RagConfig`（字段见下）
  - `rag_config: RagConfig`（模块级单例，导入即读取环境变量）
  - 字段与默认值：`embed_batch=32`、`embed_max_chars=3500`、`embed_timeout=30.0`、`allow_hash_fallback=False`、`recall_mult=4`、`recall_min=20`、`rerank_candidates=50`、`rerank_timeout=15.0`、`context_tokens=3000`、`rewrite="off"`、`task_poll_seconds=3.0`、`hnsw_m=16`、`hnsw_ef_construction=64`、`hnsw_ef_search=100`、`pipeline_v2=True`
  - 环境变量：`RAG_EMBED_BATCH`、`RAG_EMBED_MAX_CHARS`、`RAG_EMBED_TIMEOUT`、`RAG_ALLOW_HASH_FALLBACK`、`RAG_RECALL_MULT`、`RAG_RECALL_MIN`、`RAG_RERANK_CANDIDATES`、`RAG_RERANK_TIMEOUT`、`RAG_CONTEXT_TOKENS`、`RAG_REWRITE`、`RAG_TASK_POLL`、`RAG_HNSW_M`、`RAG_HNSW_EF_CONSTRUCTION`、`RAG_HNSW_EF_SEARCH`、`RAG_PIPELINE_V2`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_config.py
import importlib

from app.plugin.module_ai.knowledge import config


def test_defaults_match_spec():
    c = config.RagConfig()
    assert c.embed_batch == 32
    assert c.recall_mult == 4 and c.recall_min == 20
    assert c.rerank_candidates == 50
    assert c.context_tokens == 3000
    assert c.allow_hash_fallback is False
    assert c.pipeline_v2 is True


def test_env_override(monkeypatch):
    monkeypatch.setenv("RAG_EMBED_BATCH", "8")
    monkeypatch.setenv("RAG_ALLOW_HASH_FALLBACK", "true")
    importlib.reload(config)
    assert config.rag_config.embed_batch == 8
    assert config.rag_config.allow_hash_fallback is True
    monkeypatch.undo()
    importlib.reload(config)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_config.py -q`
Expected: FAIL（`ModuleNotFoundError: app.plugin.module_ai.knowledge.config`）

- [ ] **Step 3: 实现 `config.py`**

用 `os.getenv` + 类型转换构造 `RagConfig`，布尔值接受 `1/true/yes/on`；`rewrite` 仅允许 `off|multi_query|hyde`，非法值回落 `off`；末尾 `rag_config = _load()`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_config.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/config.py backend/tests/test_ai_rag_config.py
git commit -m "feat(ai): 新增 RAG 检索链路可调参数配置"
```

### Task 2: 修复 `kb_quality`（字段名错误 + 父块口径 + 需重建标记）

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/service.py:423-463`、`knowledge/model.py`（追加 `parent_id / is_parent / content_hash / vector_model / token_count / char_start / char_end / search_text` 列）
- Test: `backend/tests/test_ai_knowledge.py`（追加用例）

**Interfaces:**
- Consumes: 模型字段 `AiKnowledgeChunkModel.knowledge_base_id / vector / is_parent / vector_model`
- Produces: `AiKnowledgeService.kb_quality(kb_id: int) -> dict`，返回键固定为：
  `{"kb_id","docs","chunks","parents","embedded_rate","statuses","score","healthy","needs_rebuild","vector_model"}`
  - `needs_rebuild` 判定：`chunks > 0 and (stored_model is None or current_model is None or stored_model != current_model)`
  - `stored_model` = 该库最近分块的 `vector_model`；`current_model` = `await embedding.current_model_name(model_id=await cls._kb_model_id([kb_id]))`（任务 7 提供；未实现前恒为 `None`，此时本任务只要求接口不崩、字段存在）
  - `parents` = `is_parent=True` 的分块数（不计入 `chunks`）

- [ ] **Step 1: 写失败测试**

```python
def test_kb_quality_returns_200(test_client, auth_headers):
    kb_id = _create_base(test_client, auth_headers)
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "q.txt", "content": "知识库质量接口回归测试内容"},
            headers=auth_headers,
        )
        r = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["chunks"] >= 1
        assert data["parents"] == 0            # 本次未启用父子块
        assert 0.0 <= data["embedded_rate"] <= 1.0
        assert isinstance(data["needs_rebuild"], bool)
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_kb_quality_returns_200 -q`
Expected: FAIL（500 或 `AttributeError: kb_id`）

- [ ] **Step 3: 修正实现**

把两处 `AiKnowledgeDocumentModel.kb_id` / `AiKnowledgeChunkModel.kb_id` 改为 `knowledge_base_id`；统计加 `is_deleted.is_(False)` 与 `is_parent.is_(False)`（父块另计 `parents`）；`needs_rebuild = bool(chunks and vector_model and current_model and vector_model != current_model)`，`vector_model` 取该库最近分块的 `vector_model`（无则 `None`）；`current_model` 通过 `await embedding.current_model_name(model_id=await cls._kb_model_id([kb_id]))`（该函数在任务 7 提供，未实现前允许返回 `None`）。
同时在 `model.py` 的 `AiKnowledgeChunkModel` 追加 §5.1 的 ORM 列（`parent_id: int|None`、`is_parent: bool` 默认 `False`、`content_hash: str|None`、`vector_model: str|None`、`token_count: int|None`、`char_start/char_end: int|None`、`search_text: Text|None`）。测试库由 `create_all` 自动建列；**`embedding_hv` 不进 ORM**（沿用现有惰性 SQL 建列方式，见任务 5）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_kb_quality_returns_200 -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_knowledge.py
git commit -m "fix(ai): 修正知识库质量接口字段名错误并补齐父块与需重建标记"
```

### Task 3: 修复 `delete_document` 级联删除

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/service.py:1388-1402`
- Test: `backend/tests/test_ai_knowledge.py`（追加用例）

**Interfaces:**
- Consumes: `AiKnowledgeChunkModel.document_id`、`AiKnowledgeEntityChunkModel.chunk_id`、`AiChunkAnnotationLogModel.chunk_id`
- Produces: `AiKnowledgeService.delete_document(kb_id: int, doc_id: int) -> dict`，返回 `{"chunks": int, "bindings": int, "annotations": int}`

- [ ] **Step 1: 写失败测试**

```python
def test_delete_document_cascades_chunks(test_client, auth_headers):
    kb_id = _create_base(test_client, auth_headers)
    try:
        up = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/upload",
            files={"file": ("del.txt", b"delete me content for cascade", "text/plain")},
            data={"chunk_size": "100", "overlap": "0", "strategy": "fixed"},
            headers=auth_headers,
        )
        assert up.status_code == 200, up.text
        doc_id = up.json()["data"]["id"]

        before = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert before, "上传后应有分块"

        d = test_client.delete(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/{doc_id}", headers=auth_headers
        )
        assert d.status_code == 200, d.text
        assert d.json()["data"]["chunks"] == len(before)

        after = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert [c for c in after if c.get("document_id") == doc_id] == []
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_delete_document_cascades_chunks -q`
Expected: FAIL（分块仍在）

- [ ] **Step 3: 实现级联**

先查 `doc`（不存在或不属于该库 → `ValueError("文档不存在")`）；抽成 `_purge_document_chunks(db, doc_id) -> int`（供任务 4 复用）：用 `select` 取该文档全部分块 ID，按 `chunk_id in ids` 物理删除 `ai_knowledge_entity_chunks`，软删 `ai_chunk_annotation_logs`（`is_deleted=True`、`deleted_time=func.now()`），分块本身物理删除（沿用现有 `delete_chunk` 的做法）；再删文档行与 S3 对象；最后回写 `kb.chunk_count = max(0, chunk_count - 删除数)`。全程一个事务，S3 删除放在事务提交后。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_delete_document_cascades_chunks -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_knowledge.py
git commit -m "fix(ai): 删除文档时级联清理分块、实体绑定与标记录"
```

### Task 4: 修复 `reparse_document` 去重

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/service.py:1413-1428`
- Test: `backend/tests/test_ai_knowledge.py`（追加用例）

**Interfaces:**
- Consumes: `_purge_document_chunks(db, doc_id) -> int`（任务 3 提供）
- Produces: `reparse_document(kb_id, doc_id, auth) -> {"id": int, "chunks": int}`（**替换式**：先清旧分块再入库，`chunk_count` 为本次分块数而非累加）

- [ ] **Step 1: 写失败测试**

```python
def test_reparse_is_idempotent(test_client, auth_headers):
    kb_id = _create_base(test_client, auth_headers)
    try:
        up = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/upload",
            files={"file": ("re.txt", b"reparse same content twice", "text/plain")},
            data={"chunk_size": "100", "overlap": "0", "strategy": "fixed"},
            headers=auth_headers,
        )
        doc_id = up.json()["data"]["id"]
        n1 = len(test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"])
        for _ in range(2):
            r = test_client.post(
                f"/api/v1/ai/knowledge/bases/{kb_id}/documents/{doc_id}/reparse",
                headers=auth_headers,
            )
            assert r.status_code == 200, r.text
        n2 = len(test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"])
        assert n2 == n1, f"重解析不应累加分块：{n1} -> {n2}"
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_reparse_is_idempotent -q`
Expected: FAIL（分块数翻倍）

- [ ] **Step 3: 实现替换式重解析**

`reparse_document`：先调 `_purge_document_chunks(db, doc_id)` 清旧分块（含绑定/标注），再 `ingest_text(..., document_id=doc_id)`，最后 `doc.chunk_count = 新分块数`（覆盖写）并只重建一次图谱。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_reparse_is_idempotent -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_knowledge.py
git commit -m "fix(ai): 重解析改为替换式入库避免重复分块"
```

### Task 5: 统一向量写入 + 幂等补列/建索引

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/embeddings/__init__.py`、`embeddings/persist.py`
- Modify: `backend/app/plugin/module_ai/knowledge/extensions.py`、`service.py:1431-1475, 2060-2102, 2136-2162`
- Create: `backend/tests/test_ai_rag_persist.py`、`backend/tests/test_ai_rag_pg_index.py`、`backend/scripts/check_rag_indexes.py`

**Interfaces:**
- Produces:
  - `build_search_text(content: str, annotations: list | None) -> str`（`content + " " + 标注文本`，空标注时等于 `content`）
  - `vector_literal(vec: list[float]) -> str`（`"[1.0,2.0]"`）
  - `chunk_hash(content: str, model: str) -> str`（sha256 hex）
  - `async def write_vectors(db, rows, vectors, *, model_name: str, expected_dim: int | None = None) -> int`：**唯一写入路径**；JSONB 必写；PG 且 `len(vec)==expected_dim` 时同时写 `embedding`/`embedding_hv`；维度不符只写 JSONB 并 `log.warning`；写 `dimension/vector_model/content_hash/token_count/search_text`
  - `extensions.ensure_extensions()` 追加：`embedding_hv`、`parent_id`、`is_parent`、`content_hash`、`vector_model`、`token_count`、`char_start`、`char_end`、`search_text` 列；`idx_chunk_embedding_hv`、`idx_chunk_fts` 索引；存量 `search_text` 回填
    - 说明：`parent_id` 等字段已由任务 2 加入 ORM；这里是为**存量库**补 SQL 列。`embedding` / `embedding_hv` **不进 ORM**（沿用现有惰性 SQL 建列方式）。
    - `search_text` 回填 SQL：`UPDATE ai_knowledge_chunks SET search_text = content || ' ' || <标注文本拼接> WHERE search_text IS NULL`，每条语句独立提交、失败静默（与现有 `_run_sql` 一致）。
  - `backend/scripts/check_rag_indexes.py`：连接 dev 库，打印 `EXPLAIN (COSTS OFF)` 向量查询计划与两个索引是否存在，返回码 0 表示 `Index Scan`

- [ ] **Step 1: 写失败测试（纯逻辑 + PG 索引）**

```python
# backend/tests/test_ai_rag_persist.py
from app.plugin.module_ai.knowledge.embeddings.persist import (
    build_search_text, chunk_hash, vector_literal,
)


def test_build_search_text_merges_annotations():
    assert build_search_text("正文", None) == "正文"
    assert build_search_text("正文", [{"text": "别名"}, {"kind": "note"}]) == "正文 别名"


def test_vector_literal_formats_postgres_array():
    assert vector_literal([0.5, -1.0]) == "[0.5,-1.0]"


def test_chunk_hash_is_stable_and_model_scoped():
    a = chunk_hash("同一段文本", "m1")
    assert a == chunk_hash("同一段文本", "m1")
    assert a != chunk_hash("同一段文本", "m2")
    assert len(a) == 64
```

```python
# backend/tests/test_ai_rag_pg_index.py
import os

import pytest

pytestmark = pytest.mark.skipif(
    (os.getenv("DATABASE_TYPE") or "").lower() not in ("postgres", "postgresql"),
    reason="仅在 PostgreSQL 上验证索引",
)


def test_vector_and_fulltext_indexes_exist():
    import asyncio

    import asyncpg

    dsn = (
        f"postgresql://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}"
        f"@{os.environ['DATABASE_HOST']}:{os.environ['DATABASE_PORT']}/{os.environ['DATABASE_NAME']}"
    )

    async def _names():
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                "select indexname from pg_indexes where tablename = 'ai_knowledge_chunks'"
            )
            return {r["indexname"] for r in rows}
        finally:
            await conn.close()

    names = asyncio.run(_names())
    assert "idx_chunk_embedding_hv" in names
    assert "idx_chunk_fts" in names
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_persist.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 persist + extensions + 接入三条入库路径**

`persist.py` 按 Interfaces 实现；`extensions.py` 在既有语句后追加列/索引/回填（每条 `_run_sql` 独立提交）；`ingest_text`、`_ingest_single`、`rebuild_index` 一律改为「先构造 ORM 行 → `flush()` 拿 id → `write_vectors(...)`」。`rebuild_index` 返回值改为 `{"chunks": int, "vectors": int}`。`ingest_text` 不再每次 `_rebuild_graph`（改为调用方决定，见任务 12）。
`scripts/check_rag_indexes.py` 用 `psycopg` 连接 `DATABASE_*` 环境变量，执行：
`EXPLAIN (COSTS OFF) SELECT id FROM ai_knowledge_chunks WHERE knowledge_base_id = ANY(ARRAY[1]) AND is_deleted = false ORDER BY embedding_hv <=> '[0,0]'::halfvec(2560) LIMIT 5`，断言输出含 `Index Scan`。

- [ ] **Step 4: 运行确认通过（SQLite 单测 + 真实 PG 校验）**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_persist.py -q`
Expected: PASS（3 passed）

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py -q`
Expected: PASS（既有 5 例 + 新增 3 例）

Run: `cd backend; uv run python scripts/check_rag_indexes.py`
Expected: 输出包含 `Index Scan using idx_chunk_embedding_hv`，退出码 0

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/embeddings backend/app/plugin/module_ai/knowledge/extensions.py backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_rag_persist.py backend/tests/test_ai_rag_pg_index.py backend/scripts/check_rag_indexes.py
git commit -m "feat(ai): 统一向量写入路径并补齐半精度向量索引与全文索引"
```

---

## 工作流 WS2：Embedding 链路强化

### Task 6: 模型解析与维度预检

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/embeddings/dims.py`
- Test: `backend/tests/test_ai_rag_embedding.py`

**Interfaces:**
- Consumes: `AiModelService.get_runtime_model(model_id=None, usage=None)`、`models.service.build_headers(base_url, extra_headers, session_id)`
- Produces:
  - `@dataclass(frozen=True) class ResolvedEmbedder: base_url: str; api_key: str; model: str; headers: dict[str, str]; timeout: float`
  - `class EmbeddingDimensionError(RuntimeError)`
  - `async def resolve_embedder(model_id: int | None = None) -> ResolvedEmbedder`（找不到抛 `RuntimeError("未配置嵌入模型")`）
  - `async def get_dimension(model_id: int | None = None) -> int`（探测一次后缓存到模块级字典）
  - `async def verify_dimension(expected: int, model_id: int | None = None) -> int`（不等抛 `EmbeddingDimensionError`，消息含 `expected` 与实际值）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_embedding.py
import pytest

from app.plugin.module_ai.knowledge.embeddings import dims


@pytest.mark.asyncio
async def test_verify_dimension_raises_on_mismatch(monkeypatch):
    async def fake_probe(model_id=None):
        return 8

    monkeypatch.setattr(dims, "get_dimension", fake_probe)
    assert await dims.verify_dimension(8) == 8
    with pytest.raises(dims.EmbeddingDimensionError) as ei:
        await dims.verify_dimension(2560)
    assert "2560" in str(ei.value) and "8" in str(ei.value)
```

> 若项目测试风格不用 `pytest-asyncio`，改用 `asyncio.run(...)`（与 `test_ai_knowledge.py` 的同步风格一致）。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `dims.py`**

`resolve_embedder` 复用 `build_headers` 生成头；`get_dimension` 用 `AsyncOpenAI(...).embeddings.create(model=..., input=["ping"])` 取 `len(data[0].embedding)` 并缓存（键 `f"{base_url}|{model}"`）；探测失败不缓存并抛出原异常。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/embeddings/dims.py backend/tests/test_ai_rag_embedding.py
git commit -m "feat(ai): 嵌入模型解析与维度预检"
```

### Task 7: 嵌入客户端（批量/重试/分片/缓存）与兼容门面

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/embeddings/cache.py`、`embeddings/client.py`
- Modify: `backend/app/plugin/module_ai/knowledge/embeddings/__init__.py`、`knowledge/embedding.py`（改为兼容门面）
- Test: `backend/tests/test_ai_rag_embedding.py`（追加）

**Interfaces:**
- Produces:
  - `class EmbeddingCache: get(model, text) -> list[float] | None; put(model, text, vec); clear(); hits/misses`
  - `embedding_cache: EmbeddingCache`
  - `async def embed_texts(texts: list[str], model_id: int | None = None) -> list[list[float]]`（批量 32、超时 30s、重试 2 次、超长分片取归一化均值、缓存命中跳过网络）
  - `async def embed_query(text: str, model_id: int | None = None) -> list[float]`
  - `async def current_model_name(model_id: int | None = None) -> str | None`
  - `def hash_embed(text: str) -> list[float]`（保留旧 `_hash_embed` 行为，维度 `FALLBACK_DIM=256`）
  - `knowledge/embedding.py` 保留 `embed_texts / embed_query / current_model_name / FALLBACK_DIM / EMBED_DIM(=2560)`，内部转发到 `embeddings` 包（**保持 `service.py` 的 `embedding.embed_texts` 调用与既有 monkeypatch 有效**）

- [ ] **Step 1: 写失败测试**

```python
async def _fake_batch(texts, model_id=None):
    return [[1.0, 0.0] for _ in texts]


def test_cache_dedupes_identical_texts(monkeypatch):
    from app.plugin.module_ai.knowledge.embeddings import cache, client

    cache.embedding_cache.clear()
    calls = {"n": 0}

    async def fake(texts, model_id=None):
        calls["n"] += 1
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(client, "_embed_batch", fake)
    import asyncio
    v1 = asyncio.run(client.embed_texts(["同一段"]))
    v2 = asyncio.run(client.embed_texts(["同一段"]))
    assert v1 == v2 == [[1.0, 0.0]]
    assert calls["n"] == 1, "第二次应命中缓存"
    assert cache.embedding_cache.hits >= 1


def test_failure_raises_instead_of_silent_hash(monkeypatch):
    from app.plugin.module_ai.knowledge.embeddings import client

    async def boom(texts, model_id=None):
        raise TimeoutError("网关超时")

    monkeypatch.setattr(client, "_embed_batch", boom)
    import asyncio
    with pytest.raises(Exception) as ei:
        asyncio.run(client.embed_texts(["x"]))
    assert "超时" in str(ei.value) or "Timeout" in type(ei.value).__name__
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q -k "cache or silent"`
Expected: FAIL

- [ ] **Step 3: 实现客户端**

`_embed_batch(texts, model_id)`：`resolve_embedder` → 按 `rag_config.embed_batch` 分批 → `OpenAILikeEmbedder(id=model, async_client=AsyncOpenAI(..., timeout=rag_config.embed_timeout, max_retries=2))` → `async_get_embeddings_batch_and_usage`；批量异常降级逐条。`embed_texts` 外层：先查缓存（键 `f"{model}|{text}"`，model 为空时 `"default"`）→ 未命中文本分片（`embed_max_chars`）→ 合并 → 归一化均值 → 回填缓存。所有路径失败时：若 `rag_config.allow_hash_fallback` 为真则 `hash_embed`，否则抛出（消息含 provider/model/base_url/文本长度）。

- [ ] **Step 4: 运行确认通过（含旧接口回归）**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q`
Expected: PASS

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py -q`
Expected: PASS（旧 `monkeypatch.setattr(embedding, "embed_texts", _embed)` 仍生效）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/embeddings backend/app/plugin/module_ai/knowledge/embedding.py backend/tests/test_ai_rag_embedding.py
git commit -m "feat(ai): 嵌入客户端支持批量重试分片缓存并取消静默降级"
```

### Task 8: 换模型失效检测与重建入口

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/service.py`（`_kb_model_id` 附近、`update_base`、`kb_quality`）
- Test: `backend/tests/test_ai_rag_embedding.py`（追加）

**Interfaces:**
- Produces:
  - `AiKnowledgeService.mark_rebuild_needed(kb_id: int) -> None`
  - `update_base` 检测到 `model_id` 变化时调用 `mark_rebuild_needed`
  - `kb_quality(...)["needs_rebuild"]` 为真当且仅当「库内存在分块且 `vector_model` 与当前模型名不一致」

- [ ] **Step 1: 写失败测试**

```python
def test_model_change_marks_rebuild_needed(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = _create_base(test_client, auth_headers)
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "m.txt", "content": "换模型需要重建索引"},
            headers=auth_headers,
        )
        before = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert before["needs_rebuild"] is False
        test_client.put(
            f"/api/v1/ai/knowledge/bases/update/{kb_id}",
            json={"model_id": 999999},
            headers=auth_headers,
        )
        after = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert after["needs_rebuild"] is True
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_embedding.py::test_model_change_marks_rebuild_needed -q`
Expected: FAIL（`needs_rebuild` 恒为 False 或 KeyError）

- [ ] **Step 3: 实现**

`mark_rebuild_needed` 更新库的 `updated_time`（并作为「需要重建」的显式信号；不新增列，避免迁移）；`update_base` 在 `model_id` 变化且库内有分块时调用；`kb_quality` 的 `needs_rebuild` 按 Interfaces 计算（`current_model_name` 解析失败时返回 False，避免质量接口 500）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_embedding.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_rag_embedding.py
git commit -m "feat(ai): 嵌入模型变更时提示重建索引"
```

### Task 9: 嵌入可观测性（耗时与失败原因）

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/embeddings/client.py`、`service.py`（`log_search`）
- Test: `backend/tests/test_ai_rag_embedding.py`（追加）

**Interfaces:**
- Produces:
  - `client.embed_texts_with_stats(texts, model_id=None) -> tuple[list[list[float]], dict]`，`stats = {"model","dim","batches","cache_hits","ms"}`
  - `embed_texts(...)` 等价的薄封装（保持签名）
  - `log_search(...)` 增加可选关键字 `embed_ms: float = 0.0`，写入 `ai_search_logs.mode` 不变、`engines` 附加 `{"embed_ms": ...}`

- [ ] **Step 1: 写失败测试**

```python
def test_embed_stats_reports_cache_hits(monkeypatch):
    from app.plugin.module_ai.knowledge.embeddings import cache, client

    cache.embedding_cache.clear()

    async def fake(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(client, "_embed_batch", fake)
    import asyncio
    _, s1 = asyncio.run(client.embed_texts_with_stats(["统计"]))
    _, s2 = asyncio.run(client.embed_texts_with_stats(["统计"]))
    assert s1["cache_hits"] == 0
    assert s2["cache_hits"] == 1
    assert s1["dim"] == 2 and s1["batches"] >= 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q -k stats`
Expected: FAIL

- [ ] **Step 3: 实现统计与埋点**

`embed_texts_with_stats` 用 `time.perf_counter()` 计时并把缓存命中、批次数、维度、模型名回传；`embed_texts` 只返回向量。检索侧（任务 18）调用带 stats 版本并把 `embed_ms` 写入检索日志。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_embedding.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/embeddings/client.py backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_rag_embedding.py
git commit -m "feat(ai): 嵌入耗时与缓存命中可观测"
```

---

## 工作流 WS3：后台任务框架

### Task 10: 任务表与任务服务

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/model.py`（追加 `AiRagTaskModel`）、`knowledge/extensions.py`
- Create: `backend/app/plugin/module_ai/knowledge/tasks/__init__.py`
- Test: `backend/tests/test_ai_rag_tasks.py`

**Interfaces:**
- Produces（`tasks/__init__.py`）：
  - `async def create_task(kind: str, *, kb_id: int | None = None, document_id: int | None = None, payload: dict | None = None, auth=None) -> dict`
  - `async def get_task(task_id: int) -> dict | None`
  - `async def list_tasks(*, kb_id: int | None = None, status: str | None = None, page_no: int = 1, page_size: int = 20) -> dict`
  - `async def cancel_task(task_id: int) -> dict`（置 `cancel_requested=True`；`pending` 直接置 `canceled`）
  - `async def claim_next() -> dict | None`（`UPDATE ... WHERE id=(SELECT id ... WHERE status='pending' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *`，SQLite 用「先 select 再 update + status 条件」）
  - `async def update_task(task_id: int, *, progress: int | None = None, step: str | None = None, status: str | None = None, message: str | None = None, error: str | None = None) -> None`
  - `async def reset_stale_running() -> int`
  - 任务字典键：`{"id","kind","status","kb_id","document_id","payload","progress","step","message","error","cancel_requested","created_time","started_time","finished_time"}`
- 模型字段：`kind varchar(32)`、`status varchar(16) default 'pending'`、`kb_id`、`document_id`、`payload jsonb`、`progress int default 0`、`step varchar(64)`、`message text`、`error text`、`cancel_requested bool default false`、`started_time`、`finished_time`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_tasks.py
import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_create_claim_update_task():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("document_ingest", kb_id=1, document_id=2, payload={"a": 1}))
    assert t["status"] == "pending" and t["progress"] == 0

    claimed = _run(tasks.claim_next())
    assert claimed["id"] == t["id"] and claimed["status"] == "running"
    assert _run(tasks.claim_next()) is None, "同一任务不能被重复抢占"

    _run(tasks.update_task(t["id"], progress=40, step="抽词"))
    cur = _run(tasks.get_task(t["id"]))
    assert cur["progress"] == 40 and cur["step"] == "抽词"


def test_cancel_pending_becomes_canceled():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=1))
    c = _run(tasks.cancel_task(t["id"]))
    assert c["status"] == "canceled" and c["cancel_requested"] is True


def test_reset_stale_running():
    from app.plugin.module_ai.knowledge import tasks

    t = _run(tasks.create_task("kb_rebuild", kb_id=1))
    _run(tasks.claim_next())
    assert _run(tasks.reset_stale_running()) >= 1
    assert _run(tasks.get_task(t["id"]))["status"] == "pending"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: FAIL（模型/模块不存在）

- [ ] **Step 3: 实现模型、幂等建表与任务服务**

`extensions.py` 增加 `ai_rag_tasks` 建表语句（与模型列一一对应）；任务服务内部统一用 `async_db_session()`；`claim_next` 用 `FOR UPDATE SKIP LOCKED`（PG）与「条件更新」两种实现，按 `filters._is_postgres()` 分支。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/model.py backend/app/plugin/module_ai/knowledge/extensions.py backend/app/plugin/module_ai/knowledge/tasks backend/tests/test_ai_rag_tasks.py
git commit -m "feat(ai): 新增 RAG 后台任务表与任务服务"
```

### Task 11: Worker 循环与启动钩子

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/tasks/worker.py`、`tasks/jobs.py`
- Modify: `backend/app/scripts/init_app.py`（`create_task` 区）
- Test: `backend/tests/test_ai_rag_tasks.py`（追加）

**Interfaces:**
- Produces:
  - `async def run_worker(*, max_iterations: int | None = None) -> None`（启动时调一次 `reset_stale_running()`；每轮 `claim_next` → 按 `jobs.JOB_HANDLERS[kind]` 执行 → 成功置 `succeeded/finished_time`，异常置 `failed/error`；轮末 `asyncio.sleep(rag_config.task_poll_seconds)`）
  - `jobs.JOB_HANDLERS: dict[str, Callable[[dict], Awaitable[None]]]`
  - `jobs.register(kind: str, handler) -> None`
- Consumes: `tasks.claim_next/update_task/reset_stale_running`（任务 10），`config.rag_config`（任务 1）

- [ ] **Step 1: 写失败测试**

```python
def test_worker_marks_failed_on_handler_error(monkeypatch):
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import jobs, worker

    t = _run(tasks.create_task("unit_test_kind"))

    async def boom(task):
        raise RuntimeError("故意失败")

    jobs.JOB_HANDLERS["unit_test_kind"] = boom
    _run(worker.run_worker(max_iterations=1))
    cur = _run(tasks.get_task(t["id"]))
    assert cur["status"] == "failed"
    assert "故意失败" in (cur["error"] or "")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py::test_worker_marks_failed_on_handler_error -q`
Expected: FAIL

- [ ] **Step 3: 实现 worker 与钩子**

`run_worker` 在 `finally` 中保证 `failed` 落库；`max_iterations=None` 表示常驻。`init_app` 的启动钩子区（与 `start_scheduler()` 并列）追加：
```python
from app.plugin.module_ai.knowledge.tasks.worker import run_worker
asyncio.create_task(run_worker())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/tasks backend/app/scripts/init_app.py backend/tests/test_ai_rag_tasks.py
git commit -m "feat(ai): RAG 后台任务 worker 与启动钩子"
```

### Task 12: 文档入库/重建/同步改为后台任务

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/tasks/jobs.py`（追加 3 个 handler）
- Modify: `backend/app/plugin/module_ai/knowledge/service.py`（`upload_document`、`reparse_document`、`rebuild_index`、`sync_datasource`）、`knowledge/controller.py`
- Test: `backend/tests/test_ai_rag_tasks.py`、`backend/tests/test_ai_knowledge.py`

**Interfaces:**
- Produces:
  - `async def job_document_ingest(task: dict) -> None`（`payload = {"document_id","filename","chunk_size","overlap","strategy","unit","use_ocr"}`；进度 5/30/40/85/95/100）
  - `async def job_kb_rebuild(task: dict) -> None`
  - `async def job_datasource_sync(task: dict) -> None`（图谱**只重建一次**）
  - `upload_document(...) -> {"id": doc_id, "task_id": task_id}`（`doc_status="pending"`）
  - `reparse_document(...) -> {"id": doc_id, "task_id": task_id}`
  - `rebuild_index(...)` 改为返回 `{"task_id": task_id}`
  - `sync_datasource(...)` 改为返回 `{"task_id": task_id, "rows": 0}`（行数在任务里回填到 `message`）
- `service.task_progress_cb(task_id)`：供 handler 更新进度，内部检查 `cancel_requested` 并在取消时抛 `TaskCanceled`

- [ ] **Step 1: 写失败测试**

```python
def test_upload_returns_task_and_worker_finishes(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb
    from app.plugin.module_ai.knowledge.tasks import worker

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = _create_base(test_client, auth_headers)
    try:
        up = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/upload",
            files={"file": ("bg.txt", b"background ingest content", "text/plain")},
            data={"strategy": "fixed", "chunk_size": "50", "overlap": "0"},
            headers=auth_headers,
        )
        assert up.status_code == 200, up.text
        body = up.json()["data"]
        assert body["task_id"] and body["id"]

        import asyncio
        for _ in range(20):
            tr = test_client.get(
                f"/api/v1/ai/knowledge/tasks/{body['task_id']}", headers=auth_headers
            ).json()["data"]
            if tr["status"] in ("succeeded", "failed", "canceled"):
                break
            asyncio.run(worker.run_worker(max_iterations=1))

        assert tr["status"] == "succeeded", tr
        assert tr["progress"] == 100

        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert chunks, "任务完成后应有分块"
    finally:
        _delete_base(test_client, auth_headers, [kb_id])


def test_canceled_task_does_not_write_chunks(test_client, auth_headers):
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import worker

    kb_id = _create_base(test_client, auth_headers)
    try:
        t = tasks.create_task("kb_rebuild", kb_id=kb_id)
        tasks.cancel_task(t["id"])
        import asyncio
        asyncio.run(worker.run_worker(max_iterations=1))
        assert tasks.get_task(t["id"])["status"] == "canceled"
        assert test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"] == []
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

> 测试里 `run_worker(max_iterations=N)` 会消费队列中**其它测试遗留的 pending 任务**，因此断言前用「循环到目标任务终态」的辅助更稳：
> ```python
> def _drain(worker, task_id, limit=20):
>     from app.plugin.module_ai.knowledge import tasks
>     import asyncio
>     for _ in range(limit):
>         if tasks.get_task(task_id)["status"] in ("succeeded", "failed", "canceled"):
>             break
>         asyncio.run(worker.run_worker(max_iterations=1))
>     return tasks.get_task(task_id)
> ```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: FAIL（上传仍同步返回 `chunks`）

- [ ] **Step 3: 实现 job 与控制器改造**

`job_document_ingest` 读取文档行（含 `object_key`/`content`）→ 全文缺失时从 RustFS 取原始字节 → **先用现有** `AiKnowledgeService._extract_doc(filename, data)` 与 `chunk_text(text, chunk_size, overlap, strategy)` 完成解析与切分（任务 19/21/25 会在**不改签名**的前提下升级这两个函数，任务因此自动获得新能力）→ `embed_texts` → `write_vectors` → `doc_status="ready"` → 全库图谱只重建一次。每步先调进度回调（会检查取消）。
`job_kb_rebuild` 复用 `rebuild_index` 的库内逻辑但改为任务执行；`job_datasource_sync` 复用 `_ingest_single` 但批量提交、末尾只 `_rebuild_graph` 一次。
控制器：三个触发端点**必须**在响应中返回 `task_id`；HTTP 仍 200（保持前端兼容），响应体新增字段。

**测试连带修改**：上传改为异步后，任务 3/4 的上传类用例（`test_delete_document_cascades_chunks`、`test_reparse_is_idempotent`）必须改为「上传 → 轮询到 `succeeded` → 再断言分块」；`test_kb_quality_returns_200`、`test_model_change_marks_rebuild_needed` 用的是同步 `/ingest`，不受影响。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: PASS

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py -q`
Expected: PASS（上传相关断言已改为「任务完成后查分块」）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/tasks/jobs.py backend/app/plugin/module_ai/knowledge/service.py backend/app/plugin/module_ai/knowledge/controller.py backend/tests/test_ai_rag_tasks.py backend/tests/test_ai_knowledge.py
git commit -m "feat(ai): 文档入库、重建索引与数据源同步改为后台任务"
```

### Task 13: 任务查询与取消接口

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/controller.py`、`frontend/src/api/module_ai/knowledge.ts`
- Test: `backend/tests/test_ai_rag_tasks.py`（追加）

**Interfaces:**
- Produces:
  - `GET /ai/knowledge/tasks/{task_id}` → `SuccessResponse(data=task)`
  - `GET /ai/knowledge/tasks?kb_id=&status=&page_no=&page_size=` → 分页结构 `{page_no,page_size,total,has_next,items}`
  - `POST /ai/knowledge/tasks/{task_id}/cancel` → 取消后的任务
  - 权限：三者都用 `module_ai:knowledge:query`（取消用 `module_ai:knowledge:update`）
  - 前端 API：`getAiRagTask(id)`、`getAiRagTaskList(params)`、`cancelAiRagTask(id)`

- [ ] **Step 1: 写失败测试**

```python
def test_task_endpoints(test_client, auth_headers):
    from app.plugin.module_ai.knowledge import tasks

    t = tasks.create_task("kb_rebuild", kb_id=1)
    detail = test_client.get(f"/api/v1/ai/knowledge/tasks/{t['id']}", headers=auth_headers)
    assert detail.status_code == 200 and detail.json()["data"]["id"] == t["id"]

    lst = test_client.get(
        "/api/v1/ai/knowledge/tasks", params={"kb_id": 1}, headers=auth_headers
    ).json()["data"]
    assert {"page_no", "page_size", "total", "has_next", "items"} <= set(lst)
    assert any(i["id"] == t["id"] for i in lst["items"])

    c = test_client.post(
        f"/api/v1/ai/knowledge/tasks/{t['id']}/cancel", headers=auth_headers
    )
    assert c.status_code == 200 and c.json()["data"]["status"] == "canceled"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py::test_task_endpoints -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现控制器与前端 API 封装**

控制器用 `@router.get/@router.post` + `AuthPermission`，统一 `SuccessResponse`；列表分页用 `page_no/page_size` 并返回 `has_next`。前端 `knowledge.ts` 追加三个函数（`request.get/post` 现有封装风格）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_tasks.py -q`
Expected: PASS

Run: `cd frontend; pnpm run type-check`
Expected: 无类型错误

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/controller.py frontend/src/api/module_ai/knowledge.ts backend/tests/test_ai_rag_tasks.py
git commit -m "feat(ai): 新增 RAG 任务查询与取消接口"
```

---

## 工作流 WS4：检索管线与质量增强

### Task 14: 召回引擎（向量/全文/grep，含非 PG 回退）

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/search/__init__.py`、`search/engines.py`、`search/filters.py`
- Test: `backend/tests/test_ai_rag_search.py`

**Interfaces:**
- Produces（`search/engines.py`）：
  - `async def vector_search(kb_ids: list[int], query: str, top_n: int, *, model_id: int | None = None, filters: dict | None = None, min_score: float = 0.0) -> list[dict]`
  - `async def fulltext_search(kb_ids: list[int], query: str, top_n: int, *, filters: dict | None = None) -> list[dict]`
  - `async def grep_search(kb_ids: list[int], query: str, top_n: int, *, filters: dict | None = None) -> list[dict]`
  - `async def ensure_vector_index() -> bool`（PG 且扩展存在时幂等建列/索引；其他环境返回 False）
  - 返回项固定键：`{"chunk_id","knowledge_base_id","file_name","document_id","start_line","page","content","score","engine"}`
- Produces（`search/filters.py`）：
  - `def match_filters(row, filters: dict | None) -> bool`（支持 `file_name`、`document_id`、`file_type`、`since`、`until`）
  - `def apply_filters(rows: list[dict], filters: dict | None) -> list[dict]`
  - `def drop_duplicates(rows: list[dict]) -> list[dict]`（按 `(file_name, content)` 去重，保留高分/先到）
- 非 PG 路径：读 `vector` JSONB 用 Python 余弦；全文不可用时 `fulltext_search` 返回 `[]`，由管线自动补 grep。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_search.py
import asyncio


def _run(coro):
    return asyncio.run(coro)


def _seed_kb(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb

    async def fake_embed(texts, model_id=None):
        vecs = []
        for t in texts:
            v = [0.0, 0.0]
            v[0 if "智能体" in t else 1] = 1.0
            vecs.append(v)
        return vecs

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = _create_base(test_client, auth_headers)
    for name, text in (("a.txt", "智能体编排说明"), ("b.txt", "传感器安装说明")):
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": name, "content": text},
            headers=auth_headers,
        )
    return kb_id


def test_vector_search_without_pg(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge.search import engines

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        rows = _run(engines.vector_search([kb_id], "智能体", 5))
        assert rows and "智能体" in rows[0]["content"]
        assert rows[0]["engine"] in ("pyvector", "pgvector")
        filtered = _run(engines.vector_search([kb_id], "智能体", 5, filters={"file_name": "b.txt"}))
        assert all(r["file_name"] == "b.txt" for r in filtered)
        low = _run(engines.vector_search([kb_id], "智能体", 5, min_score=0.99))
        assert all(r["score"] >= 0.99 for r in low)
    finally:
        _delete_base(test_client, auth_headers, [kb_id])


def test_fulltext_unavailable_falls_back_empty(test_client, auth_headers, monkeypatch):
    import os
    import pytest
    from app.plugin.module_ai.knowledge.search import engines

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        if (os.getenv("DATABASE_TYPE") or "").lower() == "sqlite":
            assert _run(engines.fulltext_search([kb_id], "智能体", 5)) == [], "非 PG 必须返回空而非报错"
        grep = _run(engines.grep_search([kb_id], "智能体", 5))
        assert grep and "智能体" in grep[0]["content"]
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_search.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 engines 与 filters**

PG 分支：`embed_query` 取向量 → `SET LOCAL hnsw.ef_search = :ef` → `ORDER BY embedding_hv <=> :qv::halfvec(...)`，`st.local` 需事务内执行；`min_score` 用 `1 - (embedding_hv <=> qv) >= :min_score`。全文分支：`to_tsvector('jiebacfg', search_text) @@ plainto_tsquery(...)` + `ts_rank`；异常（无扩展/无列）→ 返回 `[]`。grep：拆词 `ILIKE`。SQLite 分支：一次查询候选行，Python 余弦 + 过滤。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_search.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/search backend/tests/test_ai_rag_search.py
git commit -m "feat(ai): 知识库召回引擎支持 halfvec 索引与无 PG 回退"
```

### Task 15: 融合（RRF + 归一化加权）

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/search/fusion.py`
- Test: `backend/tests/test_ai_rag_search.py`（追加）

**Interfaces:**
- Produces:
  - `def rrf(lists: list[list[dict]], k: int = 60) -> list[dict]`（分数 `Σ 1/(k+rank)`，保留首个出现的元数据，`engine="hybrid"`）
  - `def weighted(lists: list[list[dict]], weights: list[float]) -> list[dict]`（每路按本路最高分归一化后加权求和）

- [ ] **Step 1: 写失败测试**

```python
def test_rrf_orders_by_reciprocal_rank():
    from app.plugin.module_ai.knowledge.search.fusion import rrf

    a = [{"chunk_id": 1, "content": "a1", "score": 0.9}, {"chunk_id": 2, "content": "a2", "score": 0.8}]
    b = [{"chunk_id": 2, "content": "a2", "score": 0.7}, {"chunk_id": 3, "content": "a3", "score": 0.6}]
    out = rrf([a, b])
    ids = [r["chunk_id"] for r in out]
    assert ids[0] == 2, "两路都命中的应排第一"
    assert out[0]["score"] == round(1 / 62 + 1 / 61, 4)
    assert {r["engine"] for r in out} == {"hybrid"}


def test_weighted_respects_weights():
    from app.plugin.module_ai.knowledge.search.fusion import weighted

    a = [{"chunk_id": 1, "content": "a", "score": 1.0}]
    b = [{"chunk_id": 2, "content": "b", "score": 1.0}]
    assert weighted([a, b], [0.9, 0.1])[0]["chunk_id"] == 1
    assert weighted([a, b], [0.1, 0.9])[0]["chunk_id"] == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k "rrf or weighted"`
Expected: FAIL

- [ ] **Step 3: 实现 fusion**

`weighted` 归一化用「本路最高分」（最高分为 0 时该路贡献 0）；结果按分数降序、同分按首次出现顺序稳定排序。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k "rrf or weighted"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/search/fusion.py backend/tests/test_ai_rag_search.py
git commit -m "feat(ai): 混合检索融合支持 RRF 与归一化加权"
```

### Task 16: 真 Rerank

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/search/rerank.py`
- Test: `backend/tests/test_ai_rag_search.py`（追加）

**Interfaces:**
- Produces:
  - `@dataclass class RerankOutcome: items: list[dict]; status: str`（`applied|skipped|empty`）
  - `@dataclass class ResolvedRerank: base_url: str; api_key: str; headers: dict; model: str`
  - `async def resolve_rerank(*, model_id: int | None = None) -> ResolvedRerank`
  - `async def rerank(query: str, candidates: list[dict], top_n: int, *, model_id: int | None = None) -> RerankOutcome`
  - 内部 `async def _post_rerank(base_url: str, api_key: str, headers: dict, model: str, query: str, documents: list[str], top_n: int) -> list[dict]`（测试可 monkeypatch）
  - 结果项新增 `rerank_score`；按 `rerank_score` 降序
  - 未配置/超时/非 200 → `status="skipped"`，`items` 保持原顺序并截断 `top_n`

- [ ] **Step 1: 写失败测试**

```python
def test_rerank_orders_and_scores(monkeypatch):
    from app.plugin.module_ai.knowledge.search import rerank as rr

    async def fake_post(base_url, api_key, headers, model, query, documents, top_n):
        return [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]

    async def fake_resolve(model_id=None):
        return rr.ResolvedRerank(base_url="http://x", api_key="k", headers={}, model="m")

    monkeypatch.setattr(rr, "_post_rerank", fake_post)
    monkeypatch.setattr(rr, "resolve_rerank", fake_resolve)
    cands = [{"chunk_id": 1, "content": "第一"}, {"chunk_id": 2, "content": "第二"}]
    out = _run(rr.rerank("问题", cands, 2))
    assert out.status == "applied"
    assert [i["chunk_id"] for i in out.items] == [2, 1]
    assert out.items[0]["rerank_score"] == 0.9


def test_rerank_degrades_on_error(monkeypatch):
    from app.plugin.module_ai.knowledge.search import rerank as rr

    async def boom_resolve(**kw):
        raise TimeoutError("超时")

    monkeypatch.setattr(rr, "resolve_rerank", boom_resolve)
    cands = [{"chunk_id": 1, "content": "x"}]
    out = _run(rr.rerank("q", cands, 5))
    assert out.status == "skipped"
    assert [i["chunk_id"] for i in out.items] == [1]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k rerank`
Expected: FAIL

- [ ] **Step 3: 实现 rerank**

`resolve_rerank()`：先尝试 `AiModelService.get_runtime_model(usage="rerank")`；无则用 `dims.resolve_embedder()` 的 `base_url/api_key/headers` 并把 `model` 设为该嵌入模型名（实测网关接受）；都没有 → 抛 `RuntimeError`（由 `rerank()` 捕获转为 `skipped`）。`_post_rerank` 用 `httpx.AsyncClient(timeout=rag_config.rerank_timeout).post(f"{base}/rerank", json={...})`，解析 `results[].index/relevance_score`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k rerank`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/search/rerank.py backend/tests/test_ai_rag_search.py
git commit -m "feat(ai): 接入网关 rerank 精排并支持失败降级"
```

### Task 17: 上下文组装（父块回填/合并/去重/预算）

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/search/context.py`
- Test: `backend/tests/test_ai_rag_search.py`（追加）

**Interfaces:**
- Produces:
  - `async def assemble(items: list[dict], *, top_k: int, context_tokens: int | None = None) -> list[dict]`
  - 每个结果补 `context`：有 `parent_id` 时取父块文本；否则取 `chunk_index ± 1`（同文件）拼接
  - 相邻块合并：同 `file_name` 且 `chunk_index` 连续 → 合入同一 `context`（不重复字符）
  - 去重：按 `(file_name, content)` 去重
  - 预算：按 `estimate_tokens(context)` 累加，超出 `context_tokens` 时截断该条 `context`（条目本身保留，`context_truncated=True`）
  - 至少保留 1 条

- [ ] **Step 1: 写失败测试**

```python
def test_assemble_uses_neighbor_and_budget(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge.search import context

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        items = [
            {"chunk_id": 1, "file_name": "a.txt", "chunk_index": 0, "content": "第一段", "score": 0.9},
            {"chunk_id": 2, "file_name": "a.txt", "chunk_index": 1, "content": "第二段", "score": 0.8},
            {"chunk_id": 2, "file_name": "a.txt", "chunk_index": 1, "content": "第二段", "score": 0.8},
        ]
        out = _run(context.assemble(items, top_k=5, context_tokens=10))
        assert len(out) == 2, "重复项应被去掉"
        assert out[0]["context"]
        assert all("context" in i for i in out)
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k assemble`
Expected: FAIL

- [ ] **Step 3: 实现上下文组装**

父块/邻居查询一次批量完成：`select ... where id in (:parent_ids)`；邻居用 `(knowledge_base_id, file_name, chunk_index in (idx-1, idx, idx+1))`。拼接时若下一段是上一段的子串则不重复追加。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_search.py -q -k assemble`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/search/context.py backend/tests/test_ai_rag_search.py
git commit -m "feat(ai): 检索上下文支持父块回填、相邻合并与 token 预算"
```

### Task 18: 检索管线装配 + 兼容门面 + 全链路埋点

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/search/__init__.py`、`knowledge/service.py`（`search`、`_pg_search` 删除或转发、`log_search`）、`knowledge/schema.py`（`AiKnowledgeSearchSchema` 增加 `min_score: float = 0.0`、`use_rerank: bool = True`、`filters: dict | None = None`、`rewrite: str = "off"`）、`knowledge/controller.py`
- Test: `backend/tests/test_ai_rag_search.py`、`backend/tests/test_ai_knowledge.py`

**Interfaces:**
- Produces:
  - `@dataclass class SearchOptions: mode="hybrid"; use_graph=True; min_score=0.0; use_rerank=True; vector_weight=None; fulltext_weight=None; rewrite="off"; filters=None; context_tokens=None`
  - `async def search(kb_ids: list[int], query: str, top_k: int = 5, options: SearchOptions | None = None) -> list[dict]`
  - `AiKnowledgeService.search(kb_ids, query, top_k=5, use_graph=True, mode="hybrid", vector_weight=0.5, fulltext_weight=0.5, *, min_score=0.0, use_rerank=True, filters=None, context_tokens=None, rewrite=None) -> list[dict]`（**新增参数全部为关键字参数**）
  - `search()` 内部写 `ai_search_logs`（含 `embed_ms`、`rerank` 状态、各引擎命中数）；`controller.search` 不再重复写日志
  - `ask()` / `retrieve()` 走同一 `search()`，因此自动获得埋点

- [ ] **Step 1: 写失败测试**

```python
def test_pipeline_end_to_end_and_logged(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge.search import SearchOptions
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        rows = _run(AiKnowledgeService.search([kb_id], "智能体", 3))
        assert rows and "智能体" in rows[0]["content"]
        assert "timings" in rows[0] or rows[0].get("engine") == "hybrid"

        rows2 = _run(AiKnowledgeService.search(
            [kb_id], "智能体", 3, min_score=0.0,
            filters={"file_name": "b.txt"},
        ))
        assert all(r["file_name"] == "b.txt" for r in rows2)

        stats = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/search-stats", headers=auth_headers
        ).json()["data"]
        assert stats["total"] >= 2, "直接调用 service.search 也应写检索日志"
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_search.py::test_pipeline_end_to_end_and_logged -q`
Expected: FAIL（service.search 不写日志/不支持 filters）

- [ ] **Step 3: 实现管线**

`search()`：并行 `vector_search / fulltext_search / grep_search(仅在全文空或 mode=grep)`；`mode` 决定启用子集（`vector`/`fulltext`/`grep` 单路；`hybrid` 多路；`graph` 追加 `graphrag.graph_retrieve`）；融合按 `vector_weight/fulltext_weight` 是否显式给出（非 None）选择 `weighted` 或 `rrf`；再 `apply_filters → rerank → assemble`；最后埋点。`_pg_search` 保留为弃用转发（`return await search(...)`）以兼容潜在外部调用。
`log_search` 增加 `embed_ms`/`rerank`/`engine_counts` 写入 `engines` JSONB。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_search.py -q`
Expected: PASS

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/search backend/app/plugin/module_ai/knowledge/service.py backend/app/plugin/module_ai/knowledge/controller.py backend/tests/test_ai_rag_search.py
git commit -m "feat(ai): 检索管线统一装配并补齐全链路检索日志"
```

---

## 工作流 WS5：切分（标题树 / token / 父子块）

### Task 19: token 计数与带位置的分块

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/chunking/__init__.py`、`chunking/tokens.py`
- Test: `backend/tests/test_ai_rag_chunking.py`

**Interfaces:**
- Produces:
  - `@dataclass class ChunkDraft: content: str; char_start: int; char_end: int; page: int | None; token_count: int; is_parent: bool = False; parent_index: int | None = None`
  - `def estimate_tokens(text: str) -> int`（tiktoken `cl100k_base`；异常回退 `max(1, len(text)//2)`）
  - `def chunk_drafts(text: str, *, strategy: str = "fixed", chunk_size: int = 500, overlap: int = 50, unit: str = "char", page_offsets: list[int] | None = None) -> list[ChunkDraft]`
  - `def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50, strategy: str = "fixed") -> list[str]`（**签名与输出保持不变**）
  - 位置推导：用 `text.find(piece, cursor)` 定位，找不到时退化为顺序游标；`page` 用 `bisect_right(page_offsets, char_start) - 1`（`page_offsets` 为 None 时 `None`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_chunking.py
from app.plugin.module_ai.knowledge.chunking import chunk_drafts, chunk_text


def test_legacy_chunk_text_unchanged():
    assert chunk_text("ABCDEFGHIJ", chunk_size=4, overlap=1) == ["ABCD", "DEFG", "GHIJ"]
    assert chunk_text("", 100) == []


def test_drafts_carry_positions_and_pages():
    text = "AAAABBBBCCCC"
    drafts = chunk_drafts(text, chunk_size=4, overlap=0, page_offsets=[0, 8])
    assert [d.content for d in drafts] == ["AAAA", "BBBB", "CCCC"]
    assert drafts[0].char_start == 0 and drafts[0].char_end == 4
    assert drafts[1].page == 0 and drafts[2].page == 1


def test_token_unit_keeps_within_budget():
    text = "。" .join(["知识库检索"] * 200)
    drafts = chunk_drafts(text, chunk_size=20, overlap=0, unit="token")
    assert drafts and all(d.token_count <= 20 for d in drafts)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_chunking.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`chunk_text` 保持旧实现（复制到 `chunking/__init__.py`），`chunk_drafts` 先调用 `chunk_text` 得到字符串列表，再定位位置；`unit="token"` 时用 `tokens.split_by_tokens` 切分，位置同样 `find` 定位。`service.chunk_text` 改为从 `chunking` 再导出（保证既有导入路径 `from ...service import chunk_text` 仍可用）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP="1"; uv run pytest tests/test_ai_rag_chunking.py -q`
Expected: PASS

Run: `cd backend; uv run pytest tests/test_ai_knowledge.py::test_chunk_text -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/chunking backend/app/plugin/module_ai/knowledge/service.py backend/tests/test_ai_rag_chunking.py
git commit -m "feat(ai): 分块支持 token 口径与字符位置、页码"
```

### Task 20: 标题树切分（`heading` 策略）

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/chunking/heading.py`
- Modify: `backend/app/plugin/module_ai/knowledge/chunking/__init__.py`
- Test: `backend/tests/test_ai_rag_chunking.py`（追加）

**Interfaces:**
- Produces:
  - `def split_heading_sections(text: str, max_level: int = 6) -> list[tuple[str, str, int]]`（`(heading_path, section_text, char_start)`）
  - `def chunk_heading(text: str, *, chunk_size: int = 500, overlap: int = 50, second_level: bool = True, split_symbols: str = "\n\n；;。") -> list[ChunkDraft]`
  - `chunk_drafts(strategy="heading")` 转发到 `chunk_heading`
  - 规则：标题行（`^#{1,6}\s` 或 `^\d+(\.\d+)*\s`）开启新节；节内按 `split_symbols` 递归切；单块超 `chunk_size*1.5` 时二级切分；每块前缀节标题（`【标题路径】\n`），且该前缀不计入内容定位（`char_start` 指向正文起点）

- [ ] **Step 1: 写失败测试**

```python
def test_heading_splits_by_tree_and_keeps_titles():
    md = "# 一级\n\n甲段内容。\n\n## 二级\n\n乙段内容。\n\n" + ("长" * 600)
    drafts = chunk_drafts(md, strategy="heading", chunk_size=200, overlap=0)
    assert drafts
    assert drafts[0].content.startswith("【一级】")
    assert any("【一级 / 二级】" in d.content for d in drafts)
    assert all(len(d.content) <= 300 for d in drafts)


def test_heading_second_level_split():
    md = "# 标题\n\n" + ("句子内容。" * 200)
    drafts = chunk_drafts(md, strategy="heading", chunk_size=100, overlap=0)
    assert len(drafts) > 1, "超长节必须二级切分"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_chunking.py -q -k heading`
Expected: FAIL

- [ ] **Step 3: 实现 heading**

正则 `^(?P<h>#{1,6})\s+(?P<t>.+)$` 与 `^\d+(?:\.\d+)*\s+`；维护标题栈生成路径；节内切分复用 `split_by_tokens`/`chunk_text(paragraph)`；`char_start` 用本节在原文中的起点 + 相对偏移。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_chunking.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/chunking/heading.py backend/app/plugin/module_ai/knowledge/chunking/__init__.py backend/tests/test_ai_rag_chunking.py
git commit -m "feat(ai): 新增标题树感知分块策略"
```

### Task 21: 父子块装配与入库

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/chunking/__init__.py`、`service.py`（`ingest_text`、`_ingest_single`）、`tasks/jobs.py`、`search/context.py`、`schema.py`（`AiKnowledgeIngestSchema` 增加 `parent_child: bool = False`、`chunk_unit: str = "char"`）、`controller.py`（透传两字段）
- Test: `backend/tests/test_ai_rag_parent_child.py`

**Interfaces:**
- Produces:
  - `chunk_drafts(..., parent_child: bool = False, parent_size: int = 2048) -> list[ChunkDraft]`：先产出父块（`is_parent=True`，`parent_index=None`），再产出子块（`parent_index` 指向**本列表内父块下标**）
  - `AiKnowledgeIngestSchema` 新字段：`parent_child: bool = False`、`chunk_unit: str = "char"`（`char|token`）
  - 入库：父块先写（不调用 `write_vectors`，`is_parent=True`），子块写 `parent_id=父块.id`
  - `chunk_count`/`embedded_rate` 只统计子块（任务 2 已定口径）
  - `context.assemble` 优先用 `parent_id` 取父块文本

- [ ] **Step 1: 写失败测试**

```python
def test_parent_child_ingest_and_backfill(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService
    import asyncio

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = _create_base(test_client, auth_headers)
    try:
        text = "# 标题\n\n" + ("知识库父子块内容。" * 80)
        r = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={
                "file_name": "pc.md", "content": text,
                "chunk_size": 100, "overlap": 0,
                "strategy": "heading", "parent_child": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        n = r.json()["data"]["chunks"]
        assert n >= 2

        q = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert q["parents"] >= 1 and q["chunks"] == n

        res = asyncio.run(AiKnowledgeService.search([kb_id], "父子块", 3))
        assert res and "知识库父子块内容" in res[0]["context"]
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_parent_child.py -q`
Expected: FAIL

- [ ] **Step 3: 实现父子块**

`chunk_drafts` 的父块按「标题节」切（`heading` 策略）或按 `parent_size` 滑窗（其他策略）；子块在父块文本内切分并保留 `parent_index`。入库分两批 `flush`，再回填 `parent_id`。`context.assemble` 优先 `parent_id`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_parent_child.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/chunking backend/app/plugin/module_ai/knowledge/service.py backend/app/plugin/module_ai/knowledge/tasks/jobs.py backend/app/plugin/module_ai/knowledge/search/context.py backend/tests/test_ai_rag_parent_child.py
git commit -m "feat(ai): 实现真正的父子分块与检索回填"
```

---

## 工作流 WS6：解析（MinerU / 表格 / 网页）

### Task 22: 文本与 Office 解析

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/parsing/__init__.py`、`parsing/text.py`、`parsing/office.py`
- Test: `backend/tests/test_ai_rag_parsing.py`

**Interfaces:**
- Produces:
  - `@dataclass class ParsedDoc: text: str; page_offsets: list[int]; meta: dict`
  - `def decode_text(data: bytes) -> str`（BOM → utf-8 → gbk → `errors="replace"`）
  - `def parse_docx(data: bytes) -> ParsedDoc`（段落 + 表格 → Markdown 管道表，表格前后各空一行）
  - `def parse_xlsx(data: bytes) -> ParsedDoc`（逐 sheet：`## sheet 名` + Markdown 表）
  - `def parse_text_file(filename: str, data: bytes) -> ParsedDoc`（csv 转 Markdown 表）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_parsing.py
import io

from docx import Document
from openpyxl import Workbook

from app.plugin.module_ai.knowledge.parsing import text as tparse, office


def test_decode_text_handles_gbk():
    assert tparse.decode_text("中文".encode("gbk")) == "中文"


def test_docx_tables_become_markdown():
    d = Document()
    d.add_paragraph("段落一")
    tb = d.add_table(rows=2, cols=2)
    tb.cell(0, 0).text = "列A"
    tb.cell(0, 1).text = "列B"
    tb.cell(1, 0).text = "1"
    tb.cell(1, 1).text = "2"
    buf = io.BytesIO()
    d.save(buf)
    doc = office.parse_docx(buf.getvalue())
    assert "段落一" in doc.text
    assert "| 列A | 列B |" in doc.text
    assert "| 1 | 2 |" in doc.text


def test_xlsx_multi_sheet():
    wb = Workbook()
    ws = wb.active
    ws.title = "库存"
    ws.append(["名称", "数量"])
    ws.append(["螺丝", 10])
    wb.create_sheet("备注").append(["说明"])
    buf = io.BytesIO()
    wb.save(buf)
    doc = office.parse_xlsx(buf.getvalue())
    assert "## 库存" in doc.text and "| 螺丝 | 10 |" in doc.text
    assert "## 备注" in doc.text
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 text/office**

表格转 Markdown 抽成 `office.table_to_markdown(rows: list[list[str]]) -> str`（列数取最大、空单元格补空、`|` 转义）；`decode_text` 捕获 `UnicodeDecodeError` 依次尝试。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/parsing backend/tests/test_ai_rag_parsing.py
git commit -m "feat(ai): 文本与 Office 解析支持表格转 Markdown"
```

### Task 23: PDF 解析与扫描件判定

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/parsing/pdf.py`
- Test: `backend/tests/test_ai_rag_parsing.py`（追加）

**Interfaces:**
- Produces:
  - `def parse_pdf(data: bytes) -> ParsedDoc`（逐页 `extract_text()`，`page_offsets[i]` = 第 i 页起点）
  - `def is_scanned(text: str, min_chars: int = 50) -> bool`（去空白后字符数 < `min_chars`）
  - `pdf.py` 不直接依赖 MinerU（由 `parsing/__init__.py` 决策）

- [ ] **Step 1: 写失败测试**

```python
def test_pdf_page_offsets_and_scanned_detection():
    from pypdf import PdfWriter
    from app.plugin.module_ai.knowledge.parsing import pdf as ppdf

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    doc = ppdf.parse_pdf(buf.getvalue())
    assert doc.page_offsets[0] == 0
    assert len(doc.page_offsets) == 2
    assert ppdf.is_scanned(doc.text) is True
    assert ppdf.is_scanned("这是一段足够长的可提取文本" * 5) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q -k pdf`
Expected: FAIL

- [ ] **Step 3: 实现 pdf**

`PdfReader(io.BytesIO(data))`；每页 `extract_text() or ""`，累加偏移（页间补 `\n`）；解析异常 → 返回空文本 + `meta={"parser":"pypdf","error":str(e)}`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/parsing/pdf.py backend/tests/test_ai_rag_parsing.py
git commit -m "feat(ai): PDF 解析返回页偏移并支持扫描件判定"
```

### Task 24: MinerU OCR 接入

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/parsing/mineru.py`
- Modify: `backend/app/plugin/module_ai/knowledge/config.py`（MinerU 参数）
- Test: `backend/tests/test_ai_rag_parsing.py`（追加）

**Interfaces:**
- Produces:
  - `async def parse_via_mineru(filename: str, data: bytes, *, kb_id: int | None = None, with_images: bool = True) -> ParsedDoc | None`（失败返回 `None` 并记录原因）
  - `def html_tables_to_markdown(md: str) -> str`
  - `def page_offsets_from_content_list(content_list: list[dict], text: str) -> list[int]`
  - 配置：`mineru_url`、`mineru_backend="pipeline"`、`mineru_parse_method="auto"`、`mineru_lang_list=["ch"]`、`mineru_timeout=1800`（`RagConfig` 追加字段，环境变量 `MINERU_*`）
  - 调用：`mcp.ClientSession.call_tool("process_document", {...})`，`mode="sync"`，`return_md/return_content_list=True`；结果 `status=="ok"` 取 `result`

- [ ] **Step 1: 写失败测试**

```python
def test_html_table_conversion():
    from app.plugin.module_ai.knowledge.parsing import mineru

    md = "前文<table><tr><th>列A</th><th>列B</th></tr><tr><td>1</td><td>2</td></tr></table>后文"
    out = mineru.html_tables_to_markdown(md)
    assert "| 列A | 列B |" in out and "| 1 | 2 |" in out
    assert "<table" not in out


def test_page_offsets_from_content_list():
    from app.plugin.module_ai.knowledge.parsing import mineru

    text = "第一页内容\n第二页内容"
    offsets = mineru.page_offsets_from_content_list(
        [{"page_idx": 0, "text": "第一页内容"}, {"page_idx": 1, "text": "第二页内容"}], text
    )
    assert offsets == [0, len("第一页内容\n")]

```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q -k "mineru or html_table or page_offsets"`
Expected: FAIL

- [ ] **Step 3: 实现 MinerU**

用 `mcp.client.sse.sse_client(rag_config.mineru_url, timeout=..., sse_read_timeout=...)` + `ClientSession`；参数见 Interfaces；把 `result["markdown"]` 经 `html_tables_to_markdown` 清洗；图片（`result["images"]`）写 RustFS 并重写引用（复用 `service._upload_to_rustfs` 的 S3 客户端，键前缀 `knowledge_images/{kb_id}/`）；失败 `log.error` 并返回 `None`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/parsing/mineru.py backend/app/plugin/module_ai/knowledge/config.py backend/tests/test_ai_rag_parsing.py
git commit -m "feat(ai): 接入 MinerU MCP 解析扫描件与图片"
```

### Task 25: 网页导入与解析分派

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/parsing/web.py`
- Modify: `backend/app/plugin/module_ai/knowledge/parsing/__init__.py`、`knowledge/service.py`（新增 `_extract_doc_async`）、`knowledge/controller.py`、`knowledge/tasks/jobs.py`
- Test: `backend/tests/test_ai_rag_parsing.py`（追加）

**Interfaces:**
- Produces:
  - `async def parse_document(filename: str, data: bytes, *, use_ocr: bool = True, kb_id: int | None = None) -> ParsedDoc`
    - 分派：`txt/md/csv/json/log` → `parse_text_file`；`docx` → `parse_docx`；`xlsx/xls` → `parse_xlsx`；`pdf` → `parse_pdf`，`is_scanned` 且 `use_ocr` → `parse_via_mineru`；图片 → `parse_via_mineru`；`html/htm` → `web.parse_html`
  - `async def parse_url(url: str, *, kb_id: int | None = None) -> ParsedDoc`（`newspaper4k` 抽正文，快照存 RustFS `knowledge_snapshots/`）
  - `async def AiKnowledgeService._extract_doc_async(filename, data, *, use_ocr=True, kb_id=None) -> tuple[str, list[int]]`（委托 `parse_document`）
  - `_extract_doc` 保留原**同步**签名与行为（仅文本/office/pdf 文本层），旧调用点不受影响
  - `job_document_ingest` 改调 `_extract_doc_async`（解析方式由 payload `use_ocr` 控制）
  - `POST /ai/knowledge/bases/{kb_id}/web-import`（body `{"url": "..."}`）→ 创建文档 + 入队 `document_ingest`，返回 `{"id","task_id"}`

- [ ] **Step 1: 写失败测试**

```python
def test_parse_document_dispatch():
    from app.plugin.module_ai.knowledge.parsing import parse_document
    import asyncio

    doc = asyncio.run(parse_document("a.txt", "纯文本内容".encode("utf-8")))
    assert "纯文本内容" in doc.text and doc.meta["parser"] == "text"

    doc2 = asyncio.run(parse_document("a.unknown", b"fallback bytes"))
    assert doc2.meta["parser"] in ("text", "unknown")


def test_web_import_requires_url(test_client, auth_headers):
    kb_id = _create_base(test_client, auth_headers)
    try:
        r = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/web-import",
            json={"url": "http://127.0.0.1:1/nope"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["task_id"]
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_parsing.py -q -k "dispatch or web"`
Expected: FAIL

- [ ] **Step 3: 实现**

`web.parse_html` 用 `bleach.clean` + `newspaper4k.Article`（`download`/`parse` 用 `asyncio.to_thread`）；`parse_url` 失败抛 `ValueError("网页抓取失败")`（HTTP 500 由控制器转为 ErrorResponse）。分派函数对所有异常兜底为文本解析并写 `meta["fallback"]`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_parsing.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/parsing backend/app/plugin/module_ai/knowledge/service.py backend/app/plugin/module_ai/knowledge/controller.py backend/tests/test_ai_rag_parsing.py
git commit -m "feat(ai): 解析分派与网页导入"
```

---

## 工作流 WS7：评测体系

### Task 26: 评测指标

**Files:**
- Create: `backend/app/plugin/module_ai/knowledge/eval/metrics.py`
- Test: `backend/tests/test_ai_rag_eval.py`

**Interfaces:**
- Produces:
  - `def recall_at_k(retrieved: list[int], expected: list[int], k: int) -> float`
  - `def precision_at_k(retrieved: list[int], expected: list[int], k: int) -> float`
  - `def mrr(retrieved: list[int], expected: list[int]) -> float`
  - `def ndcg_at_k(retrieved: list[int], expected: list[int], k: int) -> float`
  - `def evaluate_items(items: list[dict], k: int = 5) -> dict`（`items` 元素 `{"retrieved": [chunk_id...], "expected": [chunk_id...]}`；返回 `{"recall","precision","mrr","ndcg","n"}`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_rag_eval.py
from app.plugin.module_ai.knowledge.eval import metrics


def test_metrics_hand_computed():
    retrieved = [3, 1, 2]
    expected = [1, 2]
    assert metrics.recall_at_k(retrieved, expected, 2) == 0.5
    assert metrics.precision_at_k(retrieved, expected, 2) == 0.5
    assert metrics.mrr(retrieved, expected) == 0.5          # 第一个相关在第 2 位
    assert round(metrics.ndcg_at_k(retrieved, expected, 3), 4) == 0.6934


def test_metrics_degenerate_inputs():
    assert metrics.recall_at_k([], [1], 5) == 0.0
    assert metrics.mrr([], []) == 0.0
    assert metrics.recall_at_k([1], [], 5) == 0.0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_eval.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 metrics**

标准公式：`recall = |retrieved[:k] ∩ expected| / |expected|`；`precision = |∩| / k`；`mrr = 1/首个相关的 1-based 位次`（无则 0）；`ndcg` 用二值增益与 `log2(i+2)` 折扣，`IDCG` 按 `|expected|` 计算。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; $env:PYTEST_NO_APP=1; uv run pytest tests/test_ai_rag_eval.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/eval backend/tests/test_ai_rag_eval.py
git commit -m "feat(ai): 新增检索评测指标 Recall/Precision/MRR/NDCG"
```

### Task 27: 评测数据集、运行任务与接口

**Files:**
- Modify: `backend/app/plugin/module_ai/knowledge/model.py`（3 张表）、`extensions.py`、`eval/__init__.py`、`tasks/jobs.py`、`controller.py`
- Test: `backend/tests/test_ai_rag_eval.py`（追加）

**Interfaces:**
- Produces:
  - 模型：`AiEvalSetModel`（`name/description/kb_ids jsonb`）、`AiEvalItemModel`（`set_id/query/expected_chunk_ids jsonb/expected_files jsonb`）、`AiEvalRunModel`（`set_id/kb_id/config jsonb/metrics jsonb/status/error`）
  - `async def run_eval(set_id: int, kb_id: int, config: dict, progress_cb=None) -> dict`（逐条 `search` → 取 `chunk_id` → 指标）
  - `async def job_kb_eval(task: dict) -> None`（payload `{set_id, kb_id, config}`）
  - `POST /ai/knowledge/eval/sets`（创建）、`GET /ai/knowledge/eval/sets`、`POST /ai/knowledge/eval/sets/{set_id}/items`、`GET /ai/knowledge/eval/sets/{set_id}/items`
  - `POST /ai/knowledge/bases/{kb_id}/eval/run`（body `{set_id, config}`）→ `{"task_id"}`
  - `GET /ai/knowledge/bases/{kb_id}/eval/runs` → 列表（含 `metrics`）

- [ ] **Step 1: 写失败测试**

```python
def test_eval_end_to_end(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb
    from app.plugin.module_ai.knowledge.tasks import worker
    import asyncio

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = _create_base(test_client, auth_headers)
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "e.txt", "content": "智能体编排说明"},
            headers=auth_headers,
        )
        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        cid = chunks[0]["id"]

        s = test_client.post(
            "/api/v1/ai/knowledge/eval/sets",
            json={"name": "回归集", "kb_ids": [kb_id]}, headers=auth_headers,
        ).json()["data"]
        test_client.post(
            f"/api/v1/ai/knowledge/eval/sets/{s['id']}/items",
            json={"query": "智能体", "expected_chunk_ids": [cid]}, headers=auth_headers,
        )
        run = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/eval/run",
            json={"set_id": s["id"], "config": {"top_k": 3, "use_rerank": False}},
            headers=auth_headers,
        ).json()["data"]
        asyncio.run(worker.run_worker(max_iterations=3))

        runs = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/eval/runs", headers=auth_headers
        ).json()["data"]
        assert runs and runs[0]["metrics"]["recall"] >= 0.0
        assert runs[0]["status"] in ("succeeded", "running")
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend; uv run pytest tests/test_ai_rag_eval.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

三张表 + 幂等建表；评测运行创建 `ai_rag_tasks(kind="kb_eval")` 并注册 handler；`run_eval` 逐条调用 `search`（走任务 18 管线）后计算指标并写 `ai_eval_runs.metrics`；控制器三个集合接口 + 两个运行接口，权限统一 `module_ai:knowledge:query`（创建/运行用 `update`）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend; uv run pytest tests/test_ai_rag_eval.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/knowledge/model.py backend/app/plugin/module_ai/knowledge/extensions.py backend/app/plugin/module_ai/knowledge/eval backend/app/plugin/module_ai/knowledge/tasks/jobs.py backend/app/plugin/module_ai/knowledge/controller.py backend/tests/test_ai_rag_eval.py
git commit -m "feat(ai): 知识库评测数据集与运行任务"
```

---

## 工作流 WS8：前端与验收

### Task 28: 评测 API 封装与「评测」页签

**Files:**
- Modify: `frontend/src/api/module_ai/knowledge.ts`、`frontend/src/views/module_ai/knowledge/index.vue`
- 参照：`frontend/src/views/module_system/param/index.vue`（列表/弹窗/表单风格）

**Interfaces:**
- Consumes: Task 27 的 5 个接口
- Produces: 详情抽屉新增「评测」tab：数据集下拉 + 配置表单（`mode`/`top_k`/`use_rerank`/`min_score`）+「运行评测」按钮 + 运行记录表（`el-table`：时间、配置摘要、Recall@K、MRR、NDCG、状态）+ 指标对比（同数据集多行并排）

- [ ] **Step 1: 封装 API**

`getAiEvalSets`、`createAiEvalSet`、`getAiEvalItems`、`createAiEvalItem`、`runAiEval`、`getAiEvalRuns`（风格与现有 `request.get/post` 一致）。

- [ ] **Step 2: 实现页签**

`<el-tab-pane label="评测">` + `el-form`（`label-width="96px"`）+ `el-table`（`stripe`）+ `el-tag`（状态）。运行按钮 `v-hasPerm="'module_ai:knowledge:update'"`；运行后把 `task_id` 挂到该行，只轮询该行进度（`setTimeout` 自循环，`status` 终态即停）。

- [ ] **Step 3: 验证**

Run: `cd frontend; pnpm run type-check`
Expected: 无错误

Run: `cd frontend; pnpm exec eslint src/views/module_ai/knowledge/index.vue src/api/module_ai/knowledge.ts`
Expected: 无 error（仓库存在与本次无关的历史 lint 错误，不要用全量 `pnpm run lint` 判定本次结果）

- [ ] **Step 4: 截图核对**

用无头浏览器打开 `/ai/knowledge` 详情抽屉「评测」页签截图，与「参数管理」页面对照：字号 14px、按钮 `size` 一致、无自定义配色。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/module_ai/knowledge.ts frontend/src/views/module_ai/knowledge/index.vue
git commit -m "feat(ai): 知识库评测页签与运行记录"
```

### Task 29: 文档页签任务进度与解析选项

**Files:**
- Modify: `frontend/src/views/module_ai/knowledge/index.vue`、`frontend/src/api/module_ai/knowledge.ts`

**Interfaces:**
- Consumes: Task 12 上传返回 `{id, task_id}`；Task 13 任务查询
- Produces: 文档表新增「进度」列：`el-progress`（`row.task.progress`）+ 状态标签；上传表单增加「解析方式」`el-select`（自动/仅文本层/OCR）；失败时 `el-tooltip` 显示 `row.task.error`

- [ ] **Step 1: 改造上传流程**

上传成功后不再立即拉全表：把 `{document_id, task_id, progress:0, status:'pending'}` 挂到该文档行，启动**单行轮询**（1s，终态停止）；终态时仅 `refreshDocuments()` 一次。

- [ ] **Step 2: 解析选项**

表单字段 `use_ocr: boolean`，提交到 upload 的 multipart 字段 `use_ocr`（后端 Task 12 读取）。

- [ ] **Step 3: 验证**

Run: `cd frontend; pnpm run type-check`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/module_ai/knowledge/index.vue frontend/src/api/module_ai/knowledge.ts
git commit -m "feat(ai): 文档上传进度行内展示与解析方式选择"
```

### Task 30: 分块页签（token/父子）与检索测试增强

**Files:**
- Modify: `frontend/src/views/module_ai/knowledge/index.vue`

**Interfaces:**
- Consumes: Task 21（父子块字段）、Task 18（`min_score/use_rerank/filters/timings`）
- Produces: 分块表新增「Token」「类型（父/子）」列；检索测试表单新增阈值输入、文件过滤输入、`rerank` 开关、改写下拉；结果卡片展示耗时分解（`el-descriptions`：embed/recall/fusion/rerank/total）

- [ ] **Step 1: 分块表改造**

父块行用 `el-tag type="info"` 标「父」，子块行显示 `parent_id`；按 `parent_id` 可折叠分组（`el-table` 的 `row-key` + `tree-props` 或简化为排序）。

- [ ] **Step 2: 检索测试改造**

表单字段与后端对齐：`min_score`（`el-input-number`，0–1，step 0.05）、`filters.file_name`（`el-input`，可空）、`use_rerank`（`el-switch`）、`rewrite`（`el-select`：off/multi_query/hyde）；结果下方 `el-descriptions` 显示 `timings`。

- [ ] **Step 3: 验证**

Run: `cd frontend; pnpm run type-check`
Expected: 无错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/module_ai/knowledge/index.vue
git commit -m "feat(ai): 分块父子视图与检索测试参数增强"
```

### Task 31: 全量回归与验收记录

**Files:**
- Create: `docs/superpowers/plans/2026-10-19-agent-embedding-rag-v2-acceptance.md`

**Interfaces:**
- Consumes: 全部前置任务
- Produces: 验收记录（每条证据的**实际输出**，不是"应该"）

- [ ] **Step 1: 后端全量回归**

Run: `cd backend; uv run pytest -q -n 4`
Expected: 全绿（记录用例数与耗时）

- [ ] **Step 2: 索引与孤儿分块证据**

Run: `cd backend; uv run python scripts/check_rag_indexes.py`
Expected: `Index Scan using idx_chunk_embedding_hv`

Run（dev 库 SQL）: `SELECT count(*) FROM ai_knowledge_chunks c LEFT JOIN ai_knowledge_documents d ON c.document_id = d.id WHERE c.document_id IS NOT NULL AND d.id IS NULL;`
Expected: `0`

- [ ] **Step 3: 真实模型端到端（MinerU + 真实嵌入 + rerank）**

用一份扫描件 PDF 走 `/documents/upload` → 轮询任务到 `succeeded` → 校验分块有 `page` 且内容非空；再跑一次检索，确认返回项有 `rerank_score` 且日志 `rerank=applied`。

- [ ] **Step 4: 评测数字（写进验收记录）**

同一评测集跑两组配置：`{"use_rerank": false}` 与 `{"use_rerank": true}`，记录 `recall/precision/mrr/ndcg` 与耗时；若 rerank 未提升，记录原因（候选池/查询分布）而不是隐瞒。

- [ ] **Step 5: 提交**

```bash
git add docs/superpowers/plans/2026-10-19-agent-embedding-rag-v2-acceptance.md
git commit -m "docs(ai): RAG 检索链路 v2 验收记录"
```

---

## 计划自检

- **spec 覆盖**：§2 A–G 分别对应 Task 2–4（A）、Task 5（B）、Task 6–9（C）、Task 14–18（D）、Task 10–13（E）、Task 26–27（F）、Task 19–25（G）；§11 前端对应 Task 28–30；§13 验收对应 Task 31；§12 已知差距无任务（符合非目标）。
- **类型一致性**：`write_vectors`、`ChunkDraft`、`SearchOptions`、`RerankOutcome`、`EmbeddingCache`、`run_worker(max_iterations=)`、`rag_config` 在各任务间名称与字段一致；`kb_quality` 返回键在 Task 2/8/21 一致。
- **Review Focus 映射**：非 PG 回退 → Task 14；嵌入失败可见 → Task 7/12；索引不同步 → Task 5/18；任务取消/僵尸 → Task 10/11/12；旧调用方传参 → Task 18。
- **比例**：计划以签名、测试断言与验收命令为主，未转录实现代码。

