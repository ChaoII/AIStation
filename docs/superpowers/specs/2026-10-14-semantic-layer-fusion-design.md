# 智能问数「语义层融合」设计方案（本体 + 指标 + 三级降级）

> 版本：v1（评审稿）
> 日期：2026-10-14
> 适用范围：`backend/app/plugin/module_ai/query/`、`backend/app/plugin/module_ai/ontology/`、
> `frontend/src/views/module_ai/{integration,ontology,query}/`
> 定位：在**不推翻现有问数**的前提下，把「本体（对象/属性/关系）」「指标（权威口径）」「执行（三级降级）」
> 融合为一套**金标准语义层**；用**大模型自动建模**把燃煤业务库（`ds:4`）的语义补齐；
> **LLM 只做「择义」，不「编口径」**。对标 Palantir Ontology / SuperSonic 指标平台 / WrenAI 语义模型。

---

## 0. 背景与目标

### 0.1 现状（三轮调研结论）

- 本项目**已具备**语义执行的全部原料：本体对象/属性/关系（`ai_ont_*`）+ 实例层（`instance_search/aggregate/pivot`，已接行/列级权限）+ 指标（`ai_query_metrics`，带 `sql_template` 权威口径）+ `ask()` 已实现 **fast→object→slow** 三级降级。
- 但存在**三处硬缺口**（2026-10-14 A/B 实测：对象查询开启后 `data_accuracy` 0.40→0.25，`object_rate=0.40` 却更差）：

| 编号 | 缺口 | 证据 |
|---|---|---|
| **F1** | **本体实例层只查系统库**，`ai_ont_object.datasource_id` 被忽略 | `ontology/service.py:2552 _instance_meta` / `:2532 _table_columns` / `:439 _exec` 全走 `async_db_session()`（主库） |
| **F2** | **指标没进对象查询执行层**，口径被绕过靠 LLM 重猜 | `object_query.py:301 render_ir_prompt` 不注入指标；`ObjectQueryIR`(40) 无 metric 节点；`object_exec.execute_ir` 不读 `ai_query_metrics` |
| **F3** | **无「大模型自动建模」管线**，本体侧无 LLM 生成对象/属性/关系入口 | `suggest_metrics_terms`(4894) 仅回候选 JSON 不落库；本体只有规则 `enrich_ontology_semantics`(606) |

### 0.2 目标

1. 用大模型把**燃煤业务库（`ds:4`/`ezdcs_pg`，331 张表）**的语义自动建模成金标准：对象 / 属性 / 关系 / 指标（含可验证口径）。
2. 让查询走**三层融合语义**：指标（确定性口径）→ 对象 IR（本体实例层，支持任意数据源）→ NL2SQL（兜底）。
3. 「数据与集成」「智能问数」「本体」三处都能**筛选表/字段、标注数据、建立关联关系、审核指标**。
4. 在**问数评测模块**新建「燃煤业务语义执行层评测集」，用它验收。

### 0.3 非目标（YAGNI）

- 不引入第二套 AI 框架（一律 agno）；不替换 agno 调用链路。
- 不重写 `ask()` 既有降级骨架，只**扩展**。
- 不做指标的物化/索引管道（Palantir Funnel 级），实例层仍直连数据源。
- 不建独立「评测数据集表」（见 §2.3，用字段承载，够用）。

---

## 1. 总体架构：三层语义中枢 + 三级执行降级

```
┌─ 本体层（Palantir 式）─────────────────────────────────┐
│ 对象 / 属性 / 关系，带 datasource_id + backing_table     │
│ → 可指向任意数据源（含燃煤库 ds:4）                       │
│ 大模型自动建模产出 + 人工筛选/标注/审核（工作副本/提案）    │
└─────────────────────────────────────────────────────────┘
                     ▲ 结构化绑定（新增）
┌─ 指标层（SuperSonic / WrenAI 式）───────────────────────┐
│ ai_query_metrics = 唯一权威口径                          │
│ 新增「指标 ↔ 本体对象/属性」绑定：指标声明基于哪个对象、    │
│ 哪个属性、什么聚合、哪些维度                               │
└─────────────────────────────────────────────────────────┘
                     ▼
┌─ 执行层（三级降级，LLM 只择义）─────────────────────────┐
│ ① 指标命中：确定性、零 LLM、口径权威（含流式）             │
│ ② 对象 IR：LLM 择义 → 本体实例层执行（支持任意数据源）      │
│ ③ NL2SQL：兜底                                            │
└─────────────────────────────────────────────────────────┘
```

**核心原则**：语义（对象/属性/关系/指标）是**受控词汇表**；LLM 只能在受控词汇上做**选择**，SQL/聚合口径由**确定性执行器**产出。

---

## 2. 数据模型改造

### 2.1 本体对象支持自定义数据源（F1 的数据面）

- `ai_ont_object` 已有 `datasource_id INTEGER` + `backing_table VARCHAR(160)`（`ontology/service.py:293-294`）。
- **改造点**：`upsert_object`（:1524）已支持写入二者；**新增**校验——当 `datasource_id` 非空时，`backing_table` 必须在该数据源的 schema 白名单（`ai_query_schema`）内。
- **不改表结构**，只补校验与消费（消费在 §4.1）。

### 2.2 指标 ↔ 本体对象/属性 结构化绑定（F2 的数据面）

给 `ai_query_metrics` **新增列**（`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，沿用 `_ensure_marking_columns` 风格，兼容 SQLite 测试库）：

| 新列 | 类型 | 含义 |
|---|---|---|
| `object_code` | VARCHAR(80) | 绑定本体对象 code（可空=模板型指标） |
| `property_code` | VARCHAR(80) | 绑定本体属性 code（聚合对象，可空） |
| `agg_fn` | VARCHAR(16) | 绑定型指标的聚合：count/sum/avg/min/max |
| `bound_dimensions` | JSONB | 可选维度（本体属性 code 列表，供 IR/前端展示） |

**指标分两类**（这是融合的关键）：

- **模板型**（有 `sql_template`，复杂口径如比率/多表）→ 仍走**指标快路径**（确定性 SQL，零 LLM）。
- **绑定型**（`object_code + property_code + agg_fn`）→ 口径可由「对象属性 + 聚合」**确定性推导**，既可走指标快路径（自动生成 SQL），也可走**对象查询路径**（`instance_aggregate`），且**支持任意数据源**。

> `sql_template` 仍是**执行口径的唯一权威**；`object_code/property_code` 是**语义锚定**，用于：① 注入 IR prompt（让 LLM 知道有现成指标）；② 绑定型指标的对象查询执行；③ 前端展示与口径一致性校验。

### 2.3 评测数据集（验收载体）

- 给 `ai_query_testcase` 新增列 **`dataset VARCHAR(64) DEFAULT ''`**（`eval_set.py:14 _TESTCASE_DDL` + `_CASE_FIELDS`）。
- 评测运行 filter 支持 `dataset`（`eval_runner.start_run` 的 filter 透传 `list_cases(dataset=...)`）。
- 前端评测模块加**数据集下拉/筛选 + 新建**。
- 新建数据集：**「燃煤业务语义执行层评测集」**（`dataset='coal_semantic_v1'`，`datasource='ds:4'`）。

---

## 3. 大模型自动建模管线

### 3.1 阶段（一次性脚本 + 可复用管线共用）

```
扫描数据源 schema + 数据
 → ① 筛表：LLM 识别业务实体表，排除配置表/日志表/垃圾表
 → ② 筛字段 + 标注：主键、业务名、枚举值、可聚合性、敏感列、审计列
 → ③ 建关系：识别 FK / 业务关联（入厂批次↔化验↔合同↔矿点）
 → ④ 生成指标：基于对象属性 + 聚合 → 绑定型指标（可推导口径）+ 模板型指标（含 SQL）
 → ⑤ 幂等落库（ai_ont_object/property/link + ai_query_metrics）
 → ⑥ 人工在「数据与集成」审核/修正/启用
```

### 3.2 复用现有 LLM 管线（不重复造）

- **LLM 调用骨架复用** `eval_generate.py`：`build_prompt`(17) / `parse_cases`(89，容错解析) / `verify_and_save`(271，**执行金标校验**) / `generate_round`(319) / `call_llm`(360)。
  → 把「生成评测用例」改为「生成建模提案（对象/属性/关系/指标）」。
- **规则化建模复用**：`_import_ont_table_core`（`query/service.py:4631`）、`import_ds_tables_as_ontology`(4754)、`enrich_ontology_semantics`（`ontology/service.py:606`，读 `pg_catalog` 注释 + 真实外键）。
- **LLM 一律走 agno**（`_get_runtime()` + `build_headers` + `Agent`），**不**新增 `AsyncOpenAI` 直连（现有 `suggest_metrics_terms`/`eval_generate` 的直连属于历史遗留，新增管线不复用其调用方式，只复用其解析/校验纯函数）。

### 3.3 人在环（工作副本 / 提案）

- 本体已有**工作副本 + 提案/分支**基础设施（`ai_ont_wip`、`proposal.py`、`ai_ont_proposal`、`ai_ont_branch`）——**LLM 产物先入草稿 → 人工审核 → upsert**，避免自动建模直接污染正式语义。
- 新增 `POST /ai/ontology/auto-model`（触发管线，产出提案）+ `POST /ai/ontology/auto-model/apply`（审核后应用）。

---

## 4. 执行层改造

### 4.1 本体实例层支持自定义数据源（F1 的执行面）

- 新增「对象 → 连接」解析：`_instance_meta` 读 `datasource_id`，`_table_columns` / 实例查询（`instance_search/aggregate/pivot`）按 `datasource_id` 选择引擎：
  - `datasource_id` 为空 → 现有系统主库 `async_db_session()`；
  - 非空 → 复用 `query/executor.py` 的 `build_engine(_ds_cfg_from_model(ds))` 连对应数据源，并做**表/列名大小写引号处理**（复用 `sql_quote.quote_schema_identifiers`，燃煤库大小写敏感）。
- **保持零新增存储**：仍复用本体实例层，不自己拼 SQL 绕过行/列策略（沿用 `object_exec.py` 头注纪律）。

### 4.2 指标进对象查询执行层（F2 的执行面）

- **IR 扩展**：`ObjectQueryIR`（`object_query.py:40`）新增可选 `metric`（指标 key）。当 IR 是「metric + group_by + filters」时，执行：
  - 若指标为**绑定型** → 走 `object_exec` 的 `instance_aggregate`（本体实例层，支持任意数据源）；
  - 若为**模板型** → 走指标模板渲染（确定性 SQL）。
- **prompt 注入**：`render_ir_prompt`（:301）**新增注入命中/可用的指标**（key/name/绑定对象/维度），让 LLM 在 IR 里可直接**引用指标**而非重造聚合。
- **`_object_query_path` 支持自定义数据源**：`query/service.py:6496` 目前对自定义数据源直接返回 `None`（降级），改为**允许**（依赖 §4.1）。

### 4.3 流式接指标快路径

- `ask_stream`（`service.py:6939`）目前**不调用** `_match_metric`，改为：流式也走「指标 → 对象 → NL2SQL」三级降级。

---

## 5. 三处产品化

### 5.1 本体（`frontend/src/views/module_ai/ontology/`）

- `OntObjectTypeView.vue` 的 `TABS`（:721）**新增「指标」页签**：展示/管理绑定到该对象的指标（绑定型+模板型）。
- 新增「对象 ↔ 指标绑定」编辑：选择对象属性 + 聚合 + 维度。
- 复用 `OntMaintenanceDrawer`（`MAINT_PANELS`）承接「自动建模提案」审核入口。

### 5.2 数据与集成（`frontend/src/views/module_ai/integration/index.vue`）

- 现有 7 个标签页保留；**新增「语义建模」标签页**：
  - **一键大模型建模**（选数据源 → 触发 §3 管线 → 展示提案）。
  - **筛选表**（复用 `is_system` 过滤 + `filter_rules`）、**筛选字段**（复用 `is_audit`/`enum`/`sensitive`）、**标注数据**（复用字段编辑弹窗）。
  - **建关系**（复用 `infer_asset_relations` + 人工确认）。
  - **审指标**（复用指标 CRUD，新增「绑定对象/属性」控件）。
- 现有「指标」标签页（:372）**补对象/属性绑定列与编辑控件**。

### 5.3 智能问数（`frontend/src/views/module_ai/query/index.vue`）

- 已有 `pathLabel`（fast→指标/object→对象查询/slow→NL2SQL）与 IR 展示；**补渲染 `metric` 名称**（后端 `_answer` 已返回）。
- 执行三级降级（§4.2/4.3）后自然生效。

---

## 6. 评测与验收

### 6.1 评测数据集

- 新建 **「燃煤业务语义执行层评测集」**（`dataset='coal_semantic_v1'`，`datasource='ds:4'`）。
- 题目来源：基于燃煤库真实数据（用 §3 建模产出的对象/指标）自动生成 + 人工校对（复用 `eval_generate` 的生成+校验管线）。
- 题型覆盖：指标型（走①）、对象遍历/聚合型（走②）、自由 SQL 型（走③）。

### 6.2 验收标准

在该数据集上跑评测，**同时对比**三级降级开/关：

| 指标 | 期望 |
|---|---|
| `metric_accuracy`（指标型题） | 显著高于现状（确定性口径生效） |
| `data_accuracy`（总体） | 高于「全走 NL2SQL」的现状基线 |
| `object_rate` 且对象题正确率 | 对象路径正确率 ≥ slow 路径（不再拖后腿） |
| `avg_ms`/`p95_ms` | 指标/对象路径的延迟可接受（指标路径应≈0 LLM） |

> 参考：2026-10-14 系统库 A/B 显示对象查询开启后反而 -0.15（因 F1/F2 缺口）。本方案的目标就是**让对象/指标路径真正优于 NL2SQL**。

---

## 7. 复用 vs 新建

### 可直接复用
- 本体 upsert：`upsert_object/property/link/domain`（`ontology/service.py`）。
- 规则建模：`_import_ont_table_core`、`import_ds_tables_as_ontology`、`enrich_ontology_semantics`。
- LLM 管线骨架：`eval_generate.py`（`build_prompt`/`parse_cases`/`verify_and_save`/`generate_round`）。
- 标注引擎：`filtering.py` + `is_system/is_audit/enum/sensitive`。
- 执行骨架：`ask()` 的 fast→object→slow、`object_query.py`、`object_exec.execute_ir`、`executor.build_engine`、`sql_quote`。
- 人在环：`ai_ont_wip` + `proposal.py` + `ai_ont_proposal/branch`。
- 语义出口：`semantic.py` 的 `semantic_context/context_block/concepts`。

### 需新建
1. **LLM 自动建模编排**（§3）：本体侧无 LLM 生成入口。
2. **指标↔本体绑定**（§2.2）：`ai_query_metrics` 新列 + 绑定型指标推导。
3. **指标注入 IR prompt + IR metric 节点**（§4.2）。
4. **本体实例层按 `datasource_id` 连接**（§4.1）。
5. **`_object_query_path` 支持自定义数据源**（§4.2）。
6. **`ask_stream` 接指标快路径**（§4.3）。
7. **三处前端 UI**（§5）。
8. **评测 `dataset` 字段 + 燃煤评测集**（§2.3/§6）。

---

## 8. 分阶段实施与风险

### 8.1 阶段（每阶段可独立验证）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **S1** | 数据模型（§2.1/2.2/2.3）+ 本体实例层支持自定义数据源（§4.1） | 能用本体对象查询燃煤库表 |
| **S2** | 指标↔本体绑定 + 指标进对象查询 + 流式（§4.2/4.3） | 对象/指标路径在燃煤库跑通 |
| **S3** | 大模型自动建模管线（§3）+ 数据与集成建模面板（§5.2） | 一键对燃煤库建模产出提案 |
| **S4** | 本体指标页签 + 问数展示（§5.1/5.3）+ 燃煤评测集（§6） | 评测数据集跑通并给出对比 |

### 8.2 风险

| 风险 | 缓解 |
|---|---|
| 燃煤库大小写敏感、字段中文注释不规范 | 复用 `quote_schema_identifiers` + `enrich` 规则；口径对数据验证 |
| 331 表全量建模量大、LLM 成本高 | 分批（按业务域）；先聚焦核心域（采购结算/合同/化验/入厂/入炉/煤种/矿点/车辆） |
| 自动建模产出错误语义污染 | 走工作副本/提案，人工审核后 apply |
| 实例层跨库后权限/策略失效 | 复用本体行/列策略；跨库查询沿用 `_assert_ds_access` |
| 指标绑定型 vs 模板型口径不一致 | 绑定型由「属性+聚合」推导并**对数据验证**；模板型人工确认 |

---

## 9. 与三家的对照（本方案如何结合其优势）

| 维度 | Palantir | SuperSonic | WrenAI | 本方案 |
|---|---|---|---|---|
| 语义中枢 | Ontology | 指标平台 | Semantic Model | **本体（对象/关系）+ 指标（口径）双层，结构化绑定** |
| 语义→执行 | 对象图受控操作 | 指标+维度→确定性 SQL | MDL→LogicalPlan | **指标（确定性）→对象 IR→NL2SQL 三级降级** |
| LLM 自由度 | 极低 | 低（择义） | 低 | **低（只择义，不编口径）** |
| 建模 | 人工+平台 | 指标平台 | 人工语义模型 | **大模型自动 + 人工审核（提案制）** |
| 反幻觉 | 架构性 | 语义注入 | dry-run | **架构性（受控词汇 + 确定性执行）** |
| 治理 | 强 | 中 | 中 | **复用本体行/列级策略** |
| 可解释 | 强 | 中 | 中 | **IR trace + path/metric 展示** |
