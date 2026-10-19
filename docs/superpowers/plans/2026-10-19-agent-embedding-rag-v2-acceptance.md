# RAG 检索链路 v2 实施验收记录（阶段一，进行中）

> 分支：`feat/agent-embedding-rag-v2`　日期：2026-10-19
> 设计：`docs/superpowers/specs/2026-10-19-agent-embedding-rag-v2-design.md`
> 计划：`docs/superpowers/plans/2026-10-19-agent-embedding-rag-v2.md`

本文件只记录**实际跑出的结果**，未执行的项明确标为「待做」。

## 1. 已完成的工作流

| 工作流 | 状态 | 提交 |
|---|---|---|
| WS1 正确性 + 索引真实化（Task 1–5） | ✅ | `f9f66610`…`541154af` |
| WS2 Embedding 链路强化（Task 6–9） | ✅ | `3506f220`、`e8184898`、`28f70ddb` |
| WS3 后台任务框架（Task 10–13） | ✅ | `d8e3822b`、`759d25f8`、`c101ad43` |
| WS4 检索管线与质量增强（Task 14–18） | ✅ | `d9e4043e`、`e438acc6` |
| WS5 切分：token/标题树/父子块（Task 19–21） | ✅ | `42e880e6` |
| WS6 解析：MinerU/表格/网页（Task 22–25） | ✅ | `5b38a34d` |
| WS7 评测：指标/数据集/运行（Task 26–27） | ✅（后端） | `f57f2714` |
| WS8 前端页签与检索增强（Task 28–30） | ✅（代码 + 静态检查） | `38f4ce98` |
| WS8 最终验收（Task 31） | ⏳ 待做（需运行服务） | — |

## 1.1 前端改动（`38f4ce98`）

- `frontend/src/api/module_ai/knowledge.ts`：`uploadAiKnowledgeDocument` 增加 `use_ocr`；`searchAiKnowledge` 增加可选 `opts`（min_score/use_rerank/filters/rewrite）；新增 RAG 任务与评测接口封装。
- `frontend/src/views/module_ai/knowledge/index.vue`：
  - 文档 tab：新增「解析方式（自动/仅文本层）」、策略新增「按标题树」、新增**进度列**（`el-progress`，**只轮询该行任务**，终态才刷新列表）；
  - 分块 tab：新增「类型（父块/子块）」与「Token」列；
  - 检索测试：新增相似度下限、文件过滤、Rerank 开关、查询改写；结果展示**耗时分解**（总耗时/嵌入耗时/重排状态）；
  - 新增「评测」tab：数据集选择、TopK/Rerank 配置、运行按钮、运行记录表（Recall/MRR/NDCG/状态），进度用独立横幅承载；
  - `onUnmounted` 清理全部轮询定时器。

静态检查（实测）：

```
cd frontend
pnpm run type-check        → exit 0（无类型错误）
pnpm exec eslint --fix <两个改动文件>
 → 剩余 2 个 error：openRenameRel / onGraphNodeClick 未使用
   已在 git HEAD 版本中确认同样是「只定义未引用」，属**改动前既有**问题
```

> 注：worktree 缺少 gitignored 的生成文件 `src/types/auto-imports.d.ts`、`src/types/components.d.ts`
> 与 `node_modules`，已从主仓复制/建目录联接（本地环境，不入库）。

## 2. 测试结果（实测）

```
cd backend
.venv/Scripts/python.exe -m pytest \
  tests/test_ai_knowledge.py tests/test_ai_rag_config.py tests/test_ai_rag_persist.py \
  tests/test_ai_rag_embedding.py tests/test_ai_rag_tasks.py tests/test_ai_rag_search.py \
  tests/test_ai_rag_chunking.py tests/test_ai_rag_parent_child.py \
  tests/test_ai_rag_parsing.py tests/test_ai_rag_eval.py \
  tests/test_ai_assistant.py tests/test_ai_workflow.py -q
→ 107 passed, 2 warnings in 122.91s
```

纯逻辑测试（`PYTEST_NO_APP=1`，约 25s 含导入）：
- `test_ai_rag_config.py`：4 passed
- `test_ai_rag_persist.py`：3 passed
- `test_ai_rag_embedding.py`（无应用部分）：缓存/降级/分片/统计
- `test_ai_rag_chunking.py`：6 passed
- `test_ai_rag_eval.py`：指标手算期望值（Recall@2=0.5、MRR=0.5、NDCG@3=0.6934）

lint：

```
.venv/Scripts/ruff.exe check app/plugin/module_ai/knowledge \
  app/plugin/module_ai/models/service.py app/scripts/init_app.py
→ All checks passed!
```

## 3. 索引证据（真实 dev 库，PostgreSQL 18.6 / pgvector 0.8.6）

```
cd backend
.venv/Scripts/python.exe scripts/verify_rag_indexes.py
```

实测输出要点：

```
[OK]   索引存在：idx_chunk_embedding_hv
[OK]   索引存在：idx_chunk_fts
Limit
  ->  Index Scan using idx_chunk_embedding_hv on ai_knowledge_chunks
[OK]   向量检索索引可用（Index Scan using idx_chunk_embedding_hv）
分块总数 9，其中 embedding_hv 非空 9
```

说明：dev 库只有 9 行，规划器默认会选择「顺序扫描 + 排序」（小表更便宜），
因此脚本用 `enable_seqscan/bitmapscan/sort = off` 证明**索引本身可用**；
数据量上来后会自然走索引。脚本同时完成存量 JSONB 向量 → `embedding_hv` 回填。

## 4. 正确性修复证据（测试覆盖）

| 项 | 用例 | 结果 |
|---|---|---|
| `kb_quality` 字段名错误（原先必 500） | `test_kb_quality_returns_200` | ✅ |
| 删文档级联清分块（孤儿分块） | `test_delete_document_cascades_chunks` | ✅ |
| 重解析去重（替换式） | `test_reparse_is_idempotent` | ✅ |
| 删库级联清日志/标注（防 id 复用串库） | `test_search_log_records_embed_ms` 回归 | ✅ |
| 上传异步化 + 任务进度 | `test_upload_returns_task_and_worker_finishes` | ✅ |
| 取消任务不写分块 | `test_canceled_task_does_not_write_chunks` | ✅ |
| 非 PG 回退（SQLite） | `test_vector_search_without_pg`、`test_fulltext_unavailable_falls_back_empty` | ✅ |
| 嵌入失败不静默降级 | `test_failure_raises_when_fallback_disabled` | ✅ |
| 换模型提示重建 | `test_model_change_marks_rebuild_needed` | ✅ |
| rerank 精排与降级 | `test_rerank_orders_and_scores`、`test_rerank_degrades_on_error` | ✅ |
| 父子块回填 | `test_parent_child_ingest_and_backfill` | ✅ |
| MinerU 结果转换（表格/页码） | `test_html_table_conversion_and_page_offsets` | ✅ |

## 5. 阶段一尚未完成（待做）

1. **前端视觉验证（Task 31 的一部分）**：需在 worktree 里启动 dev 服务后截图核对。按 AGENTS 规矩
   **未擅自启动服务**（5181/8002 上可能是你在跑的服务）；需要你确认端口可用后再做。
2. **真实环境端到端**：
   - 用真实扫描件 PDF 走 `/documents/upload` → MinerU OCR → 校验分块带正确 `page`；
   - 真实嵌入模型（`smbs/Embedding-4B`，2560 维）入库并检索，确认真实语义召回；
   - 同一评测集跑 `use_rerank=false/true` 两组，记录 Recall/MRR/NDCG 对比数字（前端「评测」tab 已可发起）。
3. **评测集数据**：需要在 dev 库创建评测集与条目（页面上暂无「新建评测集/条目」表单，先用接口或脚本）。
4. **兼容清理**：`service._pg_search` / `_minmax_scores` / `_fuse_weighted` / `_py_search` 已成为死代码，留待下一轮删除。
5. **迁移脚本**：本轮用 `extensions.py` 幂等补列/建表（存量库重启即生效）；仍需补一份手写 alembic revision 以覆盖全新库迁移链。

## 6. 真实环境端到端（2026-10-19 实测，worktree 后端 8003 + 真库/真网关）

前置：`SERVER_PORT=8003` 起 worktree 后端（**不复用主仓 8002**），`openapi.json` 已确认新路由
（`/ai/knowledge/eval/sets` 等）生效——即「跑的是新代码」这一步有证据。

| 验证项 | 实测结果 |
|---|---|
| 生成带中文的扫描件 PNG → `/documents/upload` | 返回 `task_id`，任务 `succeeded`（step=完成） |
| MinerU OCR | 分块内容 `## 设备检修记录：液压泵压力正常`（识别正确），`page=0` |
| 真实嵌入模型 | 分块 `vector_model=smbs/Embedding-4B`、`dimension=2560` |
| 语义检索（字面无重叠） | query「休假天数是多少」→ 命中 policy.txt「员工每年享有带薪年假十五天」，score=0.0164（RRF 分） |
| 评测运行（rerank off/on） | 两组均 `succeeded`；n=2, recall=1.0, mrr=1.0, ndcg=1.0（**该小集区分度不足，暂无 rerank 提升数字**） |
| 清理 | 脚本自动删除测试知识库 |

### 端到端抓出并修复的真实缺陷（`0x00` 入库失败）

现象：上传 PNG 返回 400 —— `asyncpg.exceptions.CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00`
（图片被当文本解码后写入 `ai_knowledge_documents.content`，PG 的 text 列不接受 NUL）。

修复：
1. `parsing/text.py::decode_text` 统一剔除 `\x00`（防御任何二进制/脏编码输入）；
2. `service.upload_document` 对图片后缀**不做文本层预解析**（直接留空，由 worker 从 RustFS 取原始字节走 OCR）。

> 说明：这两个修复是「真实环境跑一遍」才暴露出来的，单元测试（SQLite）无法发现 NUL 问题。

## 7. 收口进度与一个被推翻的假设

### 7.1 死代码清理：**假设不成立，已中止**

原以为 `_pg_search` / `_minmax_scores` / `_fuse_weighted` / `_fuse_rrf` 已被新检索管线取代。
删除脚本加的安全校验（「除定义外不得有其它引用」）直接拦下：

```
[ABORT] _pg_search 仍被引用：uses=3 defs=1
service.py:1905  vec = await cls._pg_search([kb_id], query, top_n, False, "vector")
service.py:1910  ft  = await cls._pg_search([kb_id], query, top_n * 3, False, "fulltext")
```

即：`suggest_annotate`（「检索失败？推测相关分块」）仍在用它做向量/全文双路召回。

**正确的清理顺序**（下一轮做）：
1. 把 `suggest_annotate` 的两处调用改为 `search.engines.vector_search / fulltext_search`（保持双路语义）；
2. 再删 `_pg_search` + `_minmax_scores` + `_fuse_weighted` + `_fuse_rrf`；
3. 顺带评估 `_py_search` / `_py_search_vector`（新管线已有非 PG 回退，疑似可删）。

> 教训：删「死代码」前先做**引用计数校验**，别凭印象——这次省下了一次把线上功能删坏的返工。

### 7.2 仍未完成

- 前端截图核对（环境已就绪，见 §1.1 注）；
- 手写 alembic revision（空库全链重放）；
- 上面 §7.1 的死代码清理；
- 合并回 main；
- rerank 提升数字（需构造有区分度的评测集，现有 2 条太简单）。
