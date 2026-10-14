# 筛选规则工作台（可配置 / 预览 / 对比 / 概览 / 大模型辅助）— 设计

- 日期：2026-10-14
- 模块：数据与集成（`module_ai/integration`）+ 智能问数（`module_ai/query`）
- 状态：设计待评审

## 1. 背景与目标

上一期已为每个数据源提供 `filter_rules`（系统表/审计字段自动打标）。但用户在集成页的筛选规则只是数据源编辑弹窗里的一堆**表单字段**（前缀/关键词/精确表名/正则/审计字段），存在三大痛点：

1. **看不到规则的实际影响**：填了规则却不知道哪些表会被判成系统/业务、哪些字段会被判成审计，只能凭感觉，无法「确认效果再保存」。
2. **无法对比**：改规则前后对同一批表的分类差异看不到，怕改坏。
3. **配置仅靠手工**：面对 331 张表，手动想前缀/关键词很费劲，希望让大模型根据表名/字段名辅助生成、解释。

目标：把筛选规则从「一堆表单」升级为集成页内的**筛选规则工作台**，具备——

- **规则配置**：结构化、分区清晰（tab/分步）地维护规则；
- **实时分类预览**：改规则立即看到哪些表/字段被判为系统/业务/审计，并**说明命中哪条规则**；
- **调整前后对比**：已保存规则 vs 草稿规则的分类差异（哪些表/字段翻转）；
- **全局概览仪表盘**：系统 vs 业务表、审计 vs 业务字段的分布可视化；
- **大模型辅助**：自动生成/建议规则、逐表逐字段分类建议、解释命中原因、自然语言配置规则。

## 2. 现状（已具备 / 缺口）

### 已具备
- `query/filtering.py`：纯逻辑规则引擎 `DEFAULT_FILTER_RULES` / `is_system_table()` / `is_audit_field()`（前缀/关键词/精确表名/正则/审计字段集合，大小写不敏感）。
- `ai_query_datasources.filter_rules`（JSONB）：每数据源独立规则，`upsert_datasource` 支持传入、`datasource_detail` 返回。
- 数据源同步已按 `filter_rules` 给表打 `is_system`、给字段打 `is_audit`；`list_ds_schema` 返回 `is_system`、字段 `is_audit`。
- 前端 `frontend/src/views/module_ai/integration/index.vue`：数据源编辑弹窗已有「筛选规则」表单（前缀/关键词/精确表名/正则/审计字段）。
- 前端已装 `echarts` + `vue-echarts`（可用于概览图表）。
- query 模块已有 agno 大模型调用链路（`_get_runtime()` → `AiModelService.get_runtime_model()` + `OpenAILike` + `build_headers`）。
- 后端 `list_ds_schema(datasource_id)` 返回该数据源全部表及字段名（含注释），可供大模型样本与预览计算。

### 缺口
1. 规则引擎只返回「是/否」，**不返回命中原因**（哪条规则命中），无法支撑解释与预览可视化。
2. 无「对一套候选规则计算全量分类」的接口（现有同步只按**已保存**规则打标，无法预览草稿规则的效果）。
3. 前端无可视化的工作台（预览/对比/概览/大模型辅助）。
4. 无任何大模型辅助接口（建议规则 / 自然语言配置 / 逐表逐字段建议）。

## 3. 设计

### 3.1 规则引擎强化（`query/filtering.py`）

保持纯逻辑、不碰数据库。新增：

- `classify_tables(tables: list[str], rules: dict) -> list[dict]`：对每个表名返回 `{"name", "is_system", "reason"}`。
  - `reason`：命中的具体规则描述，如 `前缀 SYS_` / `关键词 _BAK` / `精确表名 alembic_version` / `正则 ^TMP_`；未命中则 `reason=""`、`is_system=False`。
  - 规则 `enabled=False` 时全部 `is_system=False`。
- `classify_fields(fields: list[str], rules: dict) -> list[dict]`：对每个字段名返回 `{"name", "is_audit", "reason"}`（命中审计字段集合时 `reason=审计字段 xxx`）。
- 保留既有 `is_system_table` / `is_audit_field`（内部改为复用 classify 逻辑，避免重复）。

`DEFAULT_FILTER_RULES` 结构不变（向后兼容）。

### 3.2 后端新增接口

路由统一挂在 `app/plugin/module_ai/query/`（容器前缀 `/ai/query`，自动发现）。

**A. 分类预览（确定性，无 LLM）**

- `POST /api/v1/ai/query/datasources/{id}/rules/preview`
  - 入参：`{ "rules": {...} }`（**草稿**规则，可未保存）；`rules` 缺省用该源当前已保存规则。
  - 出参：
    ```json
    {
      "tables": [{"name","is_system","reason"}...],
      "fields": [{"name","is_audit","reason"}...],
      "summary": {"table_total","system_tables","business_tables","field_total","audit_fields","business_fields"}
    }
    ```
  - 实现：取该源已同步表/字段名（`list_ds_schema` 的回读，或直接读 `ai_query_schema`），用 `classify_tables/classify_fields` 计算。
  - 供「实时预览」「前后对比」「概览」三处复用；规则单一来源在后端。

**B. 大模型辅助（走 agno，复用 `_get_runtime` + `build_headers`）**

- `POST .../rules/suggest`：入参可带当前草稿规则；后端读取该源表名/字段名样本（上限如 400 表名、400 字段名），提示大模型生成一套候选 `filter_rules`（输出 JSON，含 `system_table` 与 `audit_fields`）。返回建议规则 + 简要说明。
- `POST .../rules/parse`：入参 `{ "text": "自然语言描述" }`；大模型把自然语言转成结构化 `filter_rules`（JSON）。返回解析结果 + 可应用标记。
- `POST .../rules/classify-advise`：入参 `{ "rules": {...} }` 或默认规则；大模型对表名/字段名样本给出「建议判定 + 理由」，返回分组建议（建议归系统/业务的表、建议归审计/业务的字段）。
- 「解释命中原因」默认走**规则引擎的 `reason`**（确定性、零成本）；如需自然语言叙述，可由 `classify-advise` 附带（不单开接口）。
- 所有大模型接口在 agno **之外**用 `asyncio.wait_for` 兜底超时（对齐 `_nl2sql` 的 `nl2sql_call_timeout` 实践），超时返回可读错误，不阻塞。

### 3.3 前端：筛选规则工作台

新增组件 `frontend/src/views/module_ai/integration/components/FilterRulesWorkbench.vue`（集成页文件已 ~1800 行，独立组件利于维护），在集成页「表与字段」等既有 tab 旁新增一个**「筛选规则」tab**，选中某数据源后展示工作台。

组件内用 `el-tabs` 分区（Element Plus 原生组件）：

1. **规则配置**
   - 结构化表单：启用开关、系统表前缀/关键词/精确表名（`el-select multiple allow-create`）、表名正则（`el-input`）、审计字段（`el-select multiple allow-create`）。
   - 底部「保存草稿」（写入源 `filter_rules`），并有「保存并应用」。
   - 顶部展示当前规则命中摘要（多少表/字段会被判系统/审计）。

2. **实时预览**
   - 拉取 `preview` 接口（传**当前草稿**规则）。
   - 表清单：表名 / 系统·业务（`el-tag`）/ **命中规则**（文本）。
   - 字段清单：字段名 / 审计·业务（`el-tag`）/ **命中规则**。
   - 规则一改即刷新（`@change` 触发，非节流轮询）。

3. **前后对比**
   - 取「已保存规则」的 `preview` 与「草稿规则」的 `preview` 求差集。
   - 展示**翻转清单**：`表X：业务→系统（命中 前缀 SYS_）`、`字段Y：业务→审计` 等，按类型分组（表翻转 / 字段翻转）。
   - 无差异时给出「当前草稿与已保存规则分类一致」。

4. **概览仪表盘**
   - 用 `vue-echarts` 绘制：系统 vs 业务表数量（环形/饼图）、审计 vs 业务字段数量（环形/饼图）。
   - 数据来自 `preview.summary`。

5. **大模型辅助**
   - 「生成候选规则」：调 `suggest`，结果在弹层/区展示，提供「一键应用到草稿」。
   - 「自然语言配置」：输入框 → `parse` → 预览解析出的 `filter_rules` → 「应用」。
   - 「逐表逐字段建议」：调 `classify-advise`，树/表展示建议与理由，可批量采纳。
   - 辅助为**建议**而非自动覆盖：所有结果先展示给用户，用户确认后才应用到草稿。

样式全部使用 Element Plus 组件与 `--el-*` 变量，对齐既有页面；完成后用无头浏览器截图 + 模型自读图核对。

### 3.4 版本/存储

- 规则仍存于 `ai_query_datasources.filter_rules`，无需新增表。
- 草稿规则为前端状态（`ref`），未保存前不影响源规则；「保存并应用」才写库并触发同步打标。
- 对比用的「已保存规则」从 `datasource_detail` 读取。

## 4. 分两期实施

- **首期（确定性，无 LLM）**：规则引擎 `classify_*` 强化 + `preview` 接口 + 前端工作台（规则配置 / 实时预览 / 前后对比 / 概览）。先把「看清效果再确定」落地。
- **二期（大模型辅助）**：`suggest` / `parse` / `classify-advise` 三接口 + 工作台「大模型辅助」分区。

## 5. 测试

- 后端：
  - `classify_tables`/`classify_fields` 单测：前缀/关键词/精确表名/正则命中、`reason` 正确、`enabled=False` 全放行、大小写不敏感。
  - `preview` 接口：对燃煤业务库返回正确汇总（系统/业务表数、审计/业务字段数），与已同步标一致。
  - 大模型接口：`suggest`/`parse` 输出可解析 JSON；超时兜底返回可读错误。
- 前端：`vue-tsc`、eslint。
- 端到端：燃煤业务库 → 工作台预览命中说明 → 去掉 `FUEL_` 前缀 → 对比翻转 → 概览图 → 保存应用 → 重新同步后 `is_system` 变化。

## 6. 验收标准

1. 集成页新增「筛选规则」tab，选中数据源后可配置规则并**实时看到**表/字段分类与**命中规则说明**。
2. 可对比「已保存规则 vs 草稿规则」的分类差异，明确列出翻转的表/字段。
3. 概览仪表盘以图表展示系统/业务表、审计/业务字段分布。
4. 大模型辅助可生成候选规则、自然语言配置、逐表逐字段建议，确认后能一键应用到草稿。
5. 全部使用 Element Plus 组件与 `--el-*` 变量，风格与既有页面一致。
6. 燃煤业务库全流程（预览→调整→对比→保存→同步打标）跑通。
