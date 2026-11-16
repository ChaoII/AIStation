# 用 AgentSurface 替换 AIStation 对话界面 · 设计

日期：2026-11-16
状态：待评审

## 1. 目标

把 AIStation 的**对话类界面**统一换成 `D:/AgentSurface` 的 `packages/agent-surface`（Vue 3 组件），
保留 AIStation 的后端（会话、反馈、持久化、权限、问数执行链路），**只替换前端渲染与流式状态层**。

非目标（本次不做）：
- 工作流**编排画布**（`WorkflowEditor` 的节点/连线）——它是编排器，不是对话。
- 对外 embed 页（`embedChatTransport`）——批 4 之后再复用同一适配层。
- 后端协议本身（不改 agno 事件、不改问数 `ask/stream` 的字段）。

## 2. 现状：6 个对话入口、3 种协议

| 入口 | 文件 | 协议 | 现有实现 |
|---|---|---|---|
| 全局悬浮助手 | `components/AiAssistant/index.vue` | agno 事件（`/ai/assistant/stream`） | `useAiChat` + `AgnoChatTransport` |
| 个人工作空间对话 | `views/module_ai/workspace/chat.vue` | agno 事件（`/ai/agents/{id}/run/stream`、`/ai/apps/{id}/run/stream`） | 同上 |
| 应用对话 | `views/module_ai/app/index.vue` | agno 事件（手写 fetch + SSE 解析） | 手写 |
| 智能问数 | `views/module_ai/query/index.vue` + `api/module_ai/query.ts` | 自定义（`/ai/query/ask/stream`，带 sql/rows/took_ms/metric） | 手写 |
| 工作流调试/运行 | `views/module_ai/workflow/components/WorkflowEditor.vue` | AI SDK UI Message Stream（`node-status`/`data-run`） | 保留（非目标） |
| 对外嵌入 | `views/module_ai/embed/*` | agno 事件（`embedChatTransport`） | 保留（后续复用适配层） |

消息模型差异：
- AIStation：Vercel AI SDK `UIMessage[]`
- AgentSurface：`ChatMessage[]`（parts：`reasoning` / `tool` / `text` / `surface`）

## 3. 目标架构

```
页面（6 个入口）
   └─ <AgentSurface>  ← 统一外壳：会话、思考、工具、附件、审批、压缩、反馈
          └─ AgentTransport（我们实现）
                 ├─ AgnoAgentTransport      ：agno 事件 → AgentEvent
                 ├─ QueryAgentTransport     ：问数流 → AgentEvent + surface 节点
                 └─ (Batch4) EmbedAgentTransport
```

### 3.1 事件映射（agno → AgentEvent）

| AIStation / agno | AgentSurface |
|---|---|
| `RunStarted` | `run.started`（messageId/runId） |
| `ReasoningContentDelta` | `reasoning.delta`；首个 delta 前补 `reasoning` part |
| `RunContent` | `text.delta` |
| `ToolCallStarted` | `tool.start`（id/name/args） |
| `ToolCallCompleted` | `tool.end`（status done/error + result） |
| `RunError` | `run.done {status:"error", error}` |
| `RunCompleted` | `run.done {status:"done", usage}` |
| 前端 `stop()` | `run.done {status:"stopped"}` |

### 3.2 问数的 surface 映射（关键，不能丢信息）

| 问数结果字段 | 渲染为 |
|---|---|
| `sql` | `SurfaceCode{lang:"sql"}`（已内置复制/高亮） |
| `rows` / `columns` | `SurfaceTable` |
| `path`（快路径/慢路径）、`metric`、`cached` | `SurfaceBadge` + `SurfaceKeyValue` |
| `took_ms`、`error` | `SurfaceStat` / `SurfaceCallout{tone:"error"}` |
| 现有「执行详情」弹窗 | 保留为 surface 内的按钮 action（`action` 事件回页面打开原弹窗） |
| 现有「反馈 / 更多（存报表/沉淀指标）」 | AgentSurface 的 `feedback` / `action` 事件 → 调原 AIStation API |

### 3.3 消息与历史

- 历史：`AIStation 会话消息 → ChatMessage[]`（assistant parts 从 `uiMessage.parts` 映射；工具调用映射为 `ToolPart`）。
- 新消息：AgentSurface 内部维护，`update:messages` 回写页面用于持久化。
- 会话列表：**继续用 AIStation 自己的**（`SessionSidebar`），AgentSurface 只负责对话区（`virtualize` 保留）。

## 4. 落地批次（每批独立可回滚）

| 批 | 内容 | 验收 |
|---|---|---|
| 1（约 1.5 天） | `AgnoAgentTransport` + 悬浮助手切 AgentSurface，新增开关 `ai_chat_surface=legacy\|surface`（系统管理 → 参数管理） | 悬浮助手连续 5 轮对话、工具调用、停止、反馈均正常；开关切回旧组件无异常 |
| 2（约 1 天） | 工作空间对话（agent/app 两种路径） | 同一 agent 在两个入口表现一致；历史会话可回放 |
| 3（约 0.5 天） | 应用对话 | 应用 run/stream 的工具与错误提示不丢 |
| 4（约 1.5~2 天） | 智能问数（surface：SQL/表/path/耗时/反馈/存报表/沉淀指标） | 问数金路径（`golden_path.mjs`）通过；执行详情与反馈行为与旧版一致；105 题抽 5 题结果一致 |

开关粒度：全局 **系统参数 `ai_chat_surface`**（`legacy` 默认，验证后改 `surface`；系统管理 → 参数管理）；页面级可加 `?surface=1` 便于对比。

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| AgentSurface 自带 `tokens.css/themes.css`，与 Element Plus 变量冲突 | 只在对话容器挂 `data-surface` 作用域；先做一页样式对比截图，确认不污染全局 |
| 问数信息被 surface 简化丢字段 | 4 批里字段映射表逐项对照，缺一个不改 |
| 会话/反馈 API 与 AgentSurface 事件语义不一致 | 事件适配层只做转发，不在组件里写业务；每个事件映射到现有 API 函数 |
| 工作流 HITL（`node-status`/`data-run`）误伤 | 工作流编辑器**不改**；如后续要换，单独立项 |
| 包体积 | `agent-surface` 按需引入；确认 gzip 增量 < 60KB，否则拆异步组件 |

## 6. 验收清单（全部换完后）

1. 6 个入口逐个手动走查（含工具调用、停止、重试、反馈、附件）。
2. `frontend/scripts/golden_path.mjs` 全通过；`backend/scripts/query_golden_smoke.py` 全通过。
3. 问数抽 5 题对比旧版：SQL、结果行数、耗时、路径标签一致。
4. 权限：受限账号在对话里问敏感表，仍被拒（对话 UI 不绕过权限）。
5. 关掉开关能回退到旧 UI，数据不受影响。
