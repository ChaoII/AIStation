# 「数据与集成 + 治理」链路修复与数据源过滤 实施计划

> 对应 spec：`docs/superpowers/specs/2026-10-30-integration-governance-fix-design.md`
> 日期：2026-10-30
> 执行方式：Native（当前 main，直接逐任务实现并提交）

## 前置约定

- 数据源字符串键格式：`"ds:4"`（燃煤）/ `"system"`（平台系统），沿用 `SYSTEM_DS="system"`（service.py:59）。
- `ai_pipeline` / `ai_query_concept` 由**内联 DDL** 创建（非 model.py），只改内联 DDL + 幂等 `ALTER`，**不新增 model 字段**。
- 提交信息格式 `feat(ai): 中文描述` / `fix(ai): 中文描述`；改动一律精确 `git add`。
- 后端改完用 `uv run ruff check`；纯逻辑测试用 `PYTEST_NO_APP=1` 快速模式；涉及 DB 的用 `uv run main.py ...`。
- 演示/种子脚本产出结果写入 `backend/env` 关联的 dev 库（postgres 127.0.0.1:5432 aistation）。

---

## 第一组：数据源隔离（A1/A2/A3）

### 任务 1：给 `ai_pipeline` 加 `datasource` 列（幂等）
- **文件**：`backend/app/plugin/module_ai/query/service.py`
- **改动**：
  1. `_QUERY_TABLES_SQL`（L84-88）`ai_pipeline` 建表 DDL 加列 `datasource VARCHAR(120)`。
  2. 在该模块的表就绪/ensure 逻辑处（建表后）对已存在表执行幂等 `ALTER TABLE ai_pipeline ADD COLUMN IF NOT EXISTS datasource VARCHAR(120)`。
- **验证**：`uv run ruff check app/plugin/module_ai/query/service.py`；启动后端后确认 `ai_pipeline` 有 `datasource` 列。

### 任务 2：给 `ai_query_concept` 加 `datasource` 列（幂等）
- **文件**：`backend/app/plugin/module_ai/query/service.py`
- **改动**：
  1. `_ensure_concept_table()`（L2692-2702）DDL 加列 `datasource VARCHAR(120)`。
  2. 同函数建表后对已存在表 `ALTER TABLE ai_query_concept ADD COLUMN IF NOT EXISTS datasource VARCHAR(120)`。
- **验证**：`ruff` 通过；`_ensure_concept_table()` 在已有表上可重入执行成功。

### 任务 3：存量管道/概念归入 `datasource="system"`
- **文件**：`backend/app/plugin/module_ai/query/service.py`（或新建幂等迁移脚本）
- **改动**：对现有平台行（`video_cameras→orders` 等管道、在线率/设备健康度等概念）将 `datasource` 置为 `"system"`。用一条幂等 SQL：`UPDATE ai_pipeline SET datasource='system' WHERE datasource IS NULL OR datasource=''`；`ai_query_concept` 同。
- **验证**：查库确认这些行 `datasource='system'`，且燃煤相关行未被误改。

### 任务 4：后端 `list_pipelines` / `list_concepts` 支持按 datasource 过滤
- **文件**：`backend/app/plugin/module_ai/query/service.py`、`backend/app/plugin/module_ai/query/controller.py`
- **改动**：
  - `list_pipelines(datasource: str | None = None)`（L4140）：SQL 加 `AND (:ds IS NULL OR p.datasource=:ds)`。
  - `list_concepts(datasource: str | None = None)`（L2705）：同法过滤 `concept.datasource`（注意 `ai_query_concept` 与 `ai_pipeline` 均非 model，SQL 手写）。
  - `controller.py`：`/pipeline/list`（L707-711）、`/concepts/list`（L1353-1357）接收可选 query 参数 `datasource: str | None = None` 透传。
- **验证**：`ruff` 通过；对 `pipeline/list?datasource=ds:4` 只返回燃煤管道，`?datasource=system` 只返回平台管道。

### 任务 5：前端 API 传 datasource + `loadMisc` 传参
- **文件**：`frontend/src/api/module_ai/query.ts`、`frontend/src/views/module_ai/integration/index.vue`
- **改动**：
  - `getPipelineList/getQueryTerms/getQueryConcepts` 函数签名加 `datasource` 参数并入 query。
  - `loadMisc()`（index.vue:2721-2724）：`getPipelineList({ datasource: curDs })`、`getQueryTerms({ datasource: curDs })`、`getQueryConcepts({ datasource: curDs })`，其中 `curDs` 为当前选中数据源字符串键（与 assets 列表一致）。
- **验证**：`pnpm run type-check`；浏览器选中燃煤 ds4 时管道/术语/概念只显示燃煤数据。

---

## 第二组：修复展示 / 渲染（B1/C1/C3/C2）

### 任务 6：绑定型指标返回「绑定对象/属性/聚合」口径（B1）
- **文件**：`backend/app/plugin/module_ai/query/service.py`
- **改动**：`_to_metric_dict()`（L489）对 `agg_fn` 非空的绑定型指标，把返回的 `sql_template` 覆写为展示文案（如 `绑定对象:{object_code} 属性:{property_code} 聚合:{agg_fn}`），不再返回占位 `SELECT 1 AS 数值`。
- **验证**：`ruff` 通过；`/metrics/list` 中绑定型指标 `sql_template` 展示为口径文案。

### 任务 7：数据关系图统计键对齐 + 补坐标布局（C1）
- **文件**：`backend/app/plugin/module_ai/query/service.py`、`backend/app/plugin/module_ai/query/agno_kg.py`
- **改动**：
  - `kg_stats()`（L3833）：返回键与前端对齐为 `nodes/edges/entities`（或返回 `data_nodes/data_edges/entities` 供前端读取——以 spec§3.2 的「键对齐」为准，前端 index.vue:814-823 读取端同步）。
  - `unified_graph()`（agno_kg.py:178）：对节点在无保存布局/无坐标时补默认坐标（GridCanvas 网格铺开），确保 GraphCanvas 能渲染出节点与边而非空画布。
- **验证**：`ruff` 通过；浏览器数据关系图能正常渲染节点/边，统计数字一致。

### 任务 8：表格撑满 tab 高度（C3）
- **文件**：`frontend/src/views/module_ai/integration/index.vue`
- **改动**：给管道/指标/术语/概念/示例 `el-table` 统一套 `.ig-tables` flex 容器（`display:flex; flex:1 1 auto; min-height:0; flex-direction:column`，与表格 tab index.vue:2886-2891 一致）。
- **验证**：`pnpm run type-check`；浏览器确认这些 tab 表格撑满、无大片留白。

### 任务 9：筛选规则 `el-empty` 加 `v-else`（C2）
- **文件**：`frontend/src/views/module_ai/integration/index.vue`
- **改动**：L864-867 筛选规则区 `<el-empty>` 加 `v-else`，与 `v-if="curDs"` 互斥；已选数据源时显示工作台、未选时显示空态。
- **验证**：`pnpm run type-check`；浏览器选中燃煤 ds4 后筛选规则工作台正常显示，不再出现「请先选择左侧数据源」。

---

## 第三组：数据清理与口径（B2/B3/D1）

### 任务 10：种子 alias/description 分开生成（B2）
- **文件**：`backend/scripts/seed_power_plant_ontology.py`、`backend/scripts/power_plant.py`
- **改动**：`asset_payload()` 与主种子：alias 用简短中文名（表名语义），description 用完整业务描述；对无注释表 alias 回退到表名/描述，避免「-」与「alias=description 重复」。
- **验证**：重跑种子后，`assets` 表 alias 不再空、不再与 description 完全重复。

### 任务 11：重刷 ds4 资产元数据 + 前端空 alias 回退（B2）
- **文件**：`frontend/src/views/module_ai/integration/index.vue`
- **改动**：L164 表中文名空值回退 `row.alias || row.description || row.table`。
- **数据操作**：对 ds4 相关 `ai_query_assets` 行重刷 alias/description。
- **验证**：浏览器燃煤表与字段 tab 无「-」、无重复中文名。

### 任务 12：删 fewshot 脏数据 + `_verify_feedback.py` 兜底（B3）
- **文件**：`backend/scripts/_verify_feedback.py`
- **改动**：加 `try/finally` 保证脚本退出时清理自造验证问题。
- **数据操作**：删除 `ai_query_fewshot` 中 `question='反馈链路验证题__请忽略'` 的行。
- **验证**：浏览器示例工程 tab 无该脏行。

### 任务 13：治理 DQ 统一「只统计已扫描」口径（D1）
- **文件**：`backend/app/plugin/module_ai/query/service.py`
- **改动**：
  - `dq_overview()`（L4945）/`dq_alert()`（L4985）统一口径：预警只统计**已扫描且 score<60** 的对象；未扫描对象单独标注「未扫描」，不计入预警数。
  - 治理对象范围保持 `object_enabled=true`（全局监管），仅收紧预警口径，避免 `mes_equipment/orders` 等未扫描对象按 0 分预警。
- **验证**：`ruff` 通过；治理驾驶舱「预警」数与「健康/预警/共」一致，未扫描对象不再按 0 分预警。

---

## 验收清单（对应 spec §6）

1. 选中燃煤 ds4 时，管道/术语/业务概念只显示燃煤相关行（A1/A2/A3）。
2. 指标 tab 绑定型指标显示「绑定对象/属性/聚合」口径，无 `SELECT 1`（B1）。
3. 数据关系图统计一致、图正常渲染（C1）。
4. 筛选规则已选数据源时正常显示工作台（C2）。
5. 管道/指标/术语/概念/示例表格撑满、无明显留白（C3）。
6. 表中文名无「-」无重复（B2）；示例工程无测试脏数据（B3）。
7. 治理驾驶舱「预警」与「健康/预警/共」一致，未扫描对象不再按 0 分预警（D1）。
8. 前端 `pnpm run type-check`、后端 `uv run ruff check` 通过。
9. 用无头浏览器在 5183（连 8002）登录 admin/123456，逐项截图对比（参照框架同构），供用户确认。

## 提交计划（按任务粒度）

每个任务完成并验证后单独提交（`git add` 精确文件）：
1. `feat(ai): 管道与业务概念表增加数据源归属列`
2. `feat(ai): 管道与概念列表按数据源过滤`
3. `feat(ai): 前端数据与集成加载按数据源过滤`
4. `fix(ai): 绑定型指标展示真实口径`
5. `fix(ai): 数据关系图统计键对齐与坐标布局`
6. `fix(ai): 数据集成列表表格撑满与筛选规则联动`
7. `fix(ai): 种子资产中文名与描述分离》
8. `fix(ai): 清理示例工程测试脏数据`
9. `fix(ai): 治理数据质量预警口径统一`
