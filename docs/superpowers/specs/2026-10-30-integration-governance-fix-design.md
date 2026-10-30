# 「数据与集成 + 治理」链路修复与数据源过滤 设计文档

> 所属：AI 集成开放平台 / 数据与集成 + 治理
> 日期：2026-10-30
> 状态：设计稿（待审）

## 1. 背景与问题

在「燃煤业务库」数据源（`ai_query_datasources.id=4`，code=`ezdcs_pg`，331 表）上跑了全量种子
（`seed_power_plant_ontology.py --ds=4 --no-llm`：表资产 186 / 字段 4603 / 本体对象 186 / 属性 4603 /
关系边 189 / 召回语义单元 391）后，逐 tab 走查发现 8 个问题（代号沿用盘点清单）：

| 代号 | 问题 |
|------|------|
| A1 | 管道 tab 展示平台自带管道（video_cameras→orders 等），与燃煤无关 |
| A2 | 术语 tab 全是平台系统术语（告警/摄像头/用户数），与燃煤无关 |
| A3 | 业务概念 tab 多为平台系统概念（在线率/设备健康度），涉及平台表 |
| B1 | 绑定型指标 SQL 模板显示占位 `SELECT 1 AS 数值`，未展示真实口径 |
| B2 | 部分表中文名 `-`（无注释），个别表中文名=业务描述（重复） |
| B3 | 示例工程第一条"反馈链路验证题__请忽略"为测试脏数据 |
| C1 | 数据关系图统计"表节点-/关系边-"与"当前 844 节点"矛盾，且图画布空白 |
| C2 | 筛选规则已选数据源却显示"请先选择左侧数据源" |
| C3 | 管道/指标/术语等列表下方大片留白、表格未撑满 |
| D1 | 治理驾驶舱"预警 188"与"健康/预警/共 6/1/205"不一致，且混入平台对象 |

## 2. 根因汇总（前后端已定位）

- **数据源过滤缺失**：`ai_pipeline`（service.py `_QUERY_TABLES_SQL` 内联 DDL）、`ai_query_concept`
  （`_ensure_concept_table()` 内联 DDL）**均无 `datasource` 列**；`list_pipelines()`(4140)、
  `list_concepts()`(2705) 无 datasource 过滤；前端 `loadMisc()`(index.vue:2721-2724) 调
  `getPipelineList/getQueryTerms/getQueryConcepts` **不传 datasource**。术语接口 `list_terms(datasource)`(1798)
  已支持过滤，只差前端传参。
- **绑定型指标**：`_to_metric_dict()`(489) 原样返回 `sql_template`（占位 `SELECT 1 AS 数值`，
  由 `_seed_coal_demo.py:85`/`modeling.py:279` 写入），前端指标表格(573)直接展示。
- **数据关系图**：`kg_stats()`(3833) 返回键 `data_nodes/data_edges/entities`，前端(index.vue:814-823)读
  `kg.nodes/kg.edges` → "-"；`unified_graph()`（agno_kg.py:178）为**平台全局图**（844 节点，无数据源过滤），
  节点无 `x/y` 坐标（无保存布局），前端 GraphCanvas 渲染不出。
- **筛选规则**：index.vue:864-867 `<el-empty>` **缺 `v-else`**，与 `v-if="curDs"` 未互斥。
- **表中文名**：`power_plant.asset_payload()`(133-151) 用 `alias=comment`、`description=comment`，
  `seed_power_plant_ontology.py:105-123` 对无注释表用同一 LLM 中文名同时填 alias 与 description →
  重复；LLM 漏掉的表 alias 空 → 前端(index.vue:164)显示 "-"。
- **治理 DQ**：`dq_overview()`(4945) 以 `object_enabled` 全局取对象、只统计**已扫描**；`dq_alert()`(4985)
  把**未扫描对象按 score=0 <60** 也计入预警 → `dq_alerts=188` 与 `dq.risk=1`(来自 dq_overview.risk)
  口径不一致，且 `mes_equipment/orders` 等平台对象混入。
- **fewshot 脏数据**：`_verify_feedback.py:18` 造的验证问题经 `feedback()` 自动沉淀(service.py:9224-9234)
  写入 `ai_query_fewshot`，脚本尾部清理(64)未生效/中断残留。

## 3. 方案设计

### 3.1 第一组：数据源隔离（A1/A2/A3）

**目标**：选中某数据源时，管道/术语/业务概念只显示该数据源的行；平台系统数据归入
`datasource="system"`（`SYSTEM_DS="system"`，service.py:59）。

- **后端加列（幂等）**：
  - `ai_pipeline`：在内联 DDL（service.py `_QUERY_TABLES_SQL`，约 L84-88）加 `datasource varchar`；
    并在建表/ensure 逻辑对已存在表执行 `ALTER TABLE ai_pipeline ADD COLUMN IF NOT EXISTS datasource varchar`。
  - `ai_query_concept`：在 `_ensure_concept_table()`(2692) DDL 加 `datasource varchar`；
    同样对已存在表 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS datasource varchar`。
  - 这两张表非 model.py 模型，**改表结构只改内联 DDL，不新增 model 字段**（避免与模型层冲突）。
- **后端接口过滤**：
  - `list_pipelines(datasource: str | None = None)`：`WHERE p.is_deleted=false AND (:ds IS NULL OR p.datasource=:ds)`。
  - `list_concepts(datasource: str | None = None)`：同法过滤 `concept.datasource`。
  - `list_terms` 已支持（1803-1804），无需改。
- **前端传参**：`integration/index.vue` 的 `loadMisc()`（2721-2724）对
  `getPipelineList({ datasource })`、`getQueryTerms({ datasource })`、`getQueryConcepts({ datasource })`
  传当前数据源字符串键（与 assets 列表一致，如 `"ds:4"` / `"system"`）；`query.ts` 对应函数签名加 `datasource`。
- **存量数据归属**：把现有平台管道（video_cameras→orders 等 4 条）、平台概念（在线率/设备健康度等）
  在 `ai_pipeline`/`ai_query_concept` 中 `datasource` 置为 `"system"`。

### 3.2 第二组：修复展示 / 渲染（B1/C1/C3/C2）

- **B1 绑定型指标口径**：`_to_metric_dict()`(489) 对 `agg_fn` 非空的绑定型指标，`sql_template` 字段
  改为返回展示文案（如 `绑定对象:{object_code} 属性:{property_code} 聚合:{agg_fn}`）而非占位 SQL；
  `modeling.py:279` 与 `_seed_coal_demo.py:85` 不再写死 `SELECT 1 AS 数值`。
  前端指标表格正常运行，无需大改。
- **C1 数据关系图**：
  - `kg_stats()`(3833) 改为返回键 `nodes/edges/entities`（或前端读 `data_nodes/data_edges/entities` 对齐）。
  - `unified_graph()`（agno_kg.py:178）对节点**补坐标/布局**（无保存布局时由 GraphCanvas 网格铺开，而非空画布）；
    并为下图明确「全局血缘」或按数据源过滤，避免与选中数据源语义错位。
  - 前端 `loadUnified()`/统计栏键名对齐。
- **C3 表格满高**：给管道/指标/术语/概念/示例 tab 的 `el-table` 统一套 `.ig-tables` flex 容器
  （`display:flex; flex:1 1 auto; min-height:0; flex-direction:column`，与 `table` tab 一致，index.vue:2886-2891），
  让表格撑满 tab 高度，消除下方留白。
- **C2 筛选规则**：index.vue:866 `<el-empty>` 加 `v-else`，`v-if="curDs"` 显示工作台、否则空态，二者互斥。

### 3.3 第三组：数据清理与口径（B2/B3/D1）

- **B2 表中文名**：
  - `seed_power_plant_ontology.py`（约 99-129）与 `power_plant.asset_payload()`：把 alias 与 description
    **分开生成**——alias 用简短中文名（表名语义），description 用完整业务描述；对无注释表 alias 回退到表名/描述。
  - 重刷 ds4 资产元数据（`assets` 表 alias/description），消除 "-" 与重复。
  - 前端 index.vue:164 对空 alias 回退：`row.alias || row.description || row.table_name`。
- **B3 two-shot 脏数据**：删除 `ai_query_fewshot` 中 `question='反馈链路验证题__请忽略'` 的行；
  `_verify_feedback.py` 加 `try/finally` 保证清理。
- **D1 治理 DQ 口径**：
  - `dq_alert()`(4985) 与 `dq_overview()`(4945) **统一口径**：预警只统计**已扫描且 score<60** 的对象；
    未扫描对象单独标注"未扫描"，不计入预警数（消除 188 vs 1 矛盾）。
  - 治理页为全局监管，对象范围保持 `object_enabled=true`（不按数据源收缩），但**未扫描对象不再按 0 分预警**，
    避免 mes_equipment/orders 等误导。
  - 前端 GovernancePanel.vue 对齐该口径（预警数 = 风险数）。

## 4. 改动文件清单

**前端**
- `frontend/src/api/module_ai/query.ts`：`getPipelineList/getQueryTerms/getQueryConcepts/getQueryKgUnified` 加 `datasource` 参数。
- `frontend/src/views/module_ai/integration/index.vue`：
  - `loadMisc()`(2721-2724) 传 `datasource`；`openPipe` 同理。
  - 筛选规则 `<el-empty v-else>`(866)。
  - 管道/指标/术语/概念/示例 `el-table` 套 `.ig-tables`（497/557/621/679/737）。
  - kg 统计键对齐（814-823）；表中文名空值回退（164）。
- `frontend/src/views/module_ai/integration/components/GovernancePanel.vue`：DQ 口径对齐（预警/风险展示）。

**后端**
- `backend/app/plugin/module_ai/query/service.py`：
  - `_QUERY_TABLES_SQL`(84-88) 与 `_ensure_concept_table()`(2692) 加 `datasource` 列 + 幂等 `ALTER`。
  - `list_pipelines(datasource)`(4140)、`list_concepts(datasource)`(2705) 加过滤。
  - `_to_metric_dict()`(489) 绑定型指标返回口径文案。
  - `kg_stats()`(3833) 键对齐 `nodes/edges/entities`。
  - `dq_overview()`(4945)/`dq_alert()`(4985) 统一口径，未扫描不计预警。
  - 存量管道/概念设 `datasource="system"`。
- `backend/app/plugin/module_ai/query/controller.py`：对应接口透传 `datasource` 参数。
- `backend/app/plugin/module_ai/query/agno_kg.py`：`unified_graph()`(178) 节点补坐标/布局，明确过滤语义。

**种子 / 脚本**
- `backend/scripts/seed_power_plant_ontology.py`、`backend/scripts/power_plant.py`：alias/description 分开生成。
- `backend/scripts/_verify_feedback.py`：try/finally 清理。

## 5. 数据操作（对 dev 库）

- `ALTER TABLE ai_pipeline ADD COLUMN IF NOT EXISTS datasource varchar`；`ai_query_concept` 同。
- 置 `ai_pipeline.datasource='system'`、`ai_query_concept.datasource='system'`（仅现有平台行）。
- 删 `ai_query_fewshot WHERE question='反馈链路验证题__请忽略'`。
- 重刷 ds4 资产元数据（alias/description）以消除 "-" 与重复。

## 6. 验收标准

1. 选中燃煤 ds4 时，管道/术语/业务概念只显示燃煤相关行，平台系统数据不再混入（A1/A2/A3）。
2. 指标 tab 绑定型指标显示"绑定对象/属性/聚合"口径，不再有 `SELECT 1 AS 数值`（B1）。
3. 数据关系图统计"节点/边/实体"一致，图能正常渲染出节点与边（C1）。
4. 筛选规则 tab 在已选数据源时正常显示工作台，不再出现"请先选择左侧数据源"空态（C2）。
5. 管道/指标/术语/概念/示例表格撑满 tab 高度，无明显留白（C3）。
6. 表中文名无 `-` 无重复（B2）；示例工程无测试脏数据（B3）。
7. 治理驾驶舱"预警"数与"健康/预警/共"一致，未扫描对象不再按 0 分预警（D1）。
8. 前端 `pnpm run type-check`、后端 `ruff` 通过；燃煤链路上回归用例通过。

## 7. 风险与注意

- `ai_pipeline`/`ai_query_concept` 由**内联 DDL** 创建（非 model.py），改结构只改 DDL + 幂等 ALTER，勿新增 model 字段。
- 数据源字符串键格式需与现有 `assets`/`terms` 列表一致（`"ds:4"`/`"system"`），前端统一复用。
- 治理页为**全局监管**，本次不改对象范围为单数据源（避免改变治理定位）；只统一 DQ 口径与未扫描呈现。
- 不新增第三方依赖；只改既有接口/展示/数据，不改治理接口语义、不引入新权限体系。

## 8. 非目标

- 不动独立的「本体」编辑器（对象/关系/动作/安全等 Ontology Manager）。
- 不新增数据源类型（file/api UI 支持不在本次范围）。
- 不改治理接口的全局监管定位，不引入新权限码。
