# AIStation 一体化 PostgreSQL 18 镜像：pgvector + pg_jieba + Apache AGE

> 用途：AI 知识库 RAG 所需的「向量检索(pgvector) + 中文分词全文检索(pg_jieba) + 图数据库(AGE)」。
> 基础镜像：`postgres:18-bookworm`（最新 PG18）；版本见 `devops/postgres/Dockerfile`。

## 1. 镜像内容与版本
| 扩展 | 版本 | 说明 |
|------|------|------|
| pgvector | **0.8.6** | 向量相似检索（官方支持 PG 18） |
| pg_jieba | **v2.0.1** | 中文分词全文检索（提供 `jieba` 文本搜索配置） |
| Apache AGE | **PG18 分支 / 1.7.0** | 图数据库扩展（Cypher） |

## 2. 构建
```bash
docker build -f devops/postgres/Dockerfile -t aistation-pg-rag:18 devops/postgres
# 可选覆盖版本
# docker build --build-arg PGVECTOR_VERSION=0.8.6 --build-arg PGJIEBA_VERSION=2.0.1 --build-arg AGE_VERSION=PG18 \
#   -f devops/postgres/Dockerfile -t aistation-pg-rag:18 devops/postgres
```

## 3. 运行
AGE 需要在 `shared_preload_libraries` 中加载，镜像默认已带 `-c shared_preload_libraries=age`：
```bash
docker run --name aistation-pg-rag \
  -e POSTGRES_USER=root -e POSTGRES_PASSWORD=ServBay.dev -e POSTGRES_DB=aistation \
  -p 5433:5432 -v /path/to/data:/var/lib/postgresql/data \
  aistation-pg-rag:18
```
> 若不用镜像默认 CMD，请在 `postgresql.conf` 写入：`shared_preload_libraries = 'age'`。

## 4. 启用扩展（首次建库自动执行 `init-extensions.sql`）
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_jieba;
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = public, ag_catalog;
```

## 5. 能力示例

### 中文关键词/全文检索（pg_jieba）
```sql
-- 建 jieba 全文索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunk_fts
  ON ai_knowledge_chunks USING gin (to_tsvector('jiebacfg', content));

-- 关键词检索
SELECT chunk_id, content
FROM ai_knowledge_chunks
WHERE to_tsvector('jiebacfg', content) @@ plainto_tsquery('jiebacfg', '智能体编排')
LIMIT 5;
```

### 向量检索（pgvector）
```sql
-- 建 vector 列 + HNSW 索引
ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS vec vector(256);
CREATE INDEX IF NOT EXISTS idx_chunk_vec ON ai_knowledge_chunks USING hnsw (vec vector_cosine_ops);

-- 语义检索（余弦距离）
SELECT chunk_id, content, 1 - (vec <=> :query_vec) AS score
FROM ai_knowledge_chunks
ORDER BY vec <=> :query_vec
LIMIT 5;
```

### 图检索（Apache AGE）
```sql
SELECT create_graph('kb_graph');
-- 建图后，用 cypher 做多跳邻居查询
SELECT * FROM cypher('kb_graph', $$
  MATCH (a)-[]-(b) WHERE a.name = '人工智能' RETURN b.name
$$) AS (name agtype);
```

## 6. 接入本项目知识库
- 现有分块 `vector` 列是 `JSONB`；若启用 pgvector，建议**新增** `vec vector(256)` 列（保留 JSONB 兜底），并把 `knowledge/service.py::search` 在 `DATABASE_TYPE=postgresql` 且 `vector` 扩展存在时切到 pgvector 快速路径（`vec <=> $1`）。
- 关键词检索可在 `search` 中并行跑 pg_jieba 全文检索并合并（保留 SQLite 回退）。
- GraphRAG 目前用自有实体/关系表（可移植）；若需复杂图查询，可把实体/关系同步到 AGE 图，用 cypher 做多跳扩展。

## 7. 从 PG17 迁移到 PG18 注意
- 本项目现有 `aistation-pg`（postgres:17）。切 PG18 需**数据迁移**：`pg_dumpall` / `pg_dump` 导出后在新容器导入，或 `pg_upgrade`。
- 迁移后需重新 `CREATE EXTENSION` 三个扩展并重建相关索引（向量/HNSW 索引需重建）。

## 8. 验证
```bash
docker run --rm -it aistation-pg-rag:18 psql -U root -d aistation -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','age','pg_jieba');"
```

