# 问数召回服务（Recall Service）设计

- 日期：2026-10-10
- 状态：**待评审**
- 路线：方案 B（自建召回服务）
- 范围：整体重构（召回链路 + 生成质量 + 语义层归一 + 可观测/评测）

## 一、背景：三个已实测的缺陷

问数当前的问题**不是「缺检索库」，而是**：召回单元没语义 → 分数被丢 → 无法解释/评测。

### 1.1 主召回弱，且短路屏蔽了更准的两级

- 链路顺序（`query/service.py:6265-6286`）：① Agno 语义 → ② pgvector → ③ 内存融合，
  且 ②③ 被 `if not tables:`（`:6272`）**短路**——① 只要返回任何东西（哪怕噪声）就独占。
- Agno 的检索单元是**裸标识符**（`_agno_seed_units`，`service.py:6174-6191`）：
  `数据表 {t}` / `表 {t} 的字段 {c}`——**没有中文名/注释/业务语义**。
- 我们自己的 `top_k` 根本没传给 Agno：`store.search` 调 `self._kb.search(question)` 不传
  `max_results`（`agno_store.py:99`），落到 Agno 类默认 **10** 条（agno `knowledge.py:53,614`）。
- 结果→表的映射靠**子串反推**（`service.py:6217-6220` 的 `if t in txt`），
  而 `seed` 时其实已写入 `meta_data["tables"]`（`agno_store.py:86`）——**元数据被丢弃**。

**实测（对照实验）**：题「各框架下的训练模型数量」

| 级 | 返回 |
|---|---|
| ① Agno | `ai_agents, ai_apps, ai_call_logs`（噪声） |
| ② pgvector | `ai_call_logs, train_evals, train_model_repos, **train_models**, train_predicts, train_tasks`（正确，被跳过） |
| FINAL | **不含 `train_models`** → 该题基准失败 |

把 ① 置空后重跑：**`train_models` 回到 prompt（True）**。

另一题「每个摄像头各产生多少条告警」的 ① 返回 `[ai_call_logs] 的字段 usage/description/result/error`（纯噪声），
并给 prompt 塞进 `ai_agents/ai_apps/ai_messages`——**这正是「问销售额却拿 `ai_call_logs.cost`」的温床**。

### 1.2 分数被丢 + 字典序截断

- Agno 其实**算好了归一化相似度**并写入 `meta_data["similarity_score"]`，
  且 `PgVector` 支持 `similarity_threshold`（agno `pgvector.py:92,1036-1038`）——我们都没用。
- 收尾是 `return sorted(tables)[:top_k]`（`service.py:6367`）：**按字典序截断，所有打分被丢弃**。

### 1.3 召回不确定

`_agno_search_tables` 在「未播种且 count==0」时**派生后台播种并返回 `[]`**（`service.py:6209-6214`）：
**首次问答走 pgvector（准）、播种完成后走 Agno（噪声）**——同一问题召回结果随启动状态变化。

### 1.4 基线数字（本次实测，dev + DashScope qwen-plus）

| 基准 | 结果 |
|---|---|
| 快路径（20 题指标模板） | 语义精度 **100%**、P50 **208.5ms** |
| 慢路径（98 题 NL2SQL） | 结果精度 **94.9%**、P50 **7936ms** |

慢路径失败簇：**联表 2 / 多维报表 2 / 时间窗口 1**（本体对象 5/5、本体黑话 6/6 全对）。
金标对照显示失败含：join 方向错（驱动表选错→0 行）、LEFT/INNER 语义错、**生成 SQL 为空**、输出列名/排序不对齐。

## 二、目标与非目标

**目标**
1. 召回**准**：把「正确答案表被召回又被丢掉」消灭；用中文业务词（表/字段中文名、别名、同义词）能召回。
2. 召回**稳**：同一问题任何时刻结果一致；每问可解释（哪几张表、各通道贡献多少分）。
3. **可评测**：新增离线 `Recall@k`（从金标 SQL 抽应使用的表）。
4. **语义层归一**：本体成为唯一权威语义源，消除问数自建并行语义。
5. 整体回答「问数怎么做最优」：快路径优先 + 慢路径受本体约束 + 反馈闭环。

**非目标（本轮不做）**
- 不引入新的外部检索框架/reranker 模型（方案 C 不做）。
- 不改 `ask`/`stream` 的对外接口与返回结构。
- 不做「按场景问数 / 决策问答」（scenario/decision 仍不接问数）。

## 三、现状关键事实（实现时的锚点）

| 事实 | 位置 |
|---|---|
| pgvector 表先例：`ai_query_asset_vectors(asset_type, ref, txt, tables JSONB, embedding vector(2560))` | `service.py:6106-6108` |
| 嵌入维度 2560、模型取 `usage="embedding"`（`Embedding-4B`） | `agno_embedder.py:19-37` |
| 关键词+中文注释打分（表名 6 / 中文注释 5 / 列名 3 / 片段 1） | `_relevant_tables` `service.py:6370-6409` |
| 本体别名→表（限 3 张） | `service.py:6320-6342`、`_ONT_ALIAS_MAX_TABLES=3` `:752` |
| 实体名词→表 | `_cfg_entity_map` `:6344-6348` |
| KG 图遍历 / AGE 扩表 | `:6349-6366` |
| 本体语义接口：`semantic_context` / `concepts` / `object_table_map` | `ontology/semantic.py:189,334-384,56-71` |
| 本体 Link Type（关系，含基数/join_method） | `ai_ont_link`；`semantic.py:368-383` |
| 硬编码 `ont_{tgt}`（数据源支撑对象会失败） | `service.py:2294` |
| `_scan_ont_tables` 只认 `ont_` | `service.py:808-814` |
| KG 概念边读 `ai_query_concept`（非本体） | `agno_kg.py:93` |
| `agno_tool_agent` 默认 false | `service.py:4994` |
| 配置读写 `_cfg/_cfg_bool/_cfg_int/_cfg_float` | `service.py:4994` 附近 seed |

## 四、设计

### 4.1 数据模型：版本化语义单元表

`ai_query_recall_units`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | bigserial | |
| `kind` | text | `table` / `ds_table` / `object` / `property` / `relation` / `metric` / `term` / `concept` / `fewshot` |
| `ref` | text | 唯一键：表名 / 对象 code / 属性 code / 指标 key …（与 `kind` 组成唯一） |
| `text` | text | 高语义密度文本（§4.2） |
| `meta` | jsonb | `{"tables":[...], "object":code, "boost":1.0}` |
| `embedding` | `vector(2560)` | 与现有资产向量表一致 |
| `version` | bigint | 构建批次；支持增量重建与回滚 |
| `is_deleted` / `created_time` / `updated_time` | | 与项目惯例一致 |

索引：`UNIQUE(kind, ref)`；`embedding` 上建 ivfflat/hnsw（与现有资产表保持一致做法）。

### 4.2 召回单元构建

| kind | 文本模板 | 来源 |
|---|---|---|
| `table` | `表 {table}｜中文名:{alias}｜业务域:{domain}｜描述:{description}｜场景:{business_scenarios}｜列: {col}({中文名}), …` | `ai_query_asset` + `ai_query_asset_columns` |
| `ds_table` | 同上，来源为外部数据源同步表结构 | `ai_query_schema`（数据源 schema） |
| `object` | `对象 {name}｜别名:{aliases}｜同义词:{synonyms}｜属性: {prop名}({code}), …｜关系: …` | `ontology/semantic.py` |
| `property` | `属性 {name}({code})｜所属表 {table}` | 同上 |
| `relation` | `关系 {source}→{target}（{card}，join: {src_field}={tgt_field}）` | `ai_ont_link` |
| `metric` | `指标 {name}({key})｜口径:{sql_template}｜单位:{unit}` | `ai_query_metric` |
| `term` | `术语 {term}｜→指标 {metric_key}｜→字段 {field_path}` | `ai_query_dictionary` |
| `concept` | 概念名/描述/同义词/涉及表 | 本体 `semantic.concepts()`（§4.6 归一后） |
| `fewshot` | 问题→SQL 摘要 | `ai_query_fewshot` |

**构建是显式动作**：`POST /ai/query/recall/rebuild`（全量或按 `ref` 增量），
写入时统一 `version = 当前时间戳`；不再在请求内后台播种（§4.7）。

### 4.3 多路并行召回 + RRF 融合 + 阈值

四个通道**并行**执行（互不短路），各自输出 `{table: score}` 或有序表列表：

| 通道 | 依据 | 备注 |
|---|---|---|
| ① 向量 | `SELECT meta->'tables', 1-(embedding <=> :qvec) FROM ai_query_recall_units WHERE is_deleted=false ORDER BY embedding <=> :qvec LIMIT :n` | **直接查 pgvector**，绕过 Agno 同步引擎与默认 10 条 |
| ② 关键词 | jieba 词面 + **中文注释**加权（复用 `_relevant_tables` 打分，归一化） | 保留既有「注释才是业务语义」的经验 |
| ③ 本体强信号 | 别名 / 同义词 / 对象名 / 属性名**精确命中**（权重：别名>同义词>属性>对象名） | 对象名权重最低（防通用词噪声，见 `service.py:6313-6319` 的踩坑记录） |
| ④ 实体名词 | 现有 `_cfg_entity_map` | 保持不变 |

**融合**：`RRF`（Reciprocal Rank Fusion）`score(t) = Σ_c w_c / (k + rank_c(t))`，`k=60`；
`w_c` 可配（默认 向量 1.0 / 关键词 0.8 / 本体强信号 1.2 / 实体 0.6）。
> 选 RRF 而非线性加权：各通道分数尺度不同，RRF 只用**排名**，天然可比、实现极简、无需调归一化。

**过滤与截断**：`score < min_rrf_score` 丢弃 → **按融合分数取 `top_k`**（默认 12）→ 若为空则回退核心业务表（保留现有兜底）。
**淘汰** `sorted(tables)[:top_k]`（`service.py:6367`）。

### 4.4 关系扩表（保证 join 键在上下文）

1. 取 §4.3 的种子表；
2. 用**本体 Link Type**（`ai_ont_link`）做**一跳**扩展：加入 join 目标表与其 join 字段；
3. 生成「显式 join 路径」文本（`{src_table}.{src_field} = {tgt_table}.{tgt_field}（{card}）`）注入 prompt；
4. 现有 KG/AGE 扩表**保留为补充**（本体关系优先）。

目的：治「驱动表选错 → 0 行」「LEFT/INNER 用错」这类联表失败。

### 4.5 注入与生成质量（P1）

- `_build_schema_context` 只注入**最终表集合** + 本体语义块；关系块补**方向/基数**。
- 本体块补：函数 `kind`、属性**枚举取值**（本体 `enrich_ontology_semantics` 已解析）。
- 生成侧三项：
  1. **联表方向规则**：1:N 以 N 端为驱动表；「仅发生过/有关系的」用 INNER JOIN，「每个/各主实体」用 LEFT JOIN + COALESCE；
  2. **空 SQL / 空结果自纠错**：`empty_self_correct` 现只覆盖空**结果**，补空 **SQL** 与 `path=None` 的重试；
  3. **输出列名对齐**：用本体属性中文名 + 问题措辞约束 `AS` 别名与排序键。

### 4.6 语义层归一（本体 = 唯一权威）

- `ai_query_concept` 保留为**兼容视图**：写入仍可（双写），**读路径统一走 `semantic.concepts()`**。
- 修 `_resolve_ont_entity` 的 `ont_{tgt}` 硬编码（`service.py:2294`）→ 用 `semantic.object_table_map()`。
- 修 `_scan_ont_tables`（`service.py:808-814`）→ 与 `object_table_map()` 求交（非 `ont_*` 对象也能被溯源）。
- KG 概念边（`agno_kg.py:93`）改读本体语义层。

### 4.7 可观测与确定性

- 每问落 **`recall_trace`**：`{channels: {name: [{table, score}]}, fused: [...], final: [...], expanded: [...], latency_ms}`。
  存储方式（已定）：给问数消息表 `ai_query_message` 增加 `recall_trace jsonb` 列，问答落库时一并写入；
  同时按 `[query][recall]` 前缀打一条**精简日志**（表集合 + 耗时），便于无库排障。
  完整 trace 由 `GET /ai/query/recall/probe` 返回（不依赖历史消息）。
- **确定性**：单元构建是**显式动作**，触发点有两个且都在请求路径之外——
  1. `POST /ai/query/recall/rebuild`（手动全量/增量）；
  2. **启动期检查**：比较「单元表 `max(version)`」与「资产/本体最新 `updated_time`」，落后则在 lifespan 内**同步重建**（不阻塞请求，不派生后台播种任务）。
  请求路径**只读**，不再有 `_agno_search_tables` 那种「未播种就后台播种并返回空」的分支。
- 运维口子：`POST /ai/query/recall/rebuild`、`GET /ai/query/recall/probe?question=`（返回 trace，便于排障）。

### 4.8 配置与兼容

- 配置项（`ai_query_settings`，默认值保证**不配置也能工作**）：
  `recall_enabled`(true)、`recall_top_k`(12)、`recall_min_score`(0)、
  `recall_w_vector`(1.0)、`recall_w_keyword`(0.8)、`recall_w_ontology`(1.2)、`recall_w_entity`(0.6)、
  `recall_expand_hops`(1)、`recall_trace_enabled`(true)。
- Agno 表（`ai.ai_query_agno_units`）**保留但降级为可选一路**（默认关闭向量通道走 Agno，改直查 recall_units）；
  `ai_query_asset_vectors` 保留一段时间后废弃。

## 五、评测与验收

**新增离线指标 `Recall@k`**：从 98 题金标 SQL 解析出「应使用的表」，对每题调用召回（不调 LLM），算命中率。
（解析金标 SQL 的表名用轻量正则 + 与 schema 求交；金标里用到的表即 ground truth。）

| 指标 | 基线 | 目标 |
|---|---|---|
| 98 题结果精度 | 94.9% | **≥97%** |
| Recall@8（新） | 先测基线 | 显著高于基线（先测再定阈值） |
| 快路径语义精度 | 100% | 不低于 100% |
| 慢路径 P50 | 7936ms | 不劣化（召回层不得成为新瓶颈） |
| 专项题「各框架下的训练模型数量」 | 失败 | **必须通过** |
| 召回确定性 | 播种前后不同 | 同一问题两次结果一致 |

## 六、分阶段落地（每阶段独立可验收）

1. **单元表 + 构建 + 向量通道 + RRF/阈值** → 跑基准量化（先拿收益）。
2. **关系扩表 + 注入改造**（方向/基数/枚举/kind）。
3. **语义层归一 + `recall_trace` + Recall@k 指标**。
4. **生成质量 P1**（联表规则、空 SQL 自纠错、输出对齐）。
5. **闭环**（正例→指标沉淀、负例→few-shot）。

## 七、风险与缓解

| 风险 | 缓解 |
|---|---|
| 单元文本变长 → 向量检索变慢 | 单元数按表/对象数量级（数百），`LIMIT n` + 索引；P50 纳入验收 |
| RRF 权重不当 → 召回变差 | 权重可配 + 用 Recall@k 做网格；先测基线再定默认 |
| 关系扩表引入噪声表 | 只扩**一跳**、且仅扩本体声明的 join；扩表结果单独标记、不进 top_k 计分 |
| 语义层归一造成回归 | `ai_query_concept` 保留兼容视图 + 全量 pytest 门槛 |
| 新表迁移 | `CREATE TABLE IF NOT EXISTS` 幂等；构建可重复执行 |

## 八、明确不做（本轮边界）

- 不接 `scenario` / `decision` / `proposal` / `object_view` 到问数。
- 不引入 reranker / 新嵌入模型。
- 不改 `ask`/`stream` 返回结构；不动快路径的指标匹配逻辑。
- 不改前端。
