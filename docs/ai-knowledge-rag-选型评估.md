# 知识库 RAG 插件选型与能力评估

> 对象：`backend/app/plugin/module_ai/knowledge/*`（RAG 检索）
> 评估日期：2026-10-03

## 1. 现状
- **分块**：`chunk_text`（定长 + 重叠）。
- **向量化**：`embedding.embed_texts` 优先走 OpenAI 兼容 `/embeddings`，失败回退**确定性哈希向量**（256 维，bag-of-words，可移植）。
- **检索**：`AiKnowledgeService.search` 取某知识库全部 chunk，在 Python 端按**余弦**排序返回 top_k。
- **图**：本轮新增 `graphrag`（jieba 关键词实体 + 共现关系），入库后自动建图，检索可带 `use_graph` 扩展邻居。

## 2. 插件评估结论

### pgvector —— **建议生产接入（大规模必需），当前可先不用**
- 现状向量存 `JSONB` 列表，检索在 Python 端对**该库全量 chunk** 逐个算余弦。数据量小（几百~几千 chunk）够用；**chunk 上万后延迟显著**。
- 建议：在生产 PostgreSQL 上 `CREATE EXTENSION vector;`，新增 `vector` 类型列 + **HNSW 索引**，检索用 `embedding <=> $1`（余弦距离）+ `ORDER BY` + `LIMIT`，避免全量 Python 计算。
- 说明：pgvector 是 PostgreSQL 扩展，**并非依赖库**，无需 `pip` 安装；仅需在 PG 中启用扩展并执行一次迁移（把现有 `vector` 列改为 `vector` 类型）。测试/无扩展时仍走现有 Python 余弦回退。
- 时机：当前 JSONB + Python 余弦可跑通；若单库 chunk 量预计超过 ~1 万，建议切换到 pgvector。

### jieba —— **已接入（推荐）**
- jieba 是 **Python 分词库**（`pip install jieba`，本项目已加依赖，来自清华源），**不是 PG 插件**。
- 用途：改进中文分词（`embedding._tokenize` 已改用 jieba），并作为 GraphRAG 关键词实体抽取（`graphrag.extract_keywords` 使用 jieba TF-IDF）。
- 结论：**已落地**，用于提升中文语义召回与图谱实体质量。

### AGE（Apache AGE）—— **建议先不引入**
- AGE 是 PostgreSQL 的图扩展（Cypher）。**当前不必要**：
  - GraphRAG 的实体-关系用自有表 `ai_knowledge_entities/relations` 实现，可移植（SQLite 亦可），无需额外扩展与学习成本。
  - AGE 适合海量、多跳、强连通图谱查询；当前轻量共现图谱规模小、1~2 跳扩展已够。
- 未来若图谱规模巨大或需复杂递归/Cypher 查询，再评估 AGE / Neo4j。

## 3. 已实现能力
- **常规分段检索**：定长 + 重叠分块 → 向量检索（余弦）→ 拼上下文（`retrieve`）。
- **GraphRAG**：jieba 关键词抽实体 → 同 chunk 共现建关系 → 检索时 `graph_retrieve` 扩展邻居、附带相关分块，拼入上下文（`retrieve(use_graph=True)`）。
- **能力接口**：
  - `GET /ai/knowledge/bases/{id}/graph`：返回图谱节点/边（供前端可视化）。
  - `POST /ai/knowledge/bases/{id}/search`：支持 `use_graph`。
- 测试：`tests/test_ai_knowledge.py` 覆盖入库→图→检索。

## 4. 建议下一步（若需）
- pgvector 生产接入：建 `vector` 列 + HNSW，`search` 增加 pgvector 快速路径（按 `DATABASE_TYPE`/扩展存在性分支）。
- 图谱可视化前端（已有 `/graph` 数据接口，可在知识库详情页展示）。
- 图谱引入 LLM 实体/关系抽取（jieba 关键词为轻量兜底）。
