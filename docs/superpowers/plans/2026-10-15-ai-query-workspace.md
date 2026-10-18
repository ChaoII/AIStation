# 智能问数工作台 Implementation Plan

> **⚠️ 状态：已废弃（2026-10-15 晚）**。该方案（单入口 + 页签工作台）已被用户否决，
> 改为「智能问数」独立菜单目录 + 4 个独立子菜单页面（见 `2026-10-15-ai-query-group-design.md`）。
> 本文仅作历史记录。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「数据与集成 / 智能问数 / 问数评测 / 自定义报表」四个独立菜单页收敛为「智能问数」单入口 + 页内四个页签，旧地址全部重定向到 `/ai/query?tab=xxx`。

**Architecture:** 新增前端容器组件 `module_ai/query/workspace.vue`（el-tabs + lazy），四个现有页面零改动作为子组件复用；后端 `init_app._ensure_ai_menus()` 启动幂等收敛菜单（新库不建、存量库隐藏 + redirect）；前端 `router/index.ts` 静态转发兜底旧地址。

**Tech Stack:** Vue 3 + Element Plus（前端）、FastAPI + SQLAlchemy（后端 `init_app`）、Playwright（e2e）、pytest（后端单测）。

**Spec:** `docs/superpowers/specs/2026-10-15-ai-query-workspace-design.md`

## Global Constraints

- 所有回复/注释/提交信息用中文；提交信息格式 `feat(ai-query): 中文描述`。
- 四个现有页面文件**零改动**：`query/index.vue`、`eval/index.vue`、`query/reports.vue`、`integration/index.vue` 一律不修改。
- workspace 组件名必须为 `AiQuery`（与菜单 route_name 一致，keep-alive include 按此匹配）。
- 菜单权限保持 `module_ai:query:ask` 不变；不新增后端接口、不新增数据库表。
- workspace 模板保持单根；布局样式用**非 scoped + 唯一类**（`ai-query-workspace`），字号/颜色引用 `--el-*` 变量（AGENTS.md 前端规范）。
- 后端测试效率：只跑单文件；命令用 `backend/.venv/Scripts/python.exe -m pytest tests/test_xxx.py -q`（避免 `uv run` 额外开销）；`test_ai_menus.py` 需要 DB（app 模式，勿加 `PYTEST_NO_APP=1`）。
- e2e 运行：需前后端 dev 服务已启动（backend `8001`、frontend `5180`），`pnpm e2e <spec>`（workers=1，路由为 hash，URL 形如 `/#/ai/query`）。

## Review Focus

1. `?tab=` 缺省或非法值 → 必须默认落在「智能问数」页签（不白屏、不 404）。→ Task 2 e2e 断言。
2. 旧地址带其它 query（如 `object_code`）重定向后不丢失（`/ai/query?object_code=x` 切 tab 时保留该参数）。→ Task 2 e2e 断言。
3. 存量库中旧菜单 `component_path=""`（历史脚本创建过空组件）→ 隐藏 + redirect 后直达旧地址仍正确跳转，不渲染 404。→ Task 2 e2e 断言 + Task 1 单测覆盖 redirect。
4. 页签切换后子页状态保留（lazy + v-show），再次切回不重新初始化白屏。→ Task 2 e2e 断言 `.ai-integration-page` 等元素在切换后仍存在。
5. 收敛后侧边栏只剩「智能问数」一个入口（「数据与集成/问数评测/自定义报表/数据资产」不再是平级菜单项）。→ Task 3 e2e 断言。

---

### Task 1: 后端菜单收敛（init_app 幂等 + 单测）

**Files:**
- Modify: `backend/tests/test_ai_menus.py`
- Modify: `backend/app/scripts/init_app.py`（`_ensure_ai_menus`）
- Modify: `backend/scripts/register_eval_menu.py`、`backend/scripts/register_query_reports_menu.py`、`backend/scripts/fix_ai_menu_wiring.py`（docstring 标注废弃）

**Interfaces:**
- Consumes: `init_app._ensure_ai_menus()`（无参，启动幂等，直接对 DB 生效）；`test_ai_menus.py` 现有 `_fetch_menus()` helper。
- Produces: 菜单状态约定——`AiIntegration`/`AiEval`/`AiQueryReports`/`AiAsset` 为 `hidden=True` 且 redirect 分别为 `/ai/query?tab=integration`、`/ai/query?tab=eval`、`/ai/query?tab=reports`、`/ai/query?tab=integration`；`AiQuery` 为 `hidden=False`、`component_path="module_ai/query/workspace"`、`permission="module_ai:query:ask"`、`order=33`。

- [ ] **Step 1: 扩展 `test_ai_menus.py`，写失败测试**

在 `test_ai_menus_collapsed` 旁新增 `test_ai_menus_merge_workspace(test_client)`：

```python
MERGED = {
    "AiIntegration": "/ai/query?tab=integration",
    "AiEval": "/ai/query?tab=eval",
    "AiQueryReports": "/ai/query?tab=reports",
    "AiAsset": "/ai/query?tab=integration",
}


def _ensure_merged_rows_visible() -> None:
    """保证待合并菜单在库中存在且可见，模拟存量库（component_path 留空）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.core.database import async_db_session

    async def _run() -> None:
        async with async_db_session() as db:
            async with db.begin():
                parent = await db.scalar(
                    select(MenuModel).where(MenuModel.route_name == "AI", MenuModel.type == 1)
                )
                assert parent is not None, "AI 父菜单不存在（种子数据未初始化）"
                for rname, _ in MERGED.items():
                    row = await db.scalar(
                        select(MenuModel).where(MenuModel.route_name == rname)
                    )
                    if row:
                        row.hidden = False
                        row.redirect = None
                        continue
                    db.add(
                        MenuModel(
                            name=rname, type=2, order=99, route_name=rname,
                            route_path=f"/ai/{rname.lower()}", component_path="",
                            parent_id=parent.id, status="0", is_deleted=False,
                            hidden=False, title=rname,
                        )
                    )

    asyncio.run(_run())


def test_ai_menus_merge_workspace(test_client):
    """_ensure_ai_menus 后：四个功能页被隐藏并重定向到工作台，智能问数为唯一入口。"""
    _ensure_merged_rows_visible()
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()

    for rname, redirect in MERGED.items():
        assert rname in menus, f"缺少待合并菜单 {rname}"
        assert menus[rname].hidden is True, f"{rname} 未被隐藏"
        assert menus[rname].redirect == redirect, f"{rname} redirect 应为 {redirect}"
    ask = menus["AiQuery"]
    assert ask.hidden is False, "智能问数不应被隐藏"
    assert ask.component_path == "module_ai/query/workspace", "智能问数应指向工作台容器"
    assert ask.permission == "module_ai:query:ask"
    assert ask.order == 33
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ai_menus.py::test_ai_menus_merge_workspace -q`
Expected: FAIL（`AiIntegration 未被隐藏` 等断言失败）

- [ ] **Step 3: 修改 `init_app.py`**

在 `_ensure_ai_menus()` 中：
1. 新增模块级常量 `AI_MERGE_WORKSPACE: dict[str, str] = {"AiIntegration": "/ai/query?tab=integration", "AiEval": "/ai/query?tab=eval", "AiQueryReports": "/ai/query?tab=reports", "AiAsset": "/ai/query?tab=integration"}`。
2. `pages` 列表：删除 `AiIntegration`、`AiEval`、`AiQueryReports`、`AiAsset` 四项（新库不再创建）。
3. 存量库幂等块（现有 `update` 段附近）：对 `AI_MERGE_WORKSPACE` 中每个 route_name 执行 `update(MenuModel).where(route_name==rn).values(hidden=True, redirect=target)`；对 `AiQuery` 的 update 增加 `component_path="module_ai/query/workspace"`（现有代码已 update hidden/order/permission，在其 `.values(...)` 中补该字段）。
4. 保持现有 `AiQuery` 授权幂等循环不变。

- [ ] **Step 4: 运行，确认通过 + 回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_ai_menus.py -q`
Expected: PASS（既有 `test_ai_menus_collapsed` / `test_ai_button_perms_keep_provider_report` 不回归）

- [ ] **Step 5: 三个历史脚本 docstring 标注废弃**

在 `backend/scripts/register_eval_menu.py`、`register_query_reports_menu.py`、`fix_ai_menu_wiring.py` 首行 docstring 增加一行：`已被 backend/app/scripts/init_app.py 的 _ensure_ai_menus 幂等逻辑取代（2026-10-15），请勿再运行，避免把旧菜单/旧顺序写回。`

- [ ] **Step 6: 提交**

```bash
git add backend/tests/test_ai_menus.py backend/app/scripts/init_app.py backend/scripts/
git commit -m "feat(ai-query): 菜单收敛为智能问数工作台入口并幂等迁移存量库"
```

---

### Task 2: 前端工作台容器 + 旧地址转发 + e2e 验收

**Files:**
- Create: `frontend/e2e/ai-query-workspace.spec.ts`（先写，红）
- Create: `frontend/src/views/module_ai/query/workspace.vue`
- Modify: `frontend/src/router/index.ts`（旧地址静态转发）

**Interfaces:**
- Consumes: 四个现有子组件（路径即组件，零改动）；`/ai/query` 动态路由（Task 1 后菜单指向 workspace）。
- Produces: `workspace.vue` 组件（name `AiQuery`）；URL 约定 `?tab=ask|integration|eval|reports`；静态转发 `/ai/eval`、`/ai/query/reports`、`/ai/integration`、`/ai/asset` → `/ai/query?tab=...`（均 `meta.hidden: true`）。

- [ ] **Step 1: 编写 e2e 验收 spec（预期红）**

Create `frontend/e2e/ai-query-workspace.spec.ts`（参照 `ig-merge.spec.ts` 的 auth/tour 处理），断言：
1. `/#/ai/query` 打开后 `.ai-query-workspace` 可见，且 `.ai-query-page`（智能问数子页）可见（默认 tab=ask），URL 含 `tab=ask`（默认落库后 route.replace 生效）。
2. 点击「问数评测」页签 → `.ai-eval-page` 可见；再点「数据与集成」→ `.ai-integration-page` 可见，且切换后前者仍存在于 DOM（v-show 保留）。
3. `/#/ai/query?tab=reports` 直达 → `.ai-query-reports` 可见。
4. `/#/ai/query?tab=illegal` → 回落到 `.ai-query-page`。
5. 旧地址：`/#/ai/eval` → 最终 URL 含 `?tab=eval` 且 `.ai-eval-page` 可见；`/#/ai/query/reports` → `?tab=reports` + `.ai-query-reports`；`/#/ai/integration` → `?tab=integration` + `.ai-integration-page`；`/#/ai/asset` → `?tab=integration`。
6. 参数保留：`/#/ai/query?object_code=USER` 下点「问数评测」页签后，URL 仍含 `object_code=USER` 且含 `tab=eval`。

- [ ] **Step 2: 运行 e2e 确认失败**

Run: `cd frontend && pnpm e2e ai-query-workspace.spec.ts`
Expected: FAIL（`.ai-query-workspace` 不存在等；前置：后端已跑 Task 1 后的版本或至少 dev 服务可用）

- [ ] **Step 3: 实现 `workspace.vue`**

Create `frontend/src/views/module_ai/query/workspace.vue`：
- `defineOptions({ name: "AiQuery" })`；单根 `div.app-container.ai-query-workspace`。
- `el-tabs v-model="tab" type="border-card" lazy`，页签顺序：数据与集成(integration) → 智能问数(ask) → 问数评测(eval) → 自定义报表(reports)，pane 内容分别引入四个现有组件（`import ... from "./index.vue"` 等）。
- 从 `route.query.tab` 初始化（非法/缺省 → `"ask"`），并在初始化后 `router.replace` 回写 `tab`（保证 URL 恒有合法 `tab`，e2e 断言依赖）；`watch(() => route.query.tab)` 同步；页签切换 `router.replace({ path: "/ai/query", query: { ...route.query, tab } })`（保留其它参数）。
- 样式：非 scoped `<style>` + `.ai-query-workspace` 唯一类，`el-tabs` 撑满高度、`.el-tabs__content` 为滚动区（参考 `train-detail.css` 的已知可靠做法）；不改任何全局 `.app-container` 规则。

- [ ] **Step 4: `router/index.ts` 增加静态转发**

按现有 `/ai/asset` 条目样式，在 `constantRoutes` 中新增（`/ai/asset` 条目改为指向 `/ai/query?tab=integration`）：
`/ai/eval` → `/ai/query?tab=eval`；`/ai/query/reports` → `/ai/query?tab=reports`；`/ai/integration` → `/ai/query?tab=integration`，均 `meta: { hidden: true }`，name 分别 `AiEvalMoved` / `AiQueryReportsMoved` / `AiIntegrationMoved`（`AiAssetMoved` 保留，redirect 更新）。

- [ ] **Step 5: 验证**

Run: `cd frontend && pnpm run type-check`
Expected: PASS

Run: `cd frontend && pnpm e2e ai-query-workspace.spec.ts`
Expected: PASS（全部断言通过；若个别用例受 dev 环境时序影响，按 playwright 配置的 1 次重试评估是否环境问题）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/module_ai/query/workspace.vue frontend/src/router/index.ts frontend/e2e/ai-query-workspace.spec.ts
git commit -m "feat(ai-query): 新增问数工作台页签容器并兼容旧地址"
```

---

### Task 3: 适配既有 e2e（菜单断言 + 走查脚本）

**Files:**
- Modify: `frontend/e2e/ig-merge.spec.ts`（改为断言式：菜单收敛 + 旧地址）
- Modify: `frontend/e2e/ai-pages-audit.spec.ts`（PAGES 增加 `/ai/eval`、`/ai/query/reports` 条目，注释更新 `/ai/query` 为工作台）
- Modify（按需）: `frontend/e2e/shots.spec.ts`（`/#/ai/query/reports` 截图前等待重定向完成）、`ig-check.spec.ts` / `ig-edit.spec.ts` / `ig-batch.spec.ts` / `ig-batch-save.spec.ts`（访问 `/#/ai/integration` 后等 URL 含 `tab=integration` 再操作，若现有等待已覆盖则不动）

**Interfaces:**
- Consumes: Task 1/2 后的菜单与路由行为。
- Produces: 无新接口；仅测试适配。

- [ ] **Step 1: 改写 `ig-merge.spec.ts` 为断言**

把 console.log 式走查改为 `expect` 断言：① `/#/ai/asset` 与 `/#/ai/integration` 均重定向到含 `tab=integration` 的 URL；② 侧边栏 `.el-menu` 文本含「智能问数」，且**不含**「数据与集成 / 问数评测 / 自定义报表 / 数据资产」（这些不再是平级菜单项）。

- [ ] **Step 2: 更新 `ai-pages-audit.spec.ts`**

PAGES 列表：`/ai/query` 名称注释改「智能问数（工作台）」；新增 `{ path: "/ai/eval", name: "问数评测(应重定向)", ... }`、`{ path: "/ai/query/reports", name: "自定义报表(应重定向)", ... }`；marker 保持 `.app-main .app-container`（重定向后仍满足）。

- [ ] **Step 3: 按需适配 `shots.spec.ts` / `ig-*.spec.ts`**

检查各 spec 访问旧地址处的等待逻辑：goto 后 `waitForURL(/\?tab=integration/)` 或等 `.ai-integration-page` 可见再继续；不改变原有交互断言。

- [ ] **Step 4: 验证**

Run: `cd frontend && pnpm run lint`
Expected: PASS（既有 lint 已知报错文件不在本次改动范围，忽略预存问题）

Run: `cd frontend && pnpm e2e ig-merge.spec.ts ig-check.spec.ts shots.spec.ts`
Expected: PASS（若环境串行超时，单文件重跑确认）

- [ ] **Step 5: 提交**

```bash
git add frontend/e2e/
git commit -m "test(ai-query): 适配工作台e2e断言与菜单走查"
```

---

### Task 4: 全栈回归 + 视觉核对

**Files:**
- 无新增/修改（仅验证；若发现问题按 Task 1/2 补丁提交）

**Interfaces:**
- Consumes: 全部前置任务。

- [ ] **Step 1: 后端回归**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query.py tests/test_query_eval.py tests/test_query_report.py tests/test_ai_menus.py -q`
Expected: PASS

- [ ] **Step 2: 前端静态检查**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
Expected: PASS（忽略预存 lint 报错文件）

- [ ] **Step 3: 视觉核对（无头浏览器截图 + 多模态读图）**

用 Playwright 截图脚本（或现有 `shots.spec.ts` 流程）分别打开并截图：`/#/ai/query`（默认页签）、`/#/ai/query?tab=integration`、`/#/ai/query?tab=eval`、`/#/ai/query?tab=reports`；直接用模型多模态能力读图，与 `module_ai/overview`、`module_ai/ontology` 等既有页面核对：Element Plus 组件观感、字号（正文 14px / 次要 12px）、`--el-*` 变量、无自造主题色。若发现风格割裂或高度/滚动异常，回 Task 2 修补后再截图确认。

- [ ] **Step 4: 存量库启动验证 + 提交**

对现有开发库执行一次后端启动（`uv run main.py run --env=dev` 启动日志无报错），确认菜单收敛幂等执行；若期间发现需修补，随对应任务补丁提交（如无问题则本任务无提交；必要时追加 `docs(ai-query): 更新实现说明`）。

**最终提交说明：** 按 AGENTS.md 要求，本计划内所有提交信息使用 `feat(ai-query): 中文描述` / `test(ai-query): 中文描述` 格式。
