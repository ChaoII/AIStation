# AI 管理 v2 · 界面与信息架构整治 全量回归与视觉验收报告

> 日期：2026-09-14
> 任务：Task 6（全量回归 + 视觉验收 + 账本）
> 设计：`docs/superpowers/specs/2026-09-13-ai-platform-ui-overhaul-design.md` §7
> 基线 HEAD：`ff4001d`（Task 5 完成；Task 1-5 均已通过逐任务 review）
> 性质：**仅验证，未改动任何产品代码**（工作区无 AI 相关代码 diff）

## 1. 环境

- 操作系统：Windows；Shell：PowerShell 7
- 后端：`http://127.0.0.1:8001`（dev，进程运行中）
- 前端：`http://127.0.0.1:5180`（Vite dev，进程运行中；应用 base `/web`，hash 路由）
- 登录态：复用 `frontend/e2e/.auth/user.json`（Playwright storageState）
- Playwright：`@playwright/test ^1.63.0`，chromium 项目，`workers: 1`，`retries: 1`

## 2. 自动化回归结果

### 2.1 后端 pytest

命令：`cd backend && uv run pytest -q`

结果：**338 passed，5 warnings，107.82s**（0 failed，0 error，0 skipped）。

warnings 均为既有 deprecation（`datetime.utcnow()` 与 `fastapi_limiter` 的 `close`），与本次界面整治无关。

### 2.2 后端 ruff

命令：`cd backend && uv run ruff check app/plugin/module_ai/ app/scripts/init_app.py`

结果：**All checks passed!**

### 2.3 前端 type-check

命令：`cd frontend && pnpm type-check`（即 `vue-tsc --noEmit`）

结果：退出码 2，**12 条错误，全部为 pre-existing，无一在 `module_ai/` 下**：

| 文件 | 行 | 说明 |
|---|---|---|
| `src/views/module_generator/gencode/index.vue` | 144,153,162 | `DefaultRow` → `GenTableSchema` |
| `src/views/module_monitor/cache/index.vue` | 163,176 | `DefaultRow` → `CacheInfo` |
| `src/views/module_monitor/resource/index.vue` | 116,143,153,163 | `DefaultRow` → `ResourceItem` |
| `src/views/module_system/user/components/UserTableSelect.vue` | 10,11 | `undefined` 作索引类型 |
| `src/views/module_task/cronjob/node/index.vue` | 50 | `DefaultRow` → `NodeTable` |
| `src/views/module_task/workflow/components/WorkflowDesignDrawer.vue` | 762 | TS2589 类型实例化过深 |

证据：上述文件最近一次改动为 `6565ec6`（2026-05-24「feat(video): 视频监控模块完整实现」），且 `git diff HEAD -- <这些路径>` 为空 → 与本轮 AI 界面工作无关联；Task 3 记录基线为 16 条，本次 12 条（更少），新增/改动文件 0 错误。

### 2.4 前端 E2E（Playwright，全量）

命令：`cd frontend && pnpm e2e`

结果：**37 tests，36 passed，1 failed，0 skipped，3.0m**（唯一失败为 `smoke`，1 次重试仍失败）。

| # | 用例 | 结果 |
|---|---|---|
| 1 | `auth.setup.ts` authenticate | ok |
| 2 | `ai-app.spec.ts` AI 应用页搜索在列表上方且新增按钮可见 | ok |
| 3 | `ai-chat.spec.ts` 智能助手输入框铺满且提示文案正确 | ok |
| 4 | `ai-chat.spec.ts` 带未知 app_id 打开智能助手不崩溃 | ok |
| 5 | `ai-logs.spec.ts` 调用日志页搜索在列表上方并展示筛选与表格 | ok |
| 6 | `ai-menu.spec.ts` AI 菜单收敛为 6 项且已下线页面不出现 | ok |
| 7 | `ai-model.spec.ts` 模型配置页可打开新增弹窗且搜索在列表上方 | ok |
| 8 | `ai-prompt.spec.ts` 提示词列表搜索在上、弹窗内画布可添加块并识别变量与预览 | ok |
| 9 | `ai-tool.spec.ts` 工具中心卡片网格：搜索在上、配置入口与就绪开关 | ok |
| 10-16 | alarm-snapshot / annotation-history / annotation-task-classes(2) / clean-drawer / collaboration / dataset-to-train | ok |
| 17-24 | deploy-edge-roi / deploy-log / edge / eval-detail(4) / export-history / repo-to-predict | ok |
| 25-26 | repo-versions / **smoke** | ok / **failed（429）** |
| 27-37 | stats / toast / train-detail(5) / train-schedule / train-to-eval / workbench | ok |

失败详情：`e2e/smoke.spec.ts:15`「登录后可进入主链路各页面且无致命渲染错误」断言 `consoleErrors` 为空，实际捕获多条 `Error: 请求过于频繁，请稍后重试`（HTTP 429）。

- 重试 #1 仍失败（429 累积，捕获条数由 3 增至 6）。
- 属**既有限流 flake**：Playwright 配置注释已说明「后端按客户端 IP 限流，多上下文并发会互相触发 429」，`smoke` 长链路连续访问多页触发全局 `fastapi_limiter`；非 AI 界面改动引入（AI 的 7 条用例全部通过）。
- 上一次 Task 7 全量回归同样记录 `smoke` 为 pre-existing 429 失败（见 `.superpowers/sdd/progress.md`）。
- 本轮 `dataset-to-train` 通过（历史 flaky，本次绿）。

## 3. 视觉验收

截图命令：Playwright 无头 chromium（1440×900，`fullPage`），脚本 `%TEMP%\opencode\ai-ui-shots\capture.cjs`；预置 `localStorage.showGuide=false` / `guideVisible=false` 屏蔽全局引导遮罩。

截图落盘目录：`C:\Users\aichao\AppData\Local\Temp\opencode\ai-ui-shots\`

| 页面 | 路由 | 截图 | 大小 |
|---|---|---|---|
| 智能助手 | `#/ai/chat` | `chat.png` | 96,880 B |
| 模型配置 | `#/ai/model` | `model.png` | 68,263 B |
| 提示词 | `#/ai/prompt` | `prompt.png` | 61,941 B |
| 工具中心 | `#/ai/tool` | `tool.png` | 128,760 B |
| AI应用 | `#/ai/app` | `app.png` | 64,163 B |
| 调用日志 | `#/ai/logs` | `logs.png` | 74,330 B |

核对方式：`vision-recognition` 技能（视觉大模型）逐图分析，判据 = 与 `frontend/src/views/module_system/param/index.vue` 一致的浅色 Element Plus（`--el-*`）、搜索/筛选在列表或卡片上方、无自定义深色主题外壳；工具中心另验 `el-card` header（头像+名称+来源/状态标签）/body（简介）/footer（开关+按钮）。

逐页结论：

| 页面 | 浅色主题 | 搜索在列表/卡片上方 | 无自定义深色外壳 | 结构 | 异常 | 判定 |
|---|---|---|---|---|---|---|
| 智能助手 `chat` | 是（白底深字） | 是（会话历史搜索在历史列表上方） | 是 | 会话栏+聊天区+输入框完整 | 无（省略号截断属正常） | **PASS** |
| 模型配置 `model` | 是 | 是（配置名称/模型名在表格上方） | 是 | Element Plus 表格+分页 | 无（1 条数据留白正常） | **PASS** |
| 提示词 `prompt` | 是 | 是（名称/分类筛选在表格上方独立卡片） | 是 | Element Plus 表格 + 空态 | 无（空数据分页未渲染属正常） | **PASS** |
| 工具中心 `tool` | 是 | 是（筛选栏在卡片网格上方） | 是 | `el-card` header(图标+名称+标签)/body(简介)/footer(开关+按钮) | 无 | **PASS** |
| AI应用 `app` | 是 | 是（名称/启用在表格上方） | 是 | Element Plus 表格（空数据） | 无 | **PASS** |
| 调用日志 `logs` | 是 | 是（用途/结果/关键字在表格上方） | 是 | Element Plus 表格+分页（4 条） | 无 | **PASS** |

说明：视觉模型首轮曾把**全局左侧深色导航栏/顶栏**误判为「自定义深色外壳」；经澄清（全局框架皮肤，`param` 等既有页同样如此）后复判，6 页主内容区均无自定义深色主题外壳。全局皮肤一致属预期。

6/6 页面视觉验收 **PASS**，与 §7 视觉一致性判据一致。

## 4. 遗留与限制

1. **E2E `smoke` 429（既有限流 flake）**：全量长链路易触发后端 IP 限流；建议 e2e 前重启后端、放宽 `fastapi_limiter` 或为 smoke 增加限流排除。非本次改动引入。
2. **前端 `type-check` 12 条 pre-existing 错误**：集中在 `module_generator/module_monitor/module_system/user/module_task`，与 AI 界面无关；本轮新增/改动文件 0 错误。
3. **长时后端运行 DB 连接池耗尽**（`QueuePool`）：历史已知，本次未复现；e2e 前重启后端或扩大池（已配置 `POOL_SIZE=20/MAX_OVERFLOW=40`）。
4. **逐任务 review 记录的 Minor 项沿用**：`aiui t1-t5` 的 minor（如 `firstChar` 头像兜底不可达、HTTP 工具测试仅在弹窗内、Agno 自定义参数仅在 toolkit `__init__` 显式形参时注入等），均为可接受遗留，不在本次整治范围。
5. **验证范围限定**：本轮为自动化回归 + 静态截图视觉核对；真机/交互式人工走查（如流式对话实际产生的 SSE 行为、Agno 工具真实执行）未在本次覆盖。

## 5. 结论

- 后端：`pytest` **338 passed**、`ruff` **clean**。
- 前端：`type-check` 仅 **12 条 pre-existing** 错误（新增/改动 0）；`e2e` **36/37 passed**，唯一失败为 **既有 429 flake（smoke）**，AI 相关 7 条用例全绿。
- 视觉：6/6 页面符合 §7 判据（浅色 Element Plus、搜索在列表/卡片上方、无自定义主题外壳；工具中心 `el-card` header/footer/avatar）。
- 未发现由本次 AI 界面/IA 整治引入的回归；无需回改产品代码。
