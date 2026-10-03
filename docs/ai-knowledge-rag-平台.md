# AI 知识库（multi-modal RAG 平台）使用与架构说明

> 本文档介绍 AIStation「AI 管理 → 知识库」模块的能力、使用方法与后端架构，覆盖
> 多模态检索、图谱、分块标注、检索闭环与检索统计。

## 一、模块定位

知识库是一个**可编辑、可配置、可重建、可追溯**的多模态 RAG 平台，支撑：

- 文档/文本入库 → 分块 → 向量化；
- 多模态检索：向量 / 中文全文 / 图谱 / 子串全文 / 混合加权；
- 图谱（GraphRAG）可视化与编辑：实体、关系、**实体绑定分块**；
- **分块标注**：给分块加别名/锚点/备注，标注进入三路索引，大幅提升“换说法也能命中”；
- 检索闭环：检索失败自动推测相关分块 → 一键标注 → 台账可追溯；
- 检索统计：检索次数、命中率、引擎分布、按天趋势。

## 二、检索模式（mode）

知识库检索支持以下模式，`POST /api/v1/ai/knowledge/bases/{id}/search` 传 `mode`：

| mode | 说明 | 底层 |
|------|------|------|
| `vector` | 纯向量语义检索 | pgvector（余弦+HNSW）；无向量列回退 Python 余弦 |
| `fulltext` | 中文全文分词检索 | PostgreSQL `jiebacfg`（pg_jieba）`ts_rank` |
| `hybrid` | 混合检索（向量+全文加权融合） | 见下 |
| `graph` | 图谱多跳检索 | Apache AGE Cypher / 自有表共现 + 绑定分块回溯 |
| `grep` | 子串全文（WikiLLM 式） | `ILIKE` 包含匹配 |

### 混合检索加权（hybrid）
请求可传 `vector_weight` / `fulltext_weight`（0~1，默认各 0.5）。
后端把向量、全文命中各自按 `score/max` 归一化后按权重合成（缺失侧计 0），
融合结果标记 `engine="hybrid"`。

### 分块/标注索引
每个分块的**可检索文本 = 正文 + 用户标注**。即对 `content || annotations文本` 建
向量（加/删标注自动重算向量）、中文全文 `to_tsvector`、子串 `ILIKE`。因此给分块
打上“别名”，用户换种说法提问也能命中该分块。

## 三、图谱（GraphRAG）

- 入库/重建时用 jieba TF-IDF 抽关键词建实体，按共现建关系；若启用 Apache AGE
  扩展则同步写入 AGE 图库，检索优先用 Cypher 多跳扩展邻居。
- **图谱编辑**：图形化（ECharts 力导向图）可编辑：
  - 实体：创建、编辑（改名/类型/权重，改名联动更新关系边 source/target）、删除；
  - 关系：创建、编辑（source/target/weight）、删除。
  - 保存后自动 AGE 重同步。
- **实体绑定分块**：每个实体可绑定多个分块（`ai_knowledge_entity_chunks`）。
  - 图谱检索命中实体时**优先回溯其绑定分块**（无绑定才回退正文包含匹配）；
  - 图谱节点按绑定分块数显示大小/颜色，label 显示「名称 (绑定数)」；
  - 点击图谱节点可直达该实体关联的分块列表。
- **标注自动纳入图谱**：给分块加标注时，用 jieba 提取标注关键词，自动建为
  图谱实体（`etype=annotation`）并绑定到该分块，使标注词也能通过图谱召回。

## 四、分块标注（召回增强闭环）

### 为什么需要标注
当用户提问检索不到某分块，但答案其实在该分块里，可给该分块打额外标注
（别名/锚点/备注）。标注文本进入**向量 + 中文全文 + 子串**三路索引，
下次用户换种说法提问即可命中。

### 入口
- 分块 tab：每行「标注」按钮，弹窗管理（添加/删除）；
- 检索结果：每条「+ 标注此分块」快捷入口；
- **检索失败建议标注**：检索成功后自动推测相关分块（向量召回但未被全文命中的
  分块），标记「已命中/未命中，建议标注」，可一键标注。每个标注记录**来源**
  （手动/检索/自动/图谱）与**触发查询**。

### 标注台账
`ai_chunk_annotation_logs` 表记录每次标注的 动作/文本/类型/来源/触发查询/操作人/时间。
详情抽屉「标注台账」tab 支持按来源、类型筛选与添加/删除统计。

## 五、检索统计

- 每次检索自动写入 `ai_search_logs`（查询/模式/top_k/命中数/命中的引擎/用户）。
- `GET /bases/{id}/search-stats?days=30` 返回：检索次数、命中率、平均命中、
  空命中次数、引擎分布、近 N 天按天趋势。
- 前端详情抽屉「检索统计」tab 展示统计卡 + 引擎分布 + 按天趋势表，天数可调。

## 六、前端页面（`frontend/src/views/module_ai/knowledge/index.vue`）

- **列表**：知识库列表（名称/描述/分块数/嵌入模型/图谱规模/状态/操作），
  「详情」打开抽屉。
- **详情抽屉**（多 tab）：
  - 概览：统计卡（分块/图谱节点/边/数据源）、描述/启用编辑、重建索引；
  - 文本入库：分段策略（定长/段落/句子）+ 块大小/重叠 + 嵌入模型；
  - 分块：列表 + 编辑内容（重向量化）+ 标注 + 删除；
  - 检索测试：模式选择 + 混合权重 + 结果（引擎标签/关键词高亮/图谱实体）
    +「+ 标注此分块」+ 检索失败建议标注；
  - 标注台账：筛选（来源/类型）+ 统计 + 明细表；
  - 检索统计：统计卡 + 引擎分布 + 按天趋势；
  - 图谱：ECharts 力导向图（节点标记绑定分块数）+ 编辑实体/关系 + 节点点击直达绑定分块。

## 七、后端架构（`backend/app/plugin/module_ai/knowledge/`）

```
controller.py   路由（CRUD + 检索/图谱/标注/绑定/统计）
service.py      业务（分块、向量化、多模态检索、图谱 CRUD、绑定、标注、统计）
schema.py       Pydantic 请求模型
model.py        ORM（bases/chunks/entities/relations/entity_chunks/annotation_logs/search_logs）
graphrag.py     图谱构建、AGE 同步、多跳检索、标注→实体同步
embedding.py    OpenAI 兼容嵌入 + 确定性哈希回退
extensions.py   启动自动建扩展/建列/建表
```

### 要点
- 分块向量存 `vector`(JSONB) + pgvector `embedding` 列（惰性建列 + HNSW）。
- 扩展/表在 `extensions.ensure_extensions`（启动）惰性创建，幂等。
- 全部接口带 `AuthPermission(["module_ai:knowledge:*"])` 权限校验。
- 依赖 PostgreSQL（pgvector/pg_jieba/age）；SQLite/无扩展自动回退 Python 检索。

## 八、常用接口速览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/bases/{id}/search` | 检索（mode/权重/use_graph） |
| GET  | `/bases/{id}/graph` | 图谱（节点带 chunk_count） |
| POST | `/bases/{id}/graph/entity` | 创建实体 |
| PUT  | `/bases/{id}/graph/entity/{eid}` | 编辑实体（改名联动关系） |
| PUT  | `/bases/{id}/graph/relation/{rid}` | 编辑关系 |
| GET  | `/bases/{id}/entities/{eid}/chunks` | 实体绑定分块 |
| POST | `/bases/{id}/entities/{eid}/bind` | 实体绑定分块 |
| POST | `/bases/{id}/chunks/{cid}/annotations` | 加标注（进索引+入图谱+记台账） |
| GET  | `/bases/{id}/suggest-annotate` | 检索失败建议标注 |
| GET  | `/bases/{id}/annotation-logs` | 标注台账 |
| GET  | `/bases/{id}/search-stats` | 检索统计 |
| POST | `/bases/{id}/rebuild` | 重建索引（重向量化+重建图谱） |

## 九、环境与依赖

- PostgreSQL 使用一体化镜像（pgvector 0.8.6 / pg_jieba / Apache AGE），
  `shared_preload_libraries=age,pg_jieba`；中文全文配置 `jiebacfg`。
- 嵌入模型：在「AI 管理 → 模型配置」配置 `usage=embedding` 的模型；知识库
  「嵌入模型」下拉只列 embedding 模型，未配则用确定性哈希向量。
