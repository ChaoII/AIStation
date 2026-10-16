# 智能体中心卡片 + 智能体对话界面重构 设计

> 日期：2026-10-16
> 范围：前端 `frontend/src/views/module_ai/agent/index.vue`、`market/components/IconTile.vue`；后端图标生成脚本。

## 背景与问题

用户反馈两点「丑」：
1. **智能体中心卡片「巨丑/抽象」**：当前 `agent/index.vue` 用 `el-card shadow="hover"` + 彩色首字母圆形头像 + 全选框 + 一堆标签 + 6 个操作按钮（`agent-card` CSS 在 `:2685-2743`，无白底/细边框/圆角10/hover 上浮）。而**能力市场卡片**（`market/components/MarketCard.vue:87-204`）是白底 `--el-fill-color-blank` + 边框 `--el-border-color-lighter` + 圆角 10 + hover 上浮阴影 + `IconTile` 真实图标 + 名称/标签 + 两行描述 + 底部分隔线统计，风格「清新」。
2. **智能体对话「最丑陋，没有之一；无流式打字机、无思考/工具调用过程」**：`agent/index.vue` 内嵌对话（模板 `:321-356`）用**手写** `readAgnoFrames` + `handleChatEvent` 维护 `chatMsgs`，渲染为平铺气泡 + 一次性展示的「思考过程/执行链」简单 div，无打字机光标、无可折叠思考、无工具时间线。

## 设计决策

- **卡片图标**：生成真实智能体图标（复用 `gen_skillhub_icons.py` 的 `llm_derive`/`_normalize`/`_is_color`/`dedupe_pass`/`_shrink`/`STYLE`/`NEGATIVE`），输出到 `frontend/public/agent-icons/`，写回 `ai_agents.avatar` 字段；前端用 `IconTile` 渲染，需在 `IconTile.isImage` 增加 `agent-icons/` 前缀。
- **卡片视觉**：对齐 `MarketCard`（白底/细边框/圆角10/hover 上浮/两行描述/底部统计），用 `IconTile` 替换首字母头像；保留启用/停用、批量选择与操作但布局归入卡片头/脚。
- **对话消息区**：保留既有 `readAgnoFrames` 流式链路（后端已吐 Agno 事件），仅**重做消息区渲染**——复用 `chat/components/ReasoningBlock.vue`（可折叠思考 + 流式光标）与 `ToolCallTimeline.vue`（实时工具时间线），正文加打字机光标 `.cursor-typing`，气泡/配色对齐市场卡片「清新」风。
- **流式修复**：确保 agent `run/stream` 响应头含 `Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no` + `Content-Encoding: identity`（防代理/中间件缓冲 SSE），并核查 `readAgnoFrames` 解析正常。
- **图标数据源**：`AiAgentModel.agent_name/agent_role/capabilities/category` 用于派生 `(symbol,bg)`；图标命名 `<agent_id>.png`。

## 改动清单

### ① 智能体图标生成
- 新建 `backend/scripts/gen_agent_icons.py`：借鉴 `gen_skillhub_icons.py`，从 `AiAgentModel` 读取带 `avatar` 为空/需生成的智能体，派生→出图→写 `frontend/public/agent-icons/<agent_id>.png`→回写 `ai_agents.avatar`。
- 运行：`cd backend && .venv/Scripts/python.exe scripts/gen_agent_icons.py --concurrency 2`。

### ② 卡片视觉对齐 MarketCard（`agent/index.vue`）
- 模板 `:103-207`：`.agent-avatar`（首字母圆）→ `<IconTile :item="{ icon: a.avatar, asset_type: 'agent' }" />`；卡片头去掉全选框改放右上角（或保留但弱化）；描述区两行省略；底部加统计/操作。
- 样式 `:2685-2743`：`.agent-card` 加 `background:var(--el-fill-color-blank); border:1px solid var(--el-border-color-lighter); border-radius:10px;` + hover `box-shadow + translateY(-2px)`（对齐 `MarketCard.vue:87-106`）；新增 `.agent-card__desc` 两行省略、`.agent-card__foot` 底部分隔线。
- `IconTile.vue`：`isImage`（`:39-46`）增加 `agent-icons/` 前缀支持。

### ③ 对话消息区重做（`agent/index.vue`）
- 模板 `:321-356`：user 气泡/数据不变；assistant 用 `ReasoningBlock(:text=m.think,:streaming=m.loading)` 展示思考，用 `ToolCallTimeline(:parts=buildToolParts(m.tools))` 展示工具链，正文 `renderMd(m.content)` 后加流式光标 `.cursor-typing`。
- 新增 `buildToolParts(tools:string[])`：把 `m.tools`（`string[]`）转成 `AiUIPart[]`（`{type:'tool-'+name, toolName:name, state:'output-available'}`），供 `ToolCallTimeline`。
- 样式：气泡/思考/工具/正文复用 `chat/components/MessageItem.vue`、`ReasoningBlock.vue`、`ToolCallTimeline.vue` 的配色（`--el-*` 变量），正文打字机光标用 `.cursor-typing`（`MessageItem.vue:216-218,333-341`）。
- 流式保护：核实 `agno_stream_response` 头已含 no-transform；确保用到。

## 测试

- 后端：无新增单测（纯前端+脚本）。图标脚本可用少量智能体试点（`--only`）确认输出并回写 `avatar`。
- 前端：`pnpm run type-check` + `pnpm exec eslint` 相关文件；无头浏览器截图核验：
  - 智能体中心卡片对齐 MarketCard（白底/圆角/hover/真实图标/两行描述）。
  - 智能体对话：流式打字机光标、可折叠「思考中」、实时工具时间线。

## 非目标
- 不改后端 agent 运行逻辑（`run_ui_stream`/`run_agno_tool_stream`）事件结构。
- 不引入 `useAiChat` 重构（保留 `readAgnoFrames`，只重做渲染；降低风险、行为不变）。
- 不动「AI 智能助手」功能。
