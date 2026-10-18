# 智能问数独立菜单目录设计（替代工作台方案）

- 日期：2026-10-15
- 状态：**已实施**（替代「工作台」方案，工作台方案已废弃）
- 范围：后端 `init_app` 幂等回退迁移 + 前端路由改造 + 删除工作台容器 + 测试/e2e 适配

## 一、背景

原「智能问数」为单入口 + 四个页签的工作台（`workspace.vue`），用户认为集成「别扭」，
要求结构明确：改为**独立菜单目录 + 4 个独立子菜单/页面**。

## 二、目标结构

「AI」顶级目录下新增目录「智能问数」（type=1，route_name=`AiQueryGroup`，order=33），
下挂 4 个子菜单（type=2，权限均为 `module_ai:query:ask`）：

| 子菜单 | route_name | 路由 | component_path | order |
|--------|-----------|------|----------------|-------|
| 数据与集成 | AiIntegration | `/ai/integration` | `module_ai/integration/index` | 1 |
| 智能问数 | AiQuery | `/ai/query` | `module_ai/query/index` | 2 |
| 问数评测 | AiEval | `/ai/eval` | `module_ai/eval/index` | 3 |
| 自定义报表 | AiQueryReports | `/ai/query/reports` | `module_ai/query/reports` | 4 |

数据资产（AiAsset）不单列：保持 hidden，`redirect → /ai/integration`（并入数据与集成）。

## 三、后端实现（`app/scripts/init_app.py`）

- 删除 `AI_MERGE_WORKSPACE` 收敛逻辑（原来把四页 hidden + redirect 到工作台页签）。
- 新增常量 `QUERY_GROUP` / `QUERY_GROUP_TITLE` / `QUERY_GROUP_MENUS`。
- `_ensure_ai_menus()` 幂等迁移：
  1. 目录不存在则创建（type=1，挂 AI 父菜单，授予 role 1）；已存在则复用并保证可见/图标。
  2. 四个子菜单：不存在则创建；已存在则 update（恢复可见、清 redirect、恢复 component_path、
     挂到目录下、补权限/排序/图标）。
  3. `AiAsset`：隐藏 + `redirect=/ai/integration`。
- 幂等：重复调用不重复创建、不报错（测试断言覆盖）。
- 存量库重启即生效（lifespan 调用 `_ensure_ai_menus`），无需手工 INSERT。

## 四、前端实现

- 删除 `src/views/module_ai/query/workspace.vue`（工作台容器）。
- `src/router/index.ts`：
  - 删除 4 条「旧地址 → /ai/query?tab=xxx」静态重定向（会拦截新独立路由），
    保留 `/ai/asset → /ai/integration` 静态兜底。
  - 新增全局 `beforeEach`：`/ai/query?tab=integration|eval|reports` → 对应独立页；
    无 tab / tab=ask / 非法值留在问数页（避免同 path 重定向死循环）。

## 五、测试

- 后端 `tests/test_ai_menus.py::test_ai_menus_query_group`：从「工作台遗留状态」迁移到目录结构
  （目录存在、4 子菜单可见/独立 component/无 redirect、AiAsset hidden→/ai/integration、幂等）。
- e2e：`ai-query-menu.spec.ts`（目录 + 4 独立页 + tab 兼容 + /ai/asset 重定向）、
  `ai-menu.spec.ts`、`ig-merge.spec.ts`（均改为目录结构断言）、`ai-pages-audit.spec.ts`
  （页面标注更新）。

## 六、废弃脚本/文档

- `scripts/register_eval_menu.py`、`register_query_reports_menu.py`、`fix_ai_menu_wiring.py`
  为历史一次性脚本，维持废弃状态，不纳入本次改动。
- 旧 spec/plan（`2026-10-15-ai-query-workspace-*`）已标注「已废弃」。
