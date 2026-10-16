# AI 工作台（Workbench）分阶段实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把智能体中心重构为统一工作台：左侧树形分类 + 右侧多类型卡片区（智能体/工作流/定时任务/应用）+ 独立聊天页（时间归集会话 + AI 渲染引擎）。

**Architecture:** 后端新建统一分类表 `ai_workspace_categories` + 定时任务表 `ai_workspace_cron`，给 `ai_agents`/`ai_workflows`/`ai_apps` 加 `category_id`；手写迁移。前端新增 `/ai/workspace`（左树右卡片）与 `/ai/workspace/chat/:kind/:id`（复用 `useAiChat` + chat 组件）。

**Tech Stack:** FastAPI + SQLAlchemy（后端）、Vue3 + Element Plus（前端）、pytest（后端回归）、无头浏览器截图验收（前端）。

**Spec:** `docs/superpowers/specs/2026-10-16-ai-workbench-design.md`

## Global Constraints

- 迁移**手写**；对插件表增列用 `sa.inspect(bind).has_table()` 判断；空库全链重放可过。
- 前端只用 Element Plus + `--el-*`；布局用 `el-row/el-col`，不整页 `el-card`（避免 flex-shrink 陷阱）。
- 注释/提交信息中文；精确 `git add`（禁用 `-A`）。
- 每阶段结束用无头浏览器截图核对，风格不符即返工。

## Review Focus

- 分类树多级（`parent_id`）构建正确；删除父分类时子分类/条目处理（SET NULL）。
- 工作台卡片按类型显示不同徽标与「对话」入口；无分类条目出现在「全部」。
- 聊天页会话按时间归集正确（今天/昨天/近7天/更早），新增/删除/删除当天可用。
- 聊天用 `useAiChat` 渲染 parts（思考/工具/正文），流式光标；样式对齐工作台卡片。
- 迁移不破坏既有表；工作流/应用新列 `category_id` 不影响既有功能。

---

## Phase 1: 后端 —— 统一分类 + 关联 + 菜单（Spec 数据层）

**Files:**
- Create: `backend/app/plugin/module_ai/workspace/model.py`（`AiWorkspaceCategoryModel`、`AiWorkspaceCronModel`）
- Create: `backend/app/plugin/module_ai/workspace/controller.py` / `service.py` / `schema.py`
- Modify: `backend/app/plugin/module_ai/agent/model.py`、`workflow/model.py`、`apps/model.py`（加 `category_id`）
- Modify: `backend/scripts/...` 或迁移文件（手写迁移）
- Modify: `backend/app/scripts/init_app.py`（菜单 + 权限）

**Interfaces:**
- Produces: `AiWorkspaceCategoryModel`（name/parent_id/icon/color/sort + ModelMixin/UserMixin）；`/api/v1/ai/workspace/categories/*`（list 树 / create / update / delete）；`/api/v1/ai/workspace/items`（按分类聚合 agent/workflow/app/cron）。
- Consumes: `ai_agents`/`ai_workflows`/`ai_apps` 的 `category_id`。

- [ ] **Step 1: 建 workspace 模型 + 迁移**

`workspace/model.py` 定义两表；为 `ai_agents`/`ai_workflows`/`ai_apps` 加 `category_id`（`Integer ForeignKey ai_workspace_categories.id ON DELETE SET NULL`）。手写迁移：`sa.inspect(bind).has_table()` 判断再 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（PG）或建表（`CREATE TABLE IF NOT EXISTS`）。

- [ ] **Step 2: 分类 CRUD + 树构建**

`workspace/service.py`：`list_tree()` 用 `traversal_to_tree`（`app/utils/common_util.py`）构建树；`create/update/delete` 校验 parent 存在、删除用 `SET NULL`。`controller.py` 注册 `/api/v1/ai/workspace/categories/*`。

- [ ] **Step 3: 聚合查询 + 菜单权限**

`workspace/service.py` `items(category_id)`：按分类/全部聚合 agent/workflow/app/cron 成统一条目（`type`/`id`/`name`/`desc`/`enabled`/`icon`/`category_id`）。`init_app.py` `pages` 加「工作台」，`AI_BUTTON_PERMS` 加 `module_ai:workspace:*`。

- [ ] **Step 4: 测试 + 提交**

后端：`pytest` 相关用例（分类树/聚合）；`ruff check`。
```
git add backend/app/plugin/module_ai/workspace backend/app/plugin/module_ai/{agent,workflow,apps}/model.py <迁移> backend/app/scripts/init_app.py
git commit -m "feat(workspace): 工作台统一分类表+多类型关联与菜单"
```

---

## Phase 2: 前端 —— 工作台页 `/ai/workspace`（Spec 界面·工作台）

**Files:**
- Create: `frontend/src/views/module_ai/workspace/index.vue`
- Create: `frontend/src/api/module_ai/workspace.ts`
- Modify: 无（前端路由来自后端菜单）

**Interfaces:**
- Consumes: `/ai/workspace/categories/*`、`/ai/workspace/items`。
- Produces: 卡片点「对话」`router.push('/ai/workspace/chat/'+type+'/'+id)`。

- [ ] **Step 1: 页面骨架（白底工具条 + 左树 + 右卡片）**

`el-row`：左 `el-col :lg=4`（`el-tree` 分类树，含「全部」，支持新建子分类/重命名/删除），右 `el-col :lg=20`。顶部工具条白底容器（标题 + 搜索 + 类型筛选 + 「新建」下拉）。

- [ ] **Step 2: 卡片网格**

`el-row/el-col` 卡片：类型徽标（智能体/工作流/定时任务/应用，`el-tag` 区分色）+ `IconTile` 图标 + 名称 + 两行简述 + 启停 + 「对话」按钮；白底细边框圆角 + hover 上浮。

- [ ] **Step 3: 新建下拉 + 弹窗**

「新建」下拉选类型 → 跳转对应创建（复用 agent/workflow/app 的创建弹窗或列表入口；定时任务用简单弹窗）。

- [ ] **Step 4: 前端校验 + 无头浏览器截图**

`pnpm run type-check` + `eslint`；浏览器截图核对：白底工具条不落蓝灰底、左树右卡片、卡片多类型徽标、hover 上浮。

- [ ] **Step 5: 提交**

```
git add frontend/src/views/module_ai/workspace/index.vue frontend/src/api/module_ai/workspace.ts
git commit -m "feat(workspace): 工作台页（左树分类+右多类型卡片区）"
```

---

## Phase 3: 前端 —— 聊天页 `/ai/workspace/chat/:kind/:id`（Spec 界面·聊天）

**Files:**
- Create: `frontend/src/views/module_ai/workspace/chat.vue`
- Modify: `backend/app/plugin/module_ai/sessions/service.py`（`list_sessions` 按 `updated_time` 排序）
- Create: `frontend/src/api/module_ai/session.ts`（如需新增 delete-today 接口）

**Interfaces:**
- Consumes: `useAiChat`、`ChatMessages/MessageItem/ReasoningBlock/ToolCallTimeline/RichContent/ChatInput/SessionSidebar`；`/ai/agents|workflows|apps/{id}/run/stream`。
- Produces: 会话时间分组（今天/昨天/近7天/更早）。

- [ ] **Step 1: 会话时间归集 + 操作**

后端 `list_sessions` 按 `updated_time desc`；前端按 `今天/昨天/近7天/更早` 分组；会话操作：新增 / 删除单条 / 删除当天（后端补 `delete_today` 或前端按 id 批量删）。

- [ ] **Step 2: 聊天主区（AI 渲染引擎）**

用 `useAiChat` + `AgnoChatTransport`（path 指向 `/ai/{agents|workflows|apps}/{id}/run/stream`，body 传 session_id）；`ChatMessages` 渲染 `MessageItem`（含 `ReasoningBlock`/`ToolCallTimeline`/`RichContent`），流式 + 思考 + 工具 + 技能。左侧会话列表 + 右侧对话区两栏布局。

- [ ] **Step 3: 样式**

会话列表/对话区两栏，`--el-*` 变量；正文/思考/工具对齐工作台卡片风格，字体大小用 Element 默认，美观大气。

- [ ] **Step 4: 前端校验 + 无头浏览器截图**

浏览器：进入聊天页，确认左时间归集会话、右流式/思考/工具渲染、新增/删除/删除当天可用。

- [ ] **Step 5: 提交**

```
git add frontend/src/views/module_ai/workspace/chat.vue frontend/src/api/module_ai/session.ts backend/app/plugin/module_ai/sessions/service.py
git commit -m "feat(workspace): 工作台聊天页（时间归集会话+AI渲染引擎）"
```

---

## Phase 4: 定时任务类型（Spec 数据层·定时任务）

**Files:**
- Modify: `workspace/`（cron 条目 CRUD + 调度）
- Tests

- [ ] **Step 1: cron 条目 CRUD + 调度**

`ai_workspace_cron` 增删改 + `cron` 表达式 → APScheduler 触发执行绑定的 agent/workflow/app；`next_run_time` 更新。
- [ ] **Step 2: 测试 + 提交**

```
git add backend/app/plugin/module_ai/workspace
git commit -m "feat(workspace): 定时任务类型与调度"
```

---

## 收尾（全链路验收）

- 后端：全量相关 pytest + `ruff check`。
- 前端：`pnpm run type-check` + `eslint`。
- 无头浏览器全链路：工作台（树+卡片+多类型+新建）→ 点对话 → 聊天页（时间归集会话 + 流式/思考/工具/技能渲染）截图核对，任一处不美观即返工。
