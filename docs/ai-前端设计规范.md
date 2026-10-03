# AIStation 前端 UI / 交互规范（产品经理级）

> 适用：`views/module_ai/*` 所有模块。目标是让每个模块都达到
> **知识库(knowledge) / 工作流(workflow)** 那种「丰富、可编辑、美观、可追溯」的产品级体验。
> 开发前必须对照本规范，完成 UI 后截图核对风格一致再交付。

---

## 一、视觉基准（与 Element Plus / 项目一致）

- **组件**：优先用 Element Plus 原生组件（`el-table/el-form/el-dialog/el-drawer/el-tabs/
  el-descriptions/el-statistic/el-tag/el-upload/el-empty`），不要自造主题外壳。
- **颜色/间距/圆角**：一律引用 `--el-*` 变量，禁止写死主题色（`#409eff` 等）。
- **字号**：正文 `var(--el-font-size-base)`(14px)，次要说明 12px；禁止 13/15/16 零散混用。
- **图标**：统一 Element Plus 图标（`el-icon` + 组件内 `icon` 字段）。
- **响应式**：栅格用 `el-row/el-col`（`:xs/:md/:lg`），避免自定义 Grid/Flex 主布局。
- **弹窗宽度**：常用档位（500/560/600/760px），`append-to-body`，放页面根元素内。

## 二、页面结构（标杆：详情抽屉 + 多 tab）

每个业务实体应具备：

1. **列表页**：工具栏（新建 / 搜索 / 筛选 / 批量 / 导出）、分页表格或卡片网格、空态、状态标签。
2. **详情/编辑器**：优先 `el-drawer` + `el-tabs`（概览 / 编辑 / 关联 / 统计 / 运行调试），
   而非简单弹窗；复杂实体用画布/编辑器组件。
3. **统计/可视化**：业务含趋势/分布的用 `ECharts`（拆到 `components/`）或 `el-statistic` 卡片。
4. **可编辑**：支持编辑、复制、启停、删除；配置类支持可视化构造（变量/字段/入参），
   不鼓励裸 JSON 文本框（必要 JSON 场景配 CodeMirror + 校验提示）。

## 三、交互必须项（强制）

- **删除/清空/覆盖类 → 二次确认**：`ElMessageBox.confirm`，文案写明影响范围与不可逆性，
  且带数量；确认/取消文案语义明确（「删除/取消」）。
- **局部刷新优先**：进度/状态变化只更新对应行/项，禁止周期性整体 `refreshList()`；
  仅在状态跃迁时刷新一次。
- **加载态**：请求中 `v-loading`，按钮 `:loading`，避免「点了没反应」。
- **空态**：列表/结果用 `el-empty` + 引导文案。
- **错误反馈**：`ElMessage` / `ElMessageBox`，主动提示并给出可操作建议。
- **表单校验**：必填、格式、JSON 合法性在提交前校验。
- **权限按钮**：操作按钮带 `v-hasPerm`（前端）+ 后端接口权限校验。

## 四、通用组件复用

- 搜索/表格可用 `components/CURD` 的 `PageSearch/PageContent/EnhancedDialog` 或 `useCrudList`。
- 编辑器：代码用 CodeMirror；规则/条件树/字段构造用成熟第三方库（禁手写）。
- CodeMirror 已用于 workflow；知识库/其他 JSON 场景可复用 `components/.../CodeEditor` 风格组件。
- 图表统一引入 `ECharts`（项目已用），封装成共享图表组件，避免每页重复。

## 五、各模块面向「批处理」的落地（分批）

按现状成熟度分批补齐：

- **第 1 批（最缺、收益高）**
  - `logs`：补调用详情（请求/响应/耗时）、导出 CSV、统计图表（调用量/成功率/耗时趋势/引擎分布）。
  - `app`：补**详情抽屉**（关联配置/入参字段构造器/运行调试）、复制、分页。
  - `provider`：**拉取远端模型 → 一键导入为模型配置**（闭环），补搜索/详情。
- **第 2 批（中等补齐）**
  - `model`：补详情抽屉、批量启停、能力/上下文可视化。
  - `tool`：补 Agno 工具调用测试、分组管理、参数 schema 结构化展示。
  - `skill`：补搜索栏、Markdown 渲染预览、复制、批量。
- **第 3 批（增强）**
  - `agent`：补详情/预览、复制、批量、调试面板。
  - `prompt`：补版本历史、AI 生成、模板库、富文本预览。
- **待建**：`overview`(控制台统计)、`report`(AI 报告)、`playground`(运行台)。

## 六、验收标准

- 视觉与既有模块（`module_system/param`、knowledge/workflow）一致，无割裂。
- 每个模块有：列表 + 详情/编辑 + 关键统计 + 二次确认 + 空态/加载态 + 局部刷新。
- 完成后无头浏览器截图，**用模型多模态读图**与标杆页面对照，确认一致再交付。
- 后端 ruff / 前端 type-check / lint 干净；e2e 关键路径可跑通。
