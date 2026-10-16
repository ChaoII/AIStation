# AI 工作台（Workbench）设计

> 日期：2026-10-16
> 范围：把「智能体中心」重构为统一「工作台」，统管 智能体/工作流/定时任务/应用，左侧树形分类 + 右侧卡片区 + 独立聊天界面（AI 渲染引擎）。前后端 + 数据库迁移。

## 目标

把分散的「智能体 / 工作流 / 定时任务 / 应用」收进一个**工作台入口**：
- 左侧**树形分类**（可创建/编辑/删除，多级）。
- 右侧**卡片区**（白底卡片 + 蓝灰间隔 + 类型徽标 + 名称 + 简述 + 启停 + 「对话」）。
- 点击卡片或「对话」→ **独立聊天界面**：左边按时间归集的会话列表 + 右边用 `useAiChat` + chat 组件（AI 渲染引擎）渲染流式/思考/工具/技能。

## 数据层

### 统一分类表 `ai_workspace_categories`
- `id`、`parent_id`（FK 自引用，ondelete=SET NULL）、`name`、`icon`、`color`、`sort`
- 继承 `ModelMixin + UserMixin`（含 created_id/status/…）。
- 树结构：`parent_id` 支持多级。

### 关联
- `ai_agents.category_id` → `ai_workspace_categories.id`
- `ai_workflows.category_id` → `ai_workspace_categories.id`
- `ai_apps.category_id` → `ai_workspace_categories.id`
- `ai_workspace_cron.category_id` → `ai_workspace_categories.id`（定时任务条目）

### 定时任务条目 `ai_workspace_cron`
新表：`name`、`description`、`workflow_id`（可选绑工作流）、`agent_id`（可选绑智能体）、`app_id`（可选）、`cron`（cron 表达式）、`enabled`、`category_id`、`last_run_time`、`next_run_time`。由 APScheduler（复用 `ai_workflow_schedules` 的调度机制或独立调度器）触发执行绑定的资产。

> 注：迁移**手写**（autogenerate 会把 400+ 影子表判成待 DROP，见 AGENTS.md）；空库全链重放需 `sa.inspect(bind).has_table()` 判断。

## 界面

### 工作台页 `/ai/workspace`
- **顶部工具条**（白底，不落蓝灰底）：左侧面包屑/标题「工作台」，右侧 搜索框 + 按类型筛选 + 「新建」下拉（智能体/工作流/定时任务/应用）。
- **左：分类树** `el-tree`（可展开/选中）；节点操作：新建子分类 / 重命名 / 删除；「全部」固定节点。
- **右：卡片区** `el-row/el-col` 网格，白底卡片（`--el-fill-color-blank` 细边框圆角 + hover 上浮），卡片显示：类型徽标（智能体/工作流/定时任务/应用）+ 图标 + 名称 + 两行简述 + 启停 + 「对话」。
- 空态与加载骨架。

### 聊天页 `/ai/workspace/chat/:kind/:id`
- **左：会话列表**按时间归集（今天 / 昨天 / 近 7 天 / 更早），头部：新增会话 / 删除当前 / 删除当天。
- **右：对话区**用 `useAiChat` + `ChatMessages/MessageItem/ReasoningBlock/ToolCallTimeline/RichContent/ChatInput`（专用 AI 渲染引擎），流式 / 思考 / 工具 / 技能，样式对齐工作台卡片。

### 风格
- 全部用 `el-row/el-col` + `el-card` + `--el-*` 变量；`font-size` 用 Element 默认；避免自写 CSS Grid/Flex。
- `.app-container` 为 flex column：工作台用 `el-row` 分栏（左树右卡片），顶部工具条白底独立容器；不整页 `el-card`（避免 flex-shrink 陷阱）。

## 菜单 / 权限
- `backend/app/scripts/init_app.py` `_ensure_ai_menus()` 的 `pages` 列表新增 `("工作台","AiWorkspace","/ai/workspace","module_ai/workspace/index","module_ai:workspace:query",10,"el-icon-OfficeBuilding")`。
- `AI_BUTTON_PERMS` 增加 `module_ai:workspace:{query,create,update,delete}`。
- 原 `/ai/agent`（智能体中心）页保留但可从菜单下线或作为子入口；工作台卡片点「对话」直接进聊天，不再用 agent 内嵌对话。

## 非目标（本阶段不做）
- 不重构工作流/定时任务的执行引擎（复用现有）。
- 不改「AI 智能助手」。
- 定时任务只负责「定时执行绑定资产」，不引入复杂编排。
