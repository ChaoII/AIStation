# 智能问数工作台（合并单页 + 页签）设计

- 日期：2026-10-15
- 状态：**待评审**
- 范围：前端工作台容器页 + 菜单收敛（init_app 幂等）+ 旧地址重定向 + e2e 适配

## 一、背景与目标

当前「数据与集成 / 智能问数 / 问数评测 / 自定义报表」是四个独立菜单页，在「AI」顶级目录下平铺且顺序被打散：

| 功能 | 路由 | 当前 order | 说明 |
|------|------|-----------|------|
| 数据与集成 | `/ai/integration` | 21 | 选数据源 → 选表 → 就地维护元数据 |
| 智能问数 | `/ai/query` | 33 | 会话 + 自然语言问数 |
| 问数评测 | `/ai/eval` | 34 | 测试集/运行/报表/消融/方差 |
| 自定义报表 | `/ai/query/reports` | 35 | 报表模板列表 |

中间还夹着「无代码应用(22)、治理(23)、数据资产(24)」等无关项。四个功能本质是**同一条数据链路**（接入 → 问数 → 评测 → 沉淀报表），结构相似（均为 tab 型工作页），且都归属 `module_ai:query:*` 权限。

**目标**：收敛为**一个入口 + 页面内页签切换**：

1. 菜单只保留一个「智能问数」入口（路由 ` /ai/query`），四个功能是页内的四个页签。
2. 默认落在「智能问数」页签；页签顺序按数据链路：数据与集成 → 智能问数 → 问数评测 → 自定义报表。
3. 四个页面**保持零改动**，作为子组件复用。
4. 旧地址 `/ai/eval`、`/ai/query/reports`、`/ai/integration`、`/ai/asset` 全部重定向到 `/ai/query?tab=xxx`，老书签/老链接不 404。

## 二、现状（可复用 vs 缺口）

| 已有 | 位置 |
|---|---|
| 菜单多级支持（目录→菜单，递归渲染） | `sys_menu`（type 1/2）+ `frontend/src/layouts/components/Menu/components/MenuItem.vue`（递归） |
| 启动幂等收敛菜单的先例 | `backend/app/scripts/init_app.py` `_ensure_ai_menus()`（`REMOVED_ROUTE_NAMES` 隐藏旧页面） |
| 旧地址静态重定向先例（`/ai/asset` → `/ai/integration`） | `frontend/src/router/index.ts:77-82` |
| 路由记录 `redirect` 字段（匹配后跳转、不渲染组件） | `MenuModel.redirect` + `permission.store.ts` `generator()` 透传 |
| 页面组件 keep-alive 按路由名缓存 | `AppMain/index.vue` `<keep-alive :include="cachedViews">`（tags-view 按 route name 维护） |
| 四页均为独立 `.app-container` 全屏布局 | `query/index.vue`（~800 行）、`integration/index.vue`（8 个内部页签）、`eval/index.vue`（5 个内部页签）、`query/reports.vue` |
| e2e 页面审计 | `frontend/e2e/ai-pages-audit.spec.ts`、`ig-*.spec.ts`、`shots.spec.ts`、`ig-merge.spec.ts` |

**缺口**：无工作台容器；菜单未收敛；旧地址无重定向；e2e 仍按四页地址裸测。

## 三、前端方案

### 3.1 工作台容器页（新增）

新建 `frontend/src/views/module_ai/query/workspace.vue`，作为 `/ai/query` 唯一路由组件：

- 组件名 `defineOptions({ name: "AiQuery" })` —— **必须与路由 name（菜单 route_name `AiQuery`）一致**，否则 `keep-alive :include` 缓存不生效。
- 结构：单根 `.app-container` + 唯一类 `ai-query-workspace`；内部 `el-tabs type="border-card"`（与问数评测页风格一致）+ `lazy`。
- 四个页签：

| 页签名 | tab 值 | 子组件（原文件，零改动） |
|--------|--------|--------------------------|
| 数据与集成 | `integration` | `@/views/module_ai/integration/index.vue` |
| 智能问数（默认） | `ask` | `@/views/module_ai/query/index.vue` |
| 问数评测 | `eval` | `@/views/module_ai/eval/index.vue` |
| 自定义报表 | `reports` | `@/views/module_ai/query/reports.vue` |

- `lazy` 语义：首次激活才渲染对应页，避免四页同时初始化（并发请求、首屏拖慢）；已激活页切换到别页时 DOM 保留（Element Plus tab 用 v-show），**页内状态不丢失**（会话、选中数据源、评测进度）。
- 高度：`el-tabs` 撑满 `.app-container`（flex 布局），`.el-tabs__content` 为滚动区；四个子组件根元素本身是 `.app-container`（height:100%），处于确定高度父级内，高度链路成立。样式用**非 scoped + 唯一类**（吸取「训练详情页 scoped 覆盖全局 flex 不可靠」教训），避免与全局 `.app-container` 冲突。

### 3.2 URL 参数与页签同步

- 路径：`/ai/query?tab=ask|integration|eval|reports`。
- workspace 挂载时读 `route.query.tab` 初始化；watch `route.query.tab` 同步切换（覆盖「从旧地址重定向而来」「地址栏直接改」两种场景）。
- 切换页签时 `router.replace({ path: "/ai/query", query: { ...现有 query, tab } })`，尽量保留其它参数。
- `tab` 缺省或非法 → 默认 `ask`。
- `object_code` / `object_key` 等**其它 query 参数原样保留**：子组件（`query/index.vue`）仍通过 `useRoute()` 读取，本体跳转链路（`/ai/ontology` → `/ai/query?object_code=...`）行为不变；`query/index.vue` 的 `clearObjectContext()` 里 `router.replace({ path: route.path, query })` 在子组件中 `route.path` 仍为 `/ai/query`，URL 更新与工作台 watch 兼容（子组件已自行清理自身 ref，不会出现状态复读）。

### 3.3 旧地址兼容（前端静态兜底）

按 `/ai/asset` 先例在 `frontend/src/router/index.ts` 增加四条隐藏转发（覆盖动态路由未加载、新库无旧菜单、未登录等场景）：

- `/ai/eval` → `/ai/query?tab=eval`
- `/ai/query/reports` → `/ai/query?tab=reports`
- `/ai/integration` → `/ai/query?tab=integration`
- `/ai/asset` → `/ai/query?tab=integration`（更新现有条目，原指向 `/ai/integration`）

## 四、菜单收敛（后端，启动幂等）

在 `backend/app/scripts/init_app.py` 的 `_ensure_ai_menus()` 中扩展（仿 `REMOVED_ROUTE_NAMES` 模式，新库/存量库均自愈，无需手跑脚本）：

1. **新库**：`pages` 列表删除 `AiIntegration`(21)、`AiEval`(34)、`AiQueryReports`(35)、`AiAsset`(24) 四项；`AiQuery` 保留为唯一可见入口：`component_path="module_ai/query/workspace"`、order=33、`hidden=False`、`permission="module_ai:query:ask"`、keep_alive 保持默认 true。
2. **存量库幂等**：
   - 对 `AiIntegration` / `AiEval` / `AiQueryReports` / `AiAsset`：`hidden=True`，并设置 `redirect="/ai/query?tab=integration|eval|reports"`（带 redirect 的路由记录被匹配后直接跳转，不渲染旧组件；component_path 保留无害）。
   - `AiQuery`：更新 `component_path` / `order` / `hidden=False`，并保证 admin 角色已授权（沿用现有幂等授权循环）。
3. 历史一次性脚本 `backend/scripts/register_eval_menu.py`、`register_query_reports_menu.py`、`fix_ai_menu_wiring.py` 的 docstring 标注「已被 init_app 幂等逻辑取代，勿再运行」，避免运维再跑把旧菜单/旧 order 写回。

## 五、联动行为（保持现状）

- 「存为报表」保存成功后仍为 `ElMessage` 提示「已在报表列表确认（可在『自定义报表』页签查看）」，**不自动切页签**（避免跨子组件刷新时序问题）。
- 问数页头部「查看本体」仍跳 `/ai/ontology`；本体/实例页跳问数的 `object_code` 参数链路不变。
- 无新增后端接口、无数据库表变更、无权限变更（合并前后均为 `module_ai:query:ask`）。

## 六、改动文件清单

| 操作 | 文件 |
|------|------|
| 新增 | `frontend/src/views/module_ai/query/workspace.vue` |
| 修改 | `frontend/src/router/index.ts`（旧地址静态转发） |
| 修改 | `backend/app/scripts/init_app.py`（`_ensure_ai_menus` 幂等收敛） |
| 修改 | `frontend/e2e/ai-pages-audit.spec.ts`（工作台 + 重定向后 tab 渲染） |
| 修改 | `frontend/e2e/ig-merge.spec.ts`（菜单断言：仅剩一个「智能问数」入口） |
| 修改（按需） | `frontend/e2e/ig-check.spec.ts`、`ig-edit.spec.ts`、`ig-batch.spec.ts`、`ig-batch-save.spec.ts`、`shots.spec.ts`（访问旧地址走重定向，交互不变） |
| 文档标注 | `backend/scripts/register_eval_menu.py`、`register_query_reports_menu.py`、`fix_ai_menu_wiring.py`（docstring 废弃说明） |

## 七、测试与验证

1. 前端：`pnpm run type-check`、`pnpm run lint`。
2. e2e（Playwright）：
   - `ai-pages-audit.spec.ts`：`/ai/query` 工作台渲染；`/ai/integration`、`/ai/eval`、`/ai/query/reports` 重定向后对应页签内容渲染（marker 分别为 `.ai-integration-page` / `.ai-eval-page` / `.ai-query-reports`）。
   - `ig-merge.spec.ts`：菜单断言更新——菜单含「智能问数」，不含「数据与集成 / 问数评测 / 自定义报表」作为独立菜单项；旧地址 `/ai/asset` 重定向到 `/ai/query?tab=integration`。
   - `ig-*.spec.ts` / `shots.spec.ts`：访问旧地址后等重定向完成，原有交互断言不变。
3. 后端：`test_query.py`、`test_query_eval.py`、`test_query_report.py` 回归全过（菜单改动不影响纯逻辑；如 init_app 有既有测试同样纳入）。
4. 启动验证：新库（清空重建 seed）与存量库（对现有开发库跑一次升级）各验证一次菜单结果正确。
5. 视觉核对：无头浏览器截图（工作台四页签 + 各子页），用多模态读图核对与既有 AI 页面风格一致（Element Plus 组件、`--el-*` 变量、单根布局）。

## 八、风险与对策

| 风险 | 对策 |
|------|------|
| 四页嵌进 tabs 后高度/滚动异常（嵌套滚动、白屏） | 非 scoped 样式 + 唯一类；实现后逐页截图核对；必要时将 `.el-tabs__content` 滚动子级调整为 `overflow: hidden` 让子页自管滚动 |
| 组件名冲突：子页面 `defineOptions` name（`AiQuery`/`AiEval`/`AiQueryReports`）与 workspace 同名 | workspace 用 `AiQuery`（与路由 name 一致，保证 keep-alive 生效）；子组件名称已存在且有区分，若 Vue 对非路由子组件重名无硬性限制，此处仅 workspace 参与 keep-alive include |
| 隐藏旧菜单后动态路由仍注册（transformRoutes 不过滤 hidden） | 旧菜单设置 `redirect`（匹配即跳转，不渲染），配合前端静态兜底，双保险；旧组件文件保留不动，可随时还原 |
| 存量库跑历史脚本把旧菜单写回 | 三个历史脚本 docstring 废弃标注；init_app 启动幂等兜底（每次启动都会再收敛） |
| `tab` 参数与 `object_code` 并存时互相覆盖 | workspace 切换仅更新 `tab`，其余 query 参数原样保留；`object_code` 由子组件读取，不参与 workspace 的 watch 冲突 |
