# AI 管理 v2 · 界面与信息架构整治设计

> 创建日期：2026-09-13
> 状态：用户已确认方向，待审阅
> 关联：`2026-09-13-ai-platform-v2-design.md`（功能实现已完成）

## 1. 目标

把 AI 管理从「稀稀拉拉、各页各风格」收敛为一套与系统框架一致的界面：

1. **精简信息架构**：删掉重复/无用的页面，只留 6 个菜单。
2. **统一到框架规范**：所有列表页 = 顶部搜索（`PageSearch`）+ 下方表格（`PageContent`）+ 弹窗表单（`EnhancedDialog`），与 `module_system/param` 一致。
3. **智能助手作为唯一交互入口**：保留现有布局，修好输入框，AI 应用也在这里运行。
4. **工具中心接入 Agno 精选内置工具**：可开关、可配置 Key/参数，缺依赖/Key 时状态可见。
5. **移除「提供商」独立页**：模型配置自带 base_url/api_key，不再需要单独的提供商页。

## 2. 信息架构（最终菜单）

AI 管理（父菜单）默认落地 `/ai/chat`：

| 顺序 | 标题 | 路径 | 组件 | 权限 |
|---|---|---|---|---|
| 1 | 智能助手 | `/ai/chat` | `module_ai/chat/index` | `module_ai:chat:query` |
| 2 | 模型配置 | `/ai/model` | `module_ai/model/index` | `module_ai:model:query` |
| 3 | 提示词 | `/ai/prompt` | `module_ai/prompt/index` | `module_ai:prompt:query` |
| 4 | 工具中心 | `/ai/tool` | `module_ai/tool/index` | `module_ai:tool:query` |
| 5 | AI应用 | `/ai/app` | `module_ai/app/index` | `module_ai:app:query` |
| 6 | 调用日志 | `/ai/logs` | `module_ai/logs/index` | `module_ai:assistant:query` |

**移除**：控制台 `/ai/overview`、运行台 `/ai/playground`、提供商 `/ai/provider`、AI报告 `/ai/report`、会话记忆 `/ai/memory`。

- 前端删除对应页面目录；后端模块保留（不删路由/表，兼容旧数据），仅不注册菜单、不显示页面。
- `init_app.py::_ensure_ai_menus`：父菜单 redirect 固定 `/ai/chat`；不再创建 removed 页面；对存量库将 removed 页面 `hidden=True`；`memory` 强制隐藏；`chat` 保持显示。
- 保留的按钮权限按需保留；removed 的权限不再新增（已有的可不动）。

## 3. 智能助手页（`module_ai/chat/index.vue`）

保留现有三栏布局与会话历史交互，做以下定点修改：

1. **会话历史栏**：维持 200px ↔ 64px 收起（顶栏按钮切换），不改行为。
2. **输入框修复**（`components/ChatInput.vue`）：
   - `.input-wrapper` 去掉 `max-width: 800px` 居中限宽 → 铺满聊天区（左右内边距 16px）。
   - 减小内边距（`input-container` padding 约 `8px 12px`），发送/附件按钮**内联在输入行右侧**，去掉独占一行的 footer。
   - 输入框 1 行起步、`autosize {minRows:1, maxRows:6}`；去掉单独占行的 `.input-hint`，提示并入 placeholder：「输入消息…（Enter 发送 / Shift+Enter 换行）」。
   - 占位符去掉残留的「FA助手」。
3. **去掉 Agno WebSocket 依赖**：发送/接收已走 AI SDK 运行时时流式；输入框不再因 WS 连接状态被禁用。移除 `connectWebSocket`/`disconnectWebSocket` 与相关状态；`ChatNavbar` 的连接/重连控件相应移除，保留「新建会话 / 清空 / 收起会话栏」。
4. **AI 应用运行入口**：
   - AI应用列表行内「运行」→ `router.push({ path: "/ai/chat", query: { app_id } })`。
   - 助手页读取 `app_id`：拉取应用详情，顶部（`ChatNavbar`）显示一个**可关闭**的「应用：<名称>」`el-tag`；流式走 `/ai/apps/{id}/run/stream`（`useAiChat` 的 getter 动态切换 path/body）。
   - 关闭标签 → 回到通用助手 `/ai/assistant/stream`。
   - 会话/历史与会话落库沿用现有 `session_id` 机制。

## 4. 列表页 CRUD 规范化

统一结构（每页单一根元素）：

```
<PageSearch/>            ← 顶部整行搜索
<PageContent>            ← 下方表格 + 分页 + 工具栏
<EnhancedDialog/>        ← 新增/编辑表单
```

适用页面与要点：

- **模型配置**：搜索（名称/模型名）；表格列同现；表单去掉「提供商」下拉，保留 base_url/api_key/extra_headers/usage/capabilities/context_window/默认/启用。
- **提示词**：改为「列表（名称/分类/版本/启用/操作）+ 编辑」；点「编辑」打开**全屏 `EnhancedDialog`** 承载现有三栏画布（左块列表拖拽、中编辑、右变量+预览），保存复用现有 API。
- **AI应用**：搜索（名称/启用）；表格列（图标/名称/模型/提示词/工具数/输出格式/启用/操作）；操作含「运行」；表单沿用现有字段。
- **调用日志**：搜索（用途/结果/关键字/时间）；表格分页；只读，无新增。
- **工具中心**：改为**单列表**（不再用 tabs）：搜索（名称/类型/状态）+ 表格（名称/类型/状态/启用/操作）；类型列区分「系统 / Agno / HTTP」；新增/编辑走 `EnhancedDialog`（HTTP 工具表单同现；Agno 工具表单展示配置项）。移除混在页头/工具栏的搜索或标签页。

## 5. 工具中心 · Agno 精选工具

### 5.1 数据模型扩展

`ai_tools` 新增：

- `source` `VARCHAR(16)` default `"system"`：`system` | `agno` | `http`（旧 `kind` 字段可继续使用/兼容）。
- `config` `JSONB` nullable：Agno/HTTP 工具的运行配置（如 `api_key`、`base_url`）。

### 5.2 精选清单（可开关 + 配置）

- **离线安全**：`calculator`、`csv_toolkit`、`visualization`、`webtools.expand_url`、`hackernews`、`python`（高级）、`shell`（高级，默认关）。
- **联网（需 Key / 额外依赖）**：`tavily`、`serpapi`、`duckduckgo`、`wikipedia`、`openweather`、`newspaper`、`arxiv`。

> 安装/可用性以运行时探测为准；未安装依赖或未配置必需 Key 的工具在列表中标记「未就绪」并禁止启用。

### 5.3 后端解析与执行

新增 `app/plugin/module_ai/agno_tools/`：

- `registry.py`：精选工具注册表，每项含 `key`、显示名、`module`、`class`、`requires`(pip 包/依赖名)、`config_fields`(如 `api_key`)、`group`、`risk`。
- `service.py`：
  - `get_tool_specs()` → 列表（含 `ready` 与 `reason`）。
  - `build_schema(spec)`：惰性 import 并实例化 Agno toolkit，取 `.functions`，用 `inspect.signature(entrypoint)` + docstring 生成 OpenAI function schema（`fn.parameters` 为空时回退 signature）。
  - `execute(spec, args, config)`：`await/调用 entrypoint(**args)`；异常返回 `{"error": ...}`。
  - 启动同步 `_ensure_agno_tools()`：把精选工具写入 `ai_tools`（`source="agno"`，缺失则插入，默认 `enabled=False`，不覆盖已有配置）。
- `tools_catalog/service.py::get_enabled_tool_schemas()` 合并三类：系统（`TOOL_REGISTRY`）、Agno（`agno_tools.service`）、HTTP。
- 运行循环的工具派发按 `source` 分派：system→`_call_tool`，agno→`agno_tools.service.execute`，http→`execute_http_tool`。
- 缺依赖/缺 Key：schema 不下发、执行返回明确错误，不打断流。

## 6. 非目标（Out of Scope）

- 不接入 Agno 全量 100+ 工具箱（仅精选集）。
- 不删除后端 `overview`/`report`/`provider` 模块与表（仅前端下线）。
- 不改动 AI SDK UI Message Stream 协议、模型/提示词/应用/会话的既有数据结构。
- `generate_report` 保留生成能力；因报告页下线，暂不在 UI 暴露（后续可加回）。

## 7. 验收与测试

- **视觉一致性**：6 个页面均与 `module_system/param` 一致（浅色 `el-card`、`--el-*`、无自定义主题外壳、搜索在列表上方）；用无头截图 + `vision-recognition` 核对。
- **智能助手**：输入框铺满、1 行起步自动增高、按钮内联；会话栏 200↔64；`?app_id=` 显示可关闭应用标签并走应用流。
- **后端**：`uv run pytest -q` 全绿 + 改动文件 `ruff check` clean；新增 Agno 解析（calculator schema/execute）、就绪性、工具分派测试。
- **前端**：`pnpm type-check` 新增文件 0 错误；各页 E2E 更新（搜索在上、列表在下）；关键页面截图视觉验收。

## 8. 兼容与迁移

- `ai_tools` 新列经 `init_app.py::_ensure_missing_columns` 补列（含 SQLite 分支）。
- 存量 `ai_tools` 行 `source` 默认 `system`；原 HTTP 工具按 `kind=http` 迁移为 `source=http`。
- 存量菜单：removed 页面置 `hidden=True`；不删除历史数据。

## Self-Review

- 覆盖用户诉求：删运行台/提供商/控制台/报告/记忆（§2）；输入框（§3.2）；会话栏收起（§3.1）；搜索/列表规范（§4）；Agno 工具（§5）。
- 一致：全部复用既有 API 与 `useAiChat` getter；协议与数据结构不变。
- 风险：Agno 工具依赖/Key 差异由「就绪性」兜底；删除前端页面需同步清理菜单与 API 引用，避免死链。
