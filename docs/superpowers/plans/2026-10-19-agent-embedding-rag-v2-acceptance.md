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
| WS8 前端页签与最终验收（Task 28–31） | ⏳ 待做 | — |

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

1. **前端（Task 28–30）**：评测页签、文档上传进度/解析方式、分块父子视图、检索测试阈值/过滤/rerank 开关、耗时分解。
2. **真实环境端到端（Task 31 剩余）**：
   - 用真实扫描件 PDF 走 `/documents/upload` → MinerU OCR → 校验分块带正确 `page`；
   - 真实嵌入模型（`smbs/Embedding-4B`，2560 维）入库并检索，确认真实语义召回；
   - 同一评测集跑 `use_rerank=false/true` 两组，记录 Recall/MRR/NDCG 对比数字。
3. **兼容清理**：`service._pg_search` / `_minmax_scores` / `_fuse_weighted` / `_py_search` 已成为死代码，留待下一轮删除（避免一次性改动过大）。
4. **迁移脚本**：本轮用 `extensions.py` 幂等补列/建表（存量库重启即生效）；仍需补一份手写 alembic revision 以覆盖全新库迁移链。
