# 智能体中心卡片 + 对话界面重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把智能体中心卡片对齐「能力市场」卡片风格（白底细边框圆角10 + hover 上浮 + 真实图标 + 两行描述 + 底部统计），并重做智能体对话消息区（流式打字机光标 + 可折叠思考块 + 实时工具时间线，配色清新）。

**Architecture:** 前端 `agent/index.vue` 卡片与内嵌对话消息区重做 + `IconTile.vue` 支持 agent 图标前缀；新建 `gen_agent_icons.py` 为智能体生成真实图标并回写 `ai_agents.avatar`。保留现有 `readAgnoFrames` 流式链路，仅重做渲染。

**Tech Stack:** Vue3 + Element Plus（前端）、Python + Qwen/284B（图标生成）、pytest（回归）。

**Spec:** `docs/superpowers/specs/2026-10-16-agent-center-and-chat-ui-redesign.md`

## Global Constraints

- 前端只用 Element Plus 组件与 `--el-*` 变量，禁止自定义 font-size，风格与市场卡片一致；不引入 `useAiChat` 重构（保留 `readAgnoFrames`）。
- 注释/提交信息中文；提交格式 `feat(agent): 中文描述`；精确 `git add`（禁用 `-A`）。
- 图标生成脚本走国内 Qwen 网关（`http://llm.bsh-tech.com:8086/v1`，`smbs/Image-2.1`），派生用 `smbs/LLM-284B-MXFP4`。
- 前端改动后跑 `pnpm run type-check` + `pnpm exec eslint`；用无头浏览器截图核验。

## Review Focus

- 卡片在无 `avatar`（未生成图标）时应优雅回退（显示首字母磁贴而非裂图）。
- `IconTile` 对 `agent-icons/...` 路径要能识别并渲染 `img`；`market-icons/...` 行为不变。
- 工具时间线 `ToolCallTimeline` 需要 `AiUIPart[]`，agent 的 `m.tools: string[]` 必须正确转换；空工具时该块不渲染。
- 流式正文在 `m.loading` 时显示打字机光标，结束后光标消失。
- 思考块 `ReasoningBlock` 在 `streaming` 时自动展开、完成后收起为摘要。

---

### Task 1: 生成智能体真实图标（Spec ①）

**Files:**
- Create: `backend/scripts/gen_agent_icons.py`
- Output: `frontend/public/agent-icons/<id>.png`（运行时写）
- Data: 回写 `backend` 库 `ai_agents.avatar`

**Interfaces:**
- Consumes: `AiAgentModel`（`agent_name`/`agent_role`/`capabilities`/`category_id`）从 `ai_agents` 表读取；借用 `gen_skillhub_icons.py` 的 `llm_derive`/`_normalize`/`_is_color`/`dedupe_pass`/`_shrink`/`STYLE`/`NEGATIVE`。
- Produces: `<agent_id>.png` 写入 `frontend/public/agent-icons/`，并 `UPDATE ai_agents SET avatar='agent-icons/<id>.png'`。
- 环境：`PYTHONPATH` 指向 `backend`，import `app.plugin.module_ai.agent.model.AiAgentModel`；直连 dev 库（psycopg3）。

- [ ] **Step 1: 写脚本（借鉴 gen_skillhub_icons.py）**

复制 `gen_skillhub_icons.py` 的派生/绘图/去重/缩图函数；数据源改为查 `ai_agents`（`avatar` 为空或需生成）；`--only <id,id>` 试点；输出目录 `frontend/public/agent-icons/`；生成后 `UPDATE ai_agents SET avatar=...`。

- [ ] **Step 2: 试点运行确认输出 + 回写**

Run: `cd backend && .venv\Scripts\python.exe scripts/gen_agent_icons.py --only 1 --concurrency 1`
Expected: `frontend/public/agent-icons/1.png` 生成；`ai_agents` id=1 的 `avatar='agent-icons/1.png'`。

- [ ] **Step 3: 全量生成**

Run: `cd backend && .venv\Scripts\python.exe scripts/gen_agent_icons.py --concurrency 2`

- [ ] **Step 4: 提交**

```bash
cd D:\AIStation
git add backend/scripts/gen_agent_icons.py frontend/public/agent-icons
git commit -m "feat(agent): 为智能体生成真实、各不相同、契合的图标并回写 avatar"
```

---

### Task 2: 卡片视觉对齐 MarketCard（Spec ②）

**Files:**
- Modify: `frontend/src/views/module_ai/market/components/IconTile.vue:39-46`（`isImage` 支持 `agent-icons/`）
- Modify: `frontend/src/views/module_ai/agent/index.vue`（模板 `:103-207`、样式 `:2685-2743`）

**Interfaces:**
- Consumes: `a.avatar`、`IconTile`、`a.enabled`/`a.query_enabled`/`a.knowledge_ids`/`a.tool_ids`/`a.skill_ids`/`a.mcp_ids`/`a.model_id`/`a.prompt_id`/`a.workflow_id`。
- Produces: 无新接口；卡片展示用 `<IconTile :item="{ icon: a.avatar, asset_type: 'agent' }" />`。

- [ ] **Step 1: `IconTile.vue` 支持 `agent-icons/`**

在 `isImage`（`:39-46`）把图标路径以 `market-icons/` 或 `agent-icons/` 开头判定为 `img`；`src` 前缀拼接复用现有逻辑。

- [ ] **Step 2: 改 `agent/index.vue` 卡片模板 + 样式**

模板 `.agent-avatar`（`:110-112`）改为 `<IconTile :item="{ icon: a.avatar, asset_type: 'agent' }" />`（无 avatar 时 `IconTile` 回退首字母磁贴）；卡片头右下角保留全选框（或移至工具条），描述区 `:120` 改 `.agent-card__desc` 两行省略；`:162-206` 操作按钮收敛为卡片脚部图标/按钮。样式 `.agent-card`（`:2685`）加入 MarketCard 的白底/细边框/圆角10/hover 上浮阴影（对齐 `MarketCard.vue:87-106`），新增 `.agent-card__desc`（两行 clamp）与 `.agent-card__foot`（顶部分隔线统计）。

- [ ] **Step 3: 前端校验 + 无头浏览器核验**

Run: `cd frontend && pnpm run type-check && pnpm exec eslint src/views/module_ai/agent/index.vue src/views/module_ai/market/components/IconTile.vue`
浏览器截图对照市场卡片：白底圆角、真实图标、两行描述、hover 上浮。

- [ ] **Step 4: 提交**

```bash
cd D:\AIStation
git add frontend/src/views/module_ai/agent/index.vue frontend/src/views/module_ai/market/components/IconTile.vue
git commit -m "feat(agent): 智能体中心卡片对齐能力市场卡片风格并展示真实图标"
```

---

### Task 3: 对话消息区重做（Spec ③）

**Files:**
- Modify: `frontend/src/views/module_ai/agent/index.vue`（模板 `:321-356`、样式 `:2279-2400` 区）
- Reuse: `chat/components/ReasoningBlock.vue`、`chat/components/ToolCallTimeline.vue`

**Interfaces:**
- Consumes: `chatMsgs`（`{role,content,think,tools: string[],loading}`）、`renderMd`、`readAgnoFrames`。
- Produces: 新增 `buildToolParts(tools: string[]): AiUIPart[]`（`{type:'tool-'+name, toolName:name, state:'output-available'}`）；`ReasoningBlock(:text=m.think, :streaming=m.loading)`；`ToolCallTimeline(:parts=buildToolParts(m.tools))`。

- [ ] **Step 1: 引入组件 + 转换函数**

import `ReasoningBlock`/`ToolCallTimeline`；新增 `buildToolParts`。

- [ ] **Step 2: 改消息区模板**

assistant 气泡内：`<ReasoningBlock v-if="m.think" :text="m.think" :streaming="m.loading" />`、`<ToolCallTimeline v-if="buildToolParts(m.tools).length" :parts="buildToolParts(m.tools)" />`、正文 `v-html="renderMd(m.content)"` 后加 `<span v-if="m.loading" class="cursor-typing" />`。

- [ ] **Step 3: 样式**

正文区加 `.cursor-typing`（复用 `MessageItem.vue:216-218,333-341` 的闪烁光标）；气泡/间距 `--el-*` 对齐；移除旧的 `.agent-chat-think`/`.agent-chat-tools` 平铺块样式。

- [ ] **Step 4: 前端校验 + 无头浏览器核验**

Run: `cd frontend && pnpm run type-check && pnpm exec eslint src/views/module_ai/agent/index.vue`
浏览器：进入智能体对话发送问题，确认正文流式光标、思考块「思考中」可折叠、工具时间线实时出现。

- [ ] **Step 5: 提交**

```bash
cd D:\AIStation
git add frontend/src/views/module_ai/agent/index.vue
git commit -m "feat(agent): 智能体对话消息区重做为流式打字机+可折叠思考+实时工具时间线"
```

---

## 收尾

- 后端回归：`cd backend && .venv\Scripts\python.exe -m pytest tests/test_agent_binding_validation.py tests/test_agent_market.py -q`。
- 前端：`pnpm run type-check && pnpm run lint`。
- 无头浏览器：智能体中心卡片风格对齐 + 对话流式/思考/工具时间线截图核验。
