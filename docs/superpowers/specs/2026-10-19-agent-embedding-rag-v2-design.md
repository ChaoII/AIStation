# Agent 嵌入能力补齐（RAG 检索链路 v2）设计

> 日期：2026-10-19
> 分支：`feat/agent-embedding-rag-v2`（worktree：`ce637a/agent-embedding`）
> 对标基准：`D:\BSIAP` 的 `module_ai/knowledge`、`memory`、`chat/citation_matcher`、`agent_team` 等
> 结论口径：**本条链路的能力只能比 BSIAP 强、不能比它弱**（阶段一范围 A–G，见 §2）

## 1. 背景与目标

AIStation 的知识库 RAG 已具备「可运行、功能面宽」的形态（5 种检索模式、标注闭环、图谱可视化、引用溯源、agent/助手/应用/工作流 四路接入），但对标后存在两类问题：

1. **生产级能力缺失或实际失效**：向量列没有索引（全表顺序扫描）、embedding 链路静默降级、解析能力弱、无后台任务、无评测、无 rerank。
2. **正确性缺陷**：质量接口必崩、删文档不级联删分块（孤儿分块继续被检索命中）、重解析重复入库、检索日志只覆盖一个入口。

本设计的目标是把该链路升级为「**索引真实、链路可观测、解析够用、可评测、可后台执行**」的 v2，并以可复现的数字证明强于 BSIAP。

## 2. 范围

### 2.1 阶段一范围（已确认 A–G 全选）

| 编号 | 工作内容 |
|---|---|
| A | 正确性修复：`kb_quality` 字段名错误、删文档级联、重解析去重、检索日志全链路埋点 |
| B | 向量索引真实化：`halfvec(2560)` + HNSW，消除顺序扫描；全文 GIN 索引 |
| C | Embedding 链路强化：维度预检、超时/重试/批量、缓存、换模型失效、去静默降级 |
| D | 检索质量增强：真 rerank、相似度阈值、元数据过滤、查询改写、上下文组装 |
| E | 后台任务化：任务表 + worker + 进度轮询 + 状态机 |
| F | 检索评测体系：金标准集 + Recall@K / MRR / NDCG + 对比运行 + 页面 |
| G | 解析与切分追赶：MinerU OCR、docx 表格、xlsx、URL 导入、标题树切分、真父子块、token 口径 |

### 2.2 非目标（阶段二，明确记录为「已知差距」）

以下 4 项为 BSIAP 强于我们、但不在阶段一 A–G 内的能力，**阶段一不做**，写入 §12 已知差距：

1. 知识库共享/公开（`is_public`）+ `SELF_OR_SHARED` 行级权限 + 共享库只读防护。
2. 真 GraphRAG：LLM 实体/关系抽取（带证据句）+ 人工审核入图 + Louvain 社区检测 + 社区摘要。
3. 引用句级语义匹配（0.65 阈值）+ PDF **页内高亮**定位。
4. 免登录引用预览。

### 2.3 不可破坏的约束

- `AiKnowledgeService` 的**对外签名与 4 处接入点**（agent / 助手 / 工作流 / 应用）保持兼容；`mode`/权重参数照收。
- 不新增第三方依赖（MinerU 用已有 `mcp`，网页正文用已有 `newspaper4k`，HTML 清洗用 `bleach`，token 估算用已有 `tiktoken`，向量用已有 `pgvector`）。
- AI 调用仍走 agno（AGENTS 强制）；不在 agno 之外另起平行调用链。
- 迁移必须手写 alembic（AGENTS：`autogenerate` 会把 400+ 影子表判成待 DROP）。

## 3. 现状证据（改造前）

### 3.1 索引与检索

| 事实 | 证据 |
|---|---|
| 向量列 `vector(2560)`，`EMBED_DIM=2560` | `backend/app/plugin/module_ai/knowledge/embedding.py:15-17` |
| 仅 `dim <= 2000` 才建 HNSW → 2560 永不建索引 | `knowledge/service.py:739-773` |
| 实测 `ai_knowledge_chunks` 上**没有** 任何向量索引（`pg_indexes` 只有 btree） | 2026-10-19 探针 |
| 向量检索依赖 `embedding IS NOT NULL`，缺列时靠检索时顺带 `UPDATE` 回填 | `knowledge/service.py:611-646`、`:761-770` |
| 入库只写 JSONB `vector`，不写 pgvector 列 | `knowledge/service.py:1456-1470` |
| `rebuild_index` 只写 JSONB，pgvector 列会变旧 | `knowledge/service.py:2136-2162` |
| hybrid 实际是 RRF(k=60)，权重参数被忽略，`_fuse_weighted` 是死代码 | `knowledge/service.py:648-736` |
| 全文检索无 `pg_jieba` 时直接返回空（不降级 grep） | `knowledge/service.py:574-609` |
| 向量检索无阈值、无元数据过滤、无 rerank | `knowledge/service.py:611-646` |

### 3.2 正确性缺陷

| 缺陷 | 证据 |
|---|---|
| `kb_quality` 用 `AiKnowledgeDocumentModel.kb_id` / `AiKnowledgeChunkModel.kb_id`（真实字段是 `knowledge_base_id`）→ 接口必崩 | `knowledge/service.py:423-463` |
| `delete_document` 只删文档行与 S3 对象，**不删分块** → 孤儿分块继续被检索命中 | `knowledge/service.py:1388-1402` |
| `delete_document` 中 `ok` 在 `d` 为 None 时未赋值（`UnboundLocalError`） | `knowledge/service.py:1393-1398` |
| `reparse_document` 直接追加 `ingest_text`，旧分块不删 → 重复入库 | `knowledge/service.py:1413-1428` |
| 检索日志只由 `/search` 端点写入；`ask`/agent RAG/工作流 RAG 不写 | `knowledge/controller.py:130-132`、`service.py:2175-2201` |
| 每次入库/每行数据源同步都触发一次**全库**图谱重建 | `knowledge/service.py:1474`、`:2101` |

### 3.3 解析与切分

| 事实 | 证据 |
|---|---|
| 仅 `txt/md/csv/json/log`（utf-8→gbk）+ docx（仅段落，丢表格/图片）+ pypdf（纯文本层，扫描件为空） | `knowledge/service.py:1181-1218` |
| 切分只有 `fixed/paragraph/sentence`，按字符 | `knowledge/service.py:39-84` |
| 无 token 口径、无父子块字段 | `knowledge/model.py:35-70` |
| 无后台任务：上传/重建/同步全同步阻塞 HTTP | `knowledge/controller.py:310-327`、`:428-435` |

### 3.4 环境实测（2026-10-19 探针，均非推测）

| 探测项 | 结果 |
|---|---|
| 嵌入模型 | `smbs/Embedding-4B`，网关 `http://172.168.100.146:5000/v1`，**2560 维**，单条 40–60ms |
| `POST /v1/rerank` | 可用：返回 `results[].relevance_score`，支持 `top_n`，4 文档约 70ms，排序语义合理；未授权模型返回 403 |
| PostgreSQL | 18.6；`vector 0.8.6`、`pg_jieba 1.1.0`、`age 1.8.0` |
| `halfvec(2560)` + HNSW | 事务内实测建索引与检索成功（余弦得分 1.0），**可用** |
| MinerU | `http://172.168.100.146:8100/sse` 在线，`mineru-processor 1.28.1`；工具 `upload_file` / `process_document` / `process_directory` / `query_task_status`；本机 `mcp 2.3.0` 客户端可连接（字段为 snake_case） |
| dev 库现状 | `ai_knowledge_chunks` 9 行，9 行有 embedding；无向量索引 |

## 4. 架构与模块边界

`AiKnowledgeService` 保留为**薄门面**（对外签名不变），内部拆为单一职责单元：

```
module_ai/knowledge/
  controller.py         路由（旧路径全保留；新增 tasks / eval 路由）
  service.py            门面：参数兼容、转发、错误提示
  config.py             新增：RAG 可调参数与开关
  parsing/
    __init__.py         extract(filename, data, opts) -> ParsedDoc
    text.py             txt/md/csv/json/log（编码探测：BOM → utf-8 → gbk）
    office.py           docx（段落 + 表格→Markdown）、xlsx/xls（多 sheet→Markdown）
    pdf.py              pypdf 文本层 + 页码偏移；近空判定
    mineru.py           MCP(SSE) process_document；HTML 表格→Markdown；图片存 RustFS；页码
    web.py              URL 抓取（newspaper4k 正文）+ 快照存 RustFS
  chunking/
    __init__.py         chunk(text, strategy, size, overlap, token_aware) -> list[ChunkDraft]
    fixed.py            fixed / paragraph / sentence（兼容旧行为）
    heading.py          标题树 + 分段符号 + 二级块
    tokens.py           tiktoken 估算 + 窗口切分
  embeddings/
    __init__.py         embed_texts / embed_query / verify_dimension / invalidate
    client.py           agno OpenAILikeEmbedder 封装（超时/重试/批量/分片）
    dims.py             模型→维度解析与缓存、维度校验
    cache.py            进程内 LRU（模型+文本哈希 → 向量）
  search/
    __init__.py         search() 管线（唯一入口）
    engines.py          vector(halfvec HNSW) / fulltext(jiebacfg) / grep / graph
    fusion.py           RRF（默认）+ 归一化加权（显式权重时）
    rerank.py           网关 /rerank；失败降级
    rewrite.py          multi-query / HyDE（默认关）
    filters.py          阈值、元数据、孤儿块剔除
    context.py          父块回填、相邻合并、去重、token 预算
  tasks/
    __init__.py         任务表模型与服务（create/claim/update/cancel/status）
    worker.py           asyncio worker（启动钩子挂载）
    jobs.py             document_ingest / kb_rebuild / datasource_sync / kb_eval
  eval/
    __init__.py         评测集 CRUD、运行、指标
    metrics.py          Recall@K / Precision@K / MRR / NDCG@K
  graphrag.py           保留现状（阶段二增强）
  extensions.py         幂等补列/建索引/建表（存量库重启即生效）
```

依赖方向：`controller → service → {parsing, chunking, embeddings, search, tasks, eval} → {model, config}`；`search` 不反向依赖 `service`。

## 5. 数据模型与迁移

### 5.1 `ai_knowledge_chunks` 增列

| 列 | 类型 | 说明 |
|---|---|---|
| `embedding_hv` | `halfvec(2560)` | 检索权威向量列（PG + pgvector 时） |
| `parent_id` | `int` | 父块 ID（子块指向父块） |
| `is_parent` | `bool` | 是否父块（父块不参与召回，只用于回填） |
| `content_hash` | `varchar(64)` | sha256(规范化文本 + 模型)，用于去重与幂等 |
| `vector_model` | `varchar(128)` | 生成该向量的模型名（换模型失效判定） |
| `token_count` | `int` | tiktoken 估算 token 数（窗口预算用） |
| `char_start` / `char_end` | `int` | 原文偏移（替代仅 start_line，便于精确高亮） |
| `search_text` | `text` | **正文 + 标注**的可索引文本（由写入路径维护），全文检索唯一入口 |

保留 `vector jsonb`（跨库/无扩展回退）与 `embedding vector(2560)`（兼容期双写）。

### 5.2 索引

```sql
-- 向量：半精度 HNSW（2560 维超过 vector 的 2000 上限，halfvec 上限 4000）
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hv
  ON ai_knowledge_chunks USING hnsw (embedding_hv halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);
-- 全文：jiebacfg GIN（唯一入口是 search_text 列）
CREATE INDEX IF NOT EXISTS idx_chunk_fts
  ON ai_knowledge_chunks USING gin (to_tsvector('jiebacfg', search_text));
```

> **为什么用 `search_text` 列而不是表达式索引**：现有 `_ANN_SQL` 是 `COALESCE((SELECT string_agg(...) FROM jsonb_array_elements(...)), '')`，**索引表达式不允许包含子查询**，直接建表达式索引会失败。改为由写入路径维护 `search_text = content || ' ' || 标注文本`，索引与查询共用同一表达式，保证命中。
> 存量数据一次性回填：`UPDATE ai_knowledge_chunks SET search_text = content || ' ' || <ann_sql> WHERE search_text IS NULL`；此后由 `embeddings/persist.py`、分块编辑、增删标注三处同步维护。
> `CREATE INDEX CONCURRENTLY` 不能在事务内执行：alembic 迁移内用普通建索引，生产热建用独立会话执行（`extensions.py` 每条语句独立提交，可直接 CONCURRENTLY）。

### 5.3 新表

- `ai_rag_tasks`：`id, uuid, status, kind, kb_id, document_id, payload jsonb, progress int, step varchar(64), message text, error text, cancel_requested bool, started_time, finished_time, created_time, updated_time, is_deleted, created_id`
- `ai_eval_sets`：`id, name, description, kb_ids jsonb, created_id, ...`
- `ai_eval_items`：`id, set_id, query, expected_chunk_ids jsonb, expected_files jsonb, note`
- `ai_eval_runs`：`id, set_id, kb_id, config jsonb, metrics jsonb, status, error, created_id, created_time`

状态机（任务）：`pending → running → succeeded | failed | canceled`；`cancel_requested=true` 时 worker 在检查点终止并置 `canceled`。

### 5.4 迁移策略

1. `extensions.py` 追加幂等语句（`ADD COLUMN IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS`、`CREATE TABLE IF NOT EXISTS`）——存量库**重启即生效**，不依赖 alembic。
2. 手写 alembic revision 同步模型变更（空库可全链重放；对插件表先 `sa.inspect(bind).has_table()` 判断）。
3. 兼容：`embedding` / `vector` 两列继续双写一个版本周期；新列缺失时检索自动回退旧路径。

### 5.5 统一写入路径

新增 `embeddings/persist.py::write_vectors(chunk_rows, vectors, model)`：一次写入同时维护 `vector`(jsonb) + `embedding`(vector) + `embedding_hv`(halfvec) + `dimension` + `vector_model` + `content_hash` + `token_count` + `search_text`。
**禁止**任何路径只写其中一列（当前 `ingest_text`/`rebuild_index` 的缺陷即由此产生）。

## 6. Embedding 链路（C）

### 6.1 客户端

- 仍使用 agno `OpenAILikeEmbedder` + `AsyncOpenAI(base_url, api_key, default_headers)`（`build_headers` 注入网关头）。
- agno 旋钮：`timeout=30s`、`max_retries=2`；批量大小 `RAG_EMBED_BATCH=32`（分批调用 `async_get_embeddings_batch_and_usage`）。
- 超长文本：> `RAG_EMBED_MAX_CHARS=3500` 时按窗口分片嵌入，取**归一化均值**作为该块向量，并记 `truncated=true` 到 `meta`。
- 批量失败 → 自动降级逐条；逐条仍失败 → 抛错（由任务置 `failed` 并保留错误）。

### 6.2 维度治理

- `dims.py`：首次调用探测真实维度并缓存（键：provider+model）；与库内 `vector_dim` / 既有分块 `dimension` 比对。
- 不一致 → 明确报错「嵌入模型维度变更（X→Y），需重建索引」，不再截断/补零。
- 移除 `_fit_dim` 的隐式截断/补零行为。

### 6.3 缓存与失效

- `cache.py`：进程内 LRU（`model + sha1(text)` → vector，默认 4096 条）；命中不计费。
- 换模型失效：`kb.model_id` 变更或 `chunk.vector_model != 当前模型` → `kb_quality` 返回 `needs_rebuild=true`，前端提示「一键重建」。
- 检索侧：`embed_query` 与入库用同一模型解析函数，避免「写入用 A、查询用 B」。

### 6.4 可观测性

- 取消静默降级：`RAG_ALLOW_HASH_FALLBACK=false`（默认）；哈希回退仅在显式开启或测试中启用。
- 每次失败记录 `provider/model/base_url/状态码/耗时/文本长度`；检索日志记 `embed_ms`。

## 7. 检索管线（D）

```
search(kb_ids, query, top_k, mode, filters, opts) -> list[dict]
① 预处理：strip / 归一化；opts.rewrite 时 multi-query 或 HyDE（LLM，默认关）
② 并行召回（asyncio.gather，单路异常不影响其他路）：
   vector   : halfvec HNSW，ORDER BY embedding_hv <=> :qv，topN
   fulltext : jiebacfg + GIN(search_text)，ts_rank，topN；无 pg_jieba 时自动退 grep
   grep     : ILIKE（保底；全文不可用时自动启用）
   graph    : AGE 多跳（mode=graph 或 hybrid+use_graph）
   topN = max(top_k * RAG_RECALL_MULT(4), 20)
③ 融合：默认 RRF(k=60)；显式传权重且 opts.use_weighted=true 时走归一化加权
④ 过滤：min_score（vector 路）、元数据（file_name/document_id/时间/类型）、孤儿块剔除
⑤ rerank：融合后取前 RAG_RERANK_CANDIDATES(50) → /rerank → 取 top_k
⑥ 组装：父块回填（真 parent_id）→ 相邻块合并 → 去重 → token 预算（RAG_CONTEXT_TOKENS，tiktoken 估算）
⑦ 埋点：ai_search_logs（query/mode/top_k/hit_count/engines/耗时分解/rerank 是否生效/embed_ms）
```

兼容：`mode` 五值不变；返回值在旧字段基础上新增 `rerank_score`、`context`、`timings`、`engine_detail`（不删旧字段）。

### 7.1 rerank

- `POST {base_url}/rerank`，body `{model, query, documents, top_n}`；`results[].relevance_score` 作为精排分。
- 模型解析：优先 `usage="rerank"` 模型；无则回退到当前 embedding 模型的 provider/base_url（实测该网关可用）。
- 超时 15s；失败/未配置 → **跳过重排**并在日志与返回值标注 `rerank="skipped"`，不影响主链路。
- `min_score` 在 rerank 后按 `rerank_score` 再过滤一次（可选开关）。

### 7.2 查询改写

- multi-query：LLM 生成 2–3 个改写（提示词固定、温度 0），各自召回后并入 RRF。
- HyDE：LLM 生成假设答案再嵌入召回。
- 默认关闭（`RAG_REWRITE=off`），可在检索测试页/评测配置中开启。

## 8. 后台任务（E）

- `tasks/worker.py`：`async def run_worker(): while True: claim → run → sleep(3)`，由 `init_app` 的启动钩子区 `asyncio.create_task` 挂载（与 `module_train.scheduler.start_scheduler` 同款模式，见 `init_app.py:1682-1684`、`module_train/scheduler.py:145-160`）。
- 单并发（`RAG_TASK_CONCURRENCY=1`）；启动时把 `running` 僵尸任务重置为 `pending`；任务失败重试 1 次。
- 任务类型与阶段：
  - `document_ingest`：parse(0–30) → chunk(30–40) → embed(40–85) → persist(85–95) → graph(95–100)
  - `kb_rebuild`：清向量 → 重新嵌入 → 重建索引 → 图谱
  - `datasource_sync`：批量拉取 → 分批入库 → **图谱延迟重建一次**（修正现有 N 次重建）
  - `kb_eval`：逐条检索 → 计算指标
- 接口（`module_ai:knowledge:update` 权限）：
  - `GET /ai/knowledge/tasks/{task_id}`
  - `GET /ai/knowledge/tasks?kb_id=&status=&page_no=&page_size=`
  - `POST /ai/knowledge/tasks/{task_id}/cancel`
- 触发点改造：上传文档、重新解析、重建索引、数据源同步、评测运行 → 立即返回 `task_id`（202 语义），不再阻塞请求。

## 9. 解析与切分（G）

### 9.1 解析

| 输入 | 实现 |
|---|---|
| txt/md/csv/json/log | BOM → utf-8 → gbk 兜底；CSV 按行转 Markdown 表 |
| docx | `python-docx`：段落 + **表格转 Markdown 管道表**（保留表头/对齐）；页眉页脚忽略 |
| xlsx/xls | `openpyxl`（已有依赖）：每个 sheet 转 Markdown 表，附 sheet 名 |
| pdf | `pypdf` 取文本层与逐页偏移；去空白字符数 < 50 → 判为扫描件 → MinerU |
| 图片 | MinerU |
| html / url | `newspaper4k` 抽正文 + 标题；原文快照存 RustFS（`knowledge_snapshots/`） |

### 9.2 MinerU 接入

- 传输：`mcp` SDK `sse_client(url)` + `ClientSession.call_tool("process_document", args)`（已实测连通）。
- 参数：`file_content`(base64) / `filename` / `mode="sync"` / `backend="pipeline"` / `parse_method="auto"` / `lang_list=["ch"]` / `return_md=True` / `return_content_list=True` / `return_images=True`。
- 结果处理：HTML 表格 → Markdown 管道表；图片 base64 → RustFS 并重写引用；**页码**取自 `content_list[].page_idx`。
- 超时 1800s；服务不可用或返回非 `status=ok` → 记录错误、任务 `failed`（可重试），不静默产出空文档。
- 配置项：`MINERU_MCP_URL=http://172.168.100.146:8100/sse`、`MINERU_BACKEND`、`MINERU_PARSE_METHOD`、`MINERU_LANG_LIST`、`MINERU_TIMEOUT`。

### 9.3 切分

| 策略 | 行为 |
|---|---|
| `fixed` / `paragraph` / `sentence` | 保留旧行为（回归兼容） |
| `heading` | 标题树（Markdown `#` 层级 / 编号标题）→ 节；节内按分段符号递归切；超长节二级切分 |
| token 口径 | `token_count` 用 tiktoken 估算；`ai_knowledge_bases.chunk_unit ∈ {char, token}`：**迁移前已存在的库默认 `char`（行为不变）**，迁移后新建的库默认 `token`；可在库设置中显式切换 |
| 父子块 | 父块 = 标题节或 2048 字符滑窗（`is_parent=true`）；子块 = 300–500（检索单元，`parent_id` 指向父块）。**父块只存文本、不生成向量、不参与召回与 `chunk_count` 统计**（回填时按 `parent_id` 取文本） |

位置：`char_start/char_end` 由切分器精确定位；`page` 由 `page_offsets` 二分推导；`start_line` 保留。

统计口径：`chunk_count`、`embedded_rate`、质量健康分**只统计子块**（`is_parent=false`），父块不计入，避免"父块拉低嵌入率"的假报警。

## 10. 评测体系（F）

- 数据集：`ai_eval_sets` + `ai_eval_items`（`query` + `expected_chunk_ids` 或 `expected_files` + 关键串）。
  - 支持「从标注台账 / 检索日志」一键生成候选条目，人工确认后入库。
- 配置：`{mode, use_weighted, vector_weight, fulltext_weight, use_rerank, min_score, top_k, rewrite}`。
- 指标（`eval/metrics.py`）：`Recall@K`、`Precision@K`、`MRR`、`NDCG@K`、命中率、平均与 P95 耗时。
- 运行：`POST /ai/knowledge/bases/{kb_id}/eval/run` → 后台任务 → `GET /eval/runs` 列表与对比。
- 页面：知识库详情新增「评测」tab：数据集管理、运行、指标对比（同数据集多配置并排）。

## 11. 前端

| 位置 | 改造 |
|---|---|
| 文档 tab | 上传/重解析后显示任务进度（行内，局部更新）；解析方式（自动/文本层/OCR）选择；失败原因可见 |
| 分块 tab | 显示 token 数、父子关系（父块折叠）、char 偏移；按父块分组浏览 |
| 检索测试 | 新增 `min_score`、元数据过滤（文件/时间/类型）、`rerank` 开关、改写开关；展示耗时分解与各引擎命中数 |
| 新「评测」tab | 数据集 CRUD、运行配置、指标表与对比 |
| 通用 | 全部 Element Plus 原生组件 + `--el-*` 变量；进度只更新对应行；删除类操作二次确认并带数量 |

## 12. 已知差距（阶段二，明确记录）

1. 共享/公开 + `SELF_OR_SHARED` 权限 + 共享库只读防护。
2. 真 GraphRAG（LLM 抽取 + 审核 + Louvain 社区 + 社区摘要）。
3. 引用句级语义匹配（0.65）+ PDF 页内高亮。
4. 免登录引用预览。

另：记忆向量召回（复合打分）、SQL 示例双通道 RRF、数据源 schema 索引属于「记忆/查询/数据源」子系统，不在知识库检索链路内，另行评估。

## 13. 测试与验收

### 13.1 测试

- 纯逻辑（`PYTEST_NO_APP=1`，约 2s）：切分 6 种策略、token 口径、父子块装配、解析 fixtures（docx/xlsx/md/pdf 文本层）、RRF/加权、rerank 响应解析、评测指标、任务状态机、窗口预算。
- 集成（需应用）：`ingest → search` 端到端（假嵌入器）、`delete_document` 级联（孤儿分块 = 0）、`reparse` 不重复、`kb_quality` 200、`EXPLAIN` 断言 `Index Scan`、`cancel` 任务。
- 契约：`tests/test_ai_knowledge.py` 全绿；agent/助手/工作流 RAG 注入回归。

### 13.2 验收证据（必须实际跑出）

| 项 | 证据 |
|---|---|
| 索引真实 | `EXPLAIN` 向量查询出现 `Index Scan using idx_chunk_embedding_hv` |
| 无孤儿 | 删文档后 `SELECT count(*) FROM ai_knowledge_chunks WHERE document_id=<已删>` = 0 |
| 质量接口 | `GET .../quality` 返回 200 且字段完整 |
| 重解析 | 同一文档重解析两次，分块数不翻倍 |
| 任务化 | 上传大文档立即返回 `task_id`，进度可从 0 走到 100 |
| OCR | 扫描件 PDF 经 MinerU 入库，分块带正确 `page` |
| rerank | 日志/返回值显示 `rerank=applied`；关闭时 `skipped` |
| 质量数字 | 同一评测集：`hybrid+rerank` vs `hybrid` 的 MRR/Recall@5 对比（写入 spec 附录或提交信息） |

## 14. 默认参数

| 参数 | 默认 |
|---|---|
| `RAG_EMBED_BATCH` | 32 |
| `RAG_EMBED_MAX_CHARS` | 3500 |
| `RAG_EMBED_TIMEOUT` | 30s |
| `RAG_ALLOW_HASH_FALLBACK` | false |
| `RAG_RECALL_MULT` | 4（下限 20） |
| `RAG_RERANK_CANDIDATES` | 50 |
| `RAG_RERANK_TIMEOUT` | 15s |
| `RAG_CONTEXT_TOKENS` | 3000 |
| `RAG_REWRITE` | off |
| HNSW | `m=16, ef_construction=64, ef_search=100` |
| `RAG_TASK_CONCURRENCY` / 轮询 | 1 / 3s |
| 切分默认 | `chunk_size=500, overlap=50, unit=char`（新库 token） |

## 15. 实施顺序（每步可独立验收）

| 工作流 | 内容 | 验收 |
|---|---|---|
| WS1 | 正确性修复 + halfvec 索引 + 统一写入路径 | 13.2 前 4 行 + `EXPLAIN` |
| WS2 | Embedding 强化（维度/重试/缓存/失效/可观测） | 维度预检报错可复现；缓存命中率；换模型提示 |
| WS3 | 任务框架（表 + worker + 进度 + 取消） | 上传异步、进度可轮询、僵尸任务重置 |
| WS4 | 检索质量（RRF/加权、rerank、阈值、过滤、改写、上下文） | rerank 生效与降级；阈值/过滤生效 |
| WS5 | 切分（标题树、token、父子块） | 父子块回填正确的单测 + 分块对比 |
| WS6 | 解析（MinerU、docx 表格、xlsx、URL） | 扫描件带页码入库；表格保结构 |
| WS7 | 评测体系 | 同集多配置对比可跑出数字 |
| WS8 | 前端收尾 + 全量验收 | 截图自查 + 13.2 全表 |

## 16. 风险与对策

| 风险 | 对策 |
|---|---|
| 2560 维 halfvec 索引构建内存/时间 | 先在 dev 小库验证；`CREATE INDEX CONCURRENTLY`（生产）；失败回退顺序扫描并告警 |
| GIN 表达式索引与查询表达式不一致导致不命中 | 索引与查询共用 `search_text` 同一表达式；集成测试断言 `Index Scan`；**索引表达式不能含子查询**，故不直接索引 `_ANN_SQL` |
| `CREATE INDEX CONCURRENTLY` 在事务内报错 | 迁移内普通建索引；热库用独立会话（`extensions.py` 逐条提交） |
| 2560 维 halfvec 索引构建时间/内存 | 先在 dev 小库验证；大表用 CONCURRENTLY；失败回退顺序扫描并告警 |
| 解析/OCR 长耗时 | 全部走任务；超时与可重试；MinerU 不可用时明确失败而非空文档 |
| 双写列不一致 | 唯一写入函数 + 单测断言三列同值；兼容期后删除旧列 |
| 旧接口行为变化 | 门面签名不变；`mode`/权重兼容；`RAG_PIPELINE_V2` 开关可回退一版 |
| 任务 worker 多实例重复消费 | 单实例单并发；claim 用 `UPDATE ... WHERE status='pending' RETURNING` 原子抢占 |

## 附录 A：能力对标矩阵（阶段一验收基准）

| # | 能力项 | BSIAP | AIStation 改造前 | 阶段一目标 |
|---|---|---|---|---|
| 1 | 向量索引 | 每库 `agno_kb_{id}` HNSW 真索引 | 无索引，全表顺序扫描 | halfvec(2560)+HNSW |
| 2 | Embedding 链路 | 自定义 embedder + 维度预检 + 批量回退 | 无预检/重试/缓存，静默降级哈希 | 全面对齐 + 缓存 + 可观测 |
| 3 | 嵌入模型治理 | 库级 `embed_model` | 库级 `model_id`，无失效治理 | 换模型失效重建 + 维度校验 |
| 4 | 文档解析 | MinerU OCR + 8 种 Reader + 网页快照 | 4 种文本 + docx 段落 + pypdf | MinerU + 表格 + 网页 + 多格式 |
| 5 | 切分 | 标题树 + 二级块 + 位置追踪 | 3 种字符切分 | 标题树 + token + 真父子块 |
| 6 | 混合检索 | Agno 加权（权重生效） | RRF k=60（更强），权重无效 | RRF + 可选加权（均生效） |
| 7 | Rerank | 开关是空实现 | 无 | 真 rerank + 失败降级 |
| 8 | 查询改写 | 无 | 无 | multi-query / HyDE（可开关） |
| 9 | 元数据过滤 | 无 | 无 | 文件/时间/类型过滤 |
| 10 | 上下文组织 | 父子回填 + 去重 | `chunk_index ±1` 近似回填 | 真父块 + 去重 + token 预算 |
| 11 | GraphRAG 深度 | LLM 抽取+审核+社区+摘要 | jieba 共现 + AGE 多跳 | **阶段二**（见 §12） |
| 12 | 引用溯源 | 句级匹配 + PDF 页内高亮 | 页码/行号 + 下载链接 | **阶段二**（见 §12） |
| 13 | 后台任务 | 进程内字典 + 轮询 | 全同步阻塞 HTTP | 任务表 + worker + 进度 + 取消 |
| 14 | 正确性 | 孤儿向量 2 处缺陷 | 质量接口必崩、删文档孤儿、重解析重复 | 全部修复 + 回归测试 |
| 15 | 检索日志 | 无 | 仅 `/search` 写 | 全链路埋点（含耗时分解） |
| 16 | 评测 | 无 | 无 | 金标准集 + Recall@K/MRR/NDCG |
| 17 | 共享/公开 + 行级权限 | 有（`SELF_OR_SHARED`） | 无 | **阶段二**（见 §12） |
| 18 | 免登录引用预览 | 有 | 无 | **阶段二**（见 §12） |

> 阶段一结束时，第 1–10、13–16 项必须 ≥ BSIAP；第 11、12、17、18 项按 §12 明确记为阶段二差距，不纳入本次验收。

