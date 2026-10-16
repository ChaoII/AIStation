# AI 对话 V2 · Vercel AI SDK 迁移设计

- 日期：2026-10-16
- 范围：前端 AI 对话 / 全局 AI 助手重建
- 目标：把 AI 聊天从「手写 SSE 解析」迁移到 Vercel AI SDK（`ai` + `@ai-sdk/vue` 的 `useChat`），并重做消息呈现层，实现流式打字机、思维过程可视化、Agent 工具调用时间线、富文本、输入现代化与会话管理的惊艳交互。

## 1. 背景与现状

当前前端 AI 聊天存在三层问题：

1. **手写流解析**：`composables/ai/useAiChat.ts` 用 `fetch + ReadableStream` 手解析 Agno 原生 SSE（`event: RunContent` 等），自行管理消息/状态/中止，工作量大且易错。
2. **消息模型割裂**：`useAiChat` 产出 `UiMessage`（`parts[]`），但 `views/module_ai/chat/components/MessageItem.vue` 渲染的是另一套 `ChatMessage`（`content/think/sources`）。调用方 `components/AiAssistant/index.vue` 通过 `composables/ai/uiMessage.ts` 的 `textOf/reasoningOf/toolPartsOf/sourcesOf/dataPartsOf` 做映射，并**丢弃工具详情**（只保留一行 `> 🔧 调用工具：name`）。
3. **呈现单调**：无逐 token 流式打字机、无工具调用可视化、无推理过程交互、无会话管理、无输入现代化。

后端 `/ai/assistant/stream`（以及 `/agents/{id}/run/stream`、`/apps/{id}/run/stream`）**直出 Agno 原生事件流**：`RunStarted / RunContent / ReasoningContentDelta / ToolCallStarted / ToolCallCompleted / RunCompleted / RunError`。事件信息完整，是做出惊艳效果的原料。

`ai ^7.0.99` 与 `@ai-sdk/vue ^4.0.99` 已在依赖中，迁移条件成熟。

## 2. 架构分层

```
┌─ UI 呈现层  views/module_ai/chat/*  +  components/AiAssistant/*（重构/新建）
│     ChatMessages · MessageItem · ToolCallTimeline · ReasoningBlock · RichContent
│     ChatInput(CodeMirror + @菜单 + 附件 + chips) · WelcomeScreen · SessionSidebar
├─ 状态层  @ai-sdk/vue useChat({ transport, messages, onError, onFinish, onToolCall })
│     托管 messages / status / error / 流式 parts 组装 / stop / regenerate
├─ 传输层  composables/ai/agnoChatTransport.ts
│     AgnoChatTransport implements ChatTransport  → 输出 ReadableStream<UIMessageChunk>
└─ 后端（零改动） /ai/assistant/stream · /agents|apps/{id}/run/stream
       直出 Agno 原生 SSE
```

数据流：`ChatInput` → `useChat.sendMessage` → `AgnoChatTransport.sendMessages` 把历史 `UIMessage[]` 转录为后端 `{role, parts:[{type:'text',text}]}`（+会话/模型参数）→ `fetch` 后端 Agno 流 → 逐帧转 `UIMessageChunk` 入 `ReadableStream` → `useChat` 组装进 `messages`（part 级增量）→ UI 响应式渲染。

## 3. 传输层 `AgnoChatTransport`

`ChatTransport.sendMessages({ messages, chatId, messageId, abortSignal, trigger, ... })` 返回 `Promise<ReadableStream<UIMessageChunk>>`。逐帧映射：

| Agno 事件 | 输出 chunk |
|---|---|
| `RunStarted` | `{type:'start-step'}` |
| `RunContent`（content 字符串） | 首帧 `text-start`(id)，随后 `text-delta`，收尾 `text-end` |
| `ReasoningContentDelta` | 首帧 `reasoning-start`(id)，随后 `reasoning-delta`，收尾 `reasoning-end` |
| `ToolCallStarted` | `tool-input-available`(toolCallId/toolName/input) |
| `ToolCallCompleted` | `tool-output-available`(toolCallId/output) |
| `RunError` / `error` | `{type:'error', errorText}` |
| `RunCompleted` | `finish-step` 后关闭流 |

要点：
- **part id**：`text-start`/`reasoning-start` 用固定 id（如 `${messageId}-text` / `${messageId}-reasoning`）；`tool-input/tool-output` 用后端 `tool_call_id`，缺失时按 `toolName+序号` 生成，保证成对。
- **请求体**：从 `sendMessages` 的 `messages` 取 `UIMessage[]`，仅保留 text part 转给后端（对齐现状 `payloadMessages`）；`body` 透传会话/模型参数。
- **鉴权**：`fetch` 带 `Authorization: Bearer <token>`（`Auth.getAccessToken()`）并保留 `X-Forwarded-For: 127.0.0.1` 头。
- **边界**：`abortSignal` 贯穿；帧 JSON 解析失败仅跳过；`text-start` 后直接 `error` 也能被 `useChat` 捕获；`regenerate` 对应 `trigger:'regenerate-message'`。
- **复用**：`AgnoChatTransport` 以「路径 + 请求体构造函数」参数化，可服务 `/assistant/stream`、`/agents|apps/{id}/run/stream`。

## 4. UI 呈现层（A–E）

### A 流式打字机 + 思维过程
- `text-part` 增量驱动；流式时文本末尾渲染闪烁光标（CSS 动画）；`transition` 平滑高度/不透明度。
- `reasoning-part` 渲染为可折叠「思考」块：流式时图标+「思考中…」+增量滚动，完成后自动收起为一行摘要，点击展开/收起（高度过渡动画）。

### B Agent 工具调用时间线（核心亮点）
- `tool` parts（`toolName/toolCallId/state/input/output/errorText`）渲染为**垂直状态时间线**：工具图标、工具名、状态徽标（进行中 spinner / 成功✓ / 失败✗，`el-tag`/`el-icon`）、输入/输出 `vue-json-pretty`（已有依赖）或 CodeMirror JSON 高亮、可折叠、显示耗时差。
- 执行中显示 pulsate 动画；多个工具按出现顺序纵向排列。

### C 富文本呈现
- 复用 `markdown-it` + `highlight.js` + `DOMPurify`：表格、代码块带「复制」与语言标签、图片/附件预览；`source-part` 渲染为引用来源卡片（标题/相似度）。
- 可选增强（后续评估引入）：`mermaid` 流程图、`katex` 公式、`vue-echarts` 图表（`echarts` 已有）。

### D 输入侧现代化
- `ChatInput` 用 `@codemirror/*`（已有）多行编辑：Enter 发送、Shift+Enter 换行、可拖高。
- `@` 触发命令菜单（`el-popover`+搜索）：列出工具/技能/提示词/知识库，选中即插入引用并高亮。
- 快捷指令 `chips`（`el-tag` 可点）快速填入常见问题。
- 文件/图片拖拽或点击上传：预览缩略图，作为附件 part 随消息发出；发送中可停止。

### E 会话管理
- 侧边栏（复用 `/sessions`）：会话列表、自动标题（首条消息）、重命名/删除/归档、搜索；点击切换并加载历史 `messages`（`ChatInit.messages`）；「新建会话」。
- 会话切换用 `useChat` 的 `id` 隔离，丝滑过渡。

## 5. 组件与文件清单

**新建**
- `composables/ai/agnoChatTransport.ts` — `AgnoChatTransport`
- `composables/ai/useAiChat.ts`（重写为 `useChat` 封装，保留 `sendMessage/stop/regenerate/messages/status/error` 签名兼容 `AiAssistant`）
- `views/module_ai/chat/components/ToolCallTimeline.vue`
- `views/module_ai/chat/components/ReasoningBlock.vue`
- `views/module_ai/chat/components/RichContent.vue`（markdown 渲染封装）
- `views/module_ai/chat/components/SessionSidebar.vue`

**重构**
- `views/module_ai/chat/components/ChatMessages.vue`、`MessageItem.vue`（按 part 渲染）、`ChatInput.vue`（CodeMirror + @ 菜单 + 附件 + chips）
- `composables/ai/uiMessage.ts`（扩展：按 `state` 分类 tool parts、耗时等）

风格约束：仅用 Element Plus 组件与 `--el-*` 变量；编辑器/构造器用成熟第三方组件；不造主题化外壳；完成后无头浏览器截图 + 多模态读图核对与既有页面一致。

## 6. 错误与边界

- `useChat` 捕获 `error` part → 列表顶部 `el-alert` 可关闭；流中断/Abort 恢复 status；无模型/会话创建失败降级不阻断。
- 聊天区自适应滚动到底；长消息折叠；超多消息用成熟虚拟滚动方案。
- 会话切换时保留各会话隔离状态。

## 7. 测试与验收

- 纯逻辑单测：`agnoChatTransport` 的 Agno 事件 → `UIMessageChunk` 映射（快速模式，`PYTEST_NO_APP` 不适用，属前端 vitest）。
- 前端 `vitest` 单测覆盖 transport 映射与 `uiMessage` 提取。
- 验收：无头浏览器截图 + 多模态读图，与 `module_system/param` 等既有页面风格一致；A/B/C/D/E 各截一张核对。
- `pnpm run type-check`、`pnpm run lint`（仅改动的前端文件）、`vitest run` 通过。

## 8. 范围外（YAGNI，后续）

- Agent/App 运行台前端改造（本设计只提供可复用的 `AgnoChatTransport`，运行台可后续接入）。
- mermaid/katex/echarts 图表增强（本设计仅留扩展点）。
- 语音输入/朗读（本设计不引入 Web Speech API 依赖注入）。
