# 用 AgentSurface 替换对话界面 · 实施计划

> 状态（2026-11-16）：任务 1~8 已完成并逐项验证；任务 9 的自动化验收（金路径/后端冒烟）通过，
> 文档已更新（AGENTS + 用户手册）。工作流编辑器与 embed 按设计不在范围。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AIStation 的对话界面（悬浮助手、工作空间、应用、智能问数）统一换成 `agent-surface` 组件，保留后端协议与数据链路。

**Architecture:** 新增一层 `AgentTransport` 适配器，把 agno 事件与问数流映射为 AgentSurface 的 `AgentEvent`；页面只负责把自身的会话/反馈/执行详情接到事件上。会话列表、权限、持久化仍用 AIStation 自己的实现。

**Tech Stack:** Vue 3.5 + TypeScript + Element Plus（宿主）；`agent-surface`（本地包 `D:/AgentSurface/packages/agent-surface`，已构建 dist）；Vitest（已有 `frontend` 测试基建）。

**Spec:** `docs/superpowers/specs/2026-11-16-agent-surface-replace-chat-design.md`

## Global Constraints

- **不改后端协议**：agno 事件字段、问数 `ask/stream` 的 `sql/rows/took_ms/path/metric` 一个都不改，只在前端映射。
- **工作流编排画布不动**（`WorkflowEditor` 的节点/连线、`node-status`/`data-run` 帧）。
- **会话列表继续用 AIStation**（`SessionSidebar`）；AgentSurface 只负责对话区。
- **灰度开关**：系统参数 `ai_chat_surface`，取值 `legacy`（默认）/ `surface`；每批必须可一键回退。
- **每批独立提交**，提交信息 `feat(chat): 中文描述`。
- 样式：`agent-surface` 的 token 全部挂在 `.as-root` 作用域（已核实），引入后**不得**出现全局变量污染（Task 1 用截图与计算样式验证）。

## Review Focus

- **流中断/取消**：没有 `RunCompleted` 就断开时，消息必须收尾（不能永远 `streaming`）。
- **工具调用异常**：未知工具名、`ToolCallCompleted` 带 error 时，`ToolPart` 必须是 `error` 且保留 error 文案。
- **历史回放**：含 reasoning / tool parts 的旧会话回放后，正文与工具状态必须与当时一致。
- **问数错误路径**：无 SQL（`SQL 校验失败`）或 0 行时，界面必须显示错误/空态，而不是空白 surface。
- **权限拒绝**：受限账号在对话里问敏感表时，必须显示拒绝原因（不能静默失败或显示旧结果）。

---

## 任务 1：接入依赖与样式隔离基座

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/composables/ai/surface/surfaceStyles.ts`
- Test: `frontend/src/composables/ai/surface/__tests__/surfaceStyles.test.ts`

**Interfaces:**
- Produces: `SURFACE_STYLE_IMPORT: string`（`'agent-surface/style.css'`）、`surfacePropsDefaults(): { theme: 'light'; palette: 'paper'; locale: 'zh-CN'; showReasoning: true; showToolCalls: true }`

- [ ] **Step 1: 构建本地包并加依赖**

```bash
cd D:/AgentSurface/packages/agent-surface && npm run build
cd D:/AIStation/frontend && pnpm add "agent-surface@file:../../AgentSurface/packages/agent-surface"
```

预期：`frontend/node_modules/agent-surface/dist/agent-surface.js` 存在。

- [ ] **Step 2: 写失败测试（默认 props）**

```ts
import { describe, expect, it } from "vitest";
import { surfacePropsDefaults, SURFACE_STYLE_IMPORT } from "../surfaceStyles";

describe("surface 基座", () => {
  it("默认中文 + 纸色 + 显示思考与工具", () => {
    expect(surfacePropsDefaults()).toEqual({
      theme: "light", palette: "paper", locale: "zh-CN",
      showReasoning: true, showToolCalls: true,
    });
    expect(SURFACE_STYLE_IMPORT).toBe("agent-surface/style.css");
  });
});
```

- [ ] **Step 3: 运行确认失败**

`cd frontend && npx vitest run src/composables/ai/surface/__tests__/surfaceStyles.test.ts`
预期：Cannot find module '../surfaceStyles'。

- [ ] **Step 4: 实现**

`surfaceStyles.ts` 导出上述常量与函数（纯常量，不含副作用）。

- [ ] **Step 5: 运行确认通过 + 全站样式未被污染**

跑测试通过；然后无头浏览器打开任意旧页面，`getComputedStyle(document.body).getPropertyValue('--as-bg')` 必须为空（token 未泄露到 `:root`）。

- [ ] **Step 6: 提交**

`feat(chat): 引入 agent-surface 与样式基座`

---

## 任务 2：agno 事件适配器（核心）

**Files:**
- Create: `frontend/src/composables/ai/surface/agnoSurfaceTransport.ts`
- Test: `frontend/src/composables/ai/surface/__tests__/agnoSurfaceTransport.test.ts`

**Interfaces:**
- Produces: `mapAgnoFrame(event: string, data: unknown, ctx: MapCtx): AgentEvent[]`；`class AgnoSurfaceTransport implements AgentTransport { constructor(opts: { path: string; buildBody?: () => Record<string, unknown> }) ; stream(input: SendInput, opts?: { signal?: AbortSignal }): AsyncIterable<AgentEvent> }`
- `MapCtx = { messageId: string; runId: string; reasoningOpen: boolean; textOpen: boolean }`

- [ ] **Step 1: 写失败测试（6 条映射）**

```ts
// RunStarted → run.started；RunContent → text.delta；ReasoningContentDelta → reasoning.delta
// ToolCallStarted → tool.start；ToolCallCompleted(error) → tool.end{status:"error"} 保留 error
// RunCompleted → run.done{status:"done"}；RunError → run.done{status:"error"}
// 流中断（无 RunCompleted）时 flush(ctx) 必须补 run.done{status:"stopped"}
```

- [ ] **Step 2: 运行确认失败**

`npx vitest run src/composables/ai/surface/__tests__/agnoSurfaceTransport.test.ts`

- [ ] **Step 3: 实现**

复用现有 `parseAgnoFrame`（`composables/ai/agnoChatTransport.ts` 已导出）解析帧；`stream()` 用 `fetch` + `response.body` 逐帧产出；`finally` 里调用 `flush()`。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交** `feat(chat): agno 事件适配器`

---

## 任务 3：历史消息映射（UIMessage → ChatMessage）

**Files:**
- Create: `frontend/src/composables/ai/surface/messageMap.ts`
- Test: `frontend/src/composables/ai/surface/__tests__/messageMap.test.ts`

**Interfaces:**
- Produces: `toChatMessages(messages: UIMessage[]): ChatMessage[]`；`toUiMessages(messages: ChatMessage[]): UIMessage[]`（回写持久化用）

- [ ] **Step 1: 写失败测试**：user 文本 → `role:"user"` + 1 个 text part；assistant 的 reasoning/text/tool parts 按序映射；tool 状态 `input-available|output-available|output-error` → `running|done|error`；未知 part 丢弃但不抛错。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现**（纯函数，不引组件）
- [ ] **Step 4: 运行确认通过**；**Step 5 提交** `feat(chat): 对话消息双向映射`

---

## 任务 4：悬浮助手切换（含灰度开关）

**Files:**
- Modify: `frontend/src/components/AiAssistant/index.vue`
- Modify: `frontend/src/main.ts`（注册系统参数读取或复用现有 settings 读取工具）
- Test: 手动 + `frontend/scripts/golden_path.mjs`（不应回归）

**Interfaces:**
- Consumes: `AgnoSurfaceTransport`（Task 2）、`toChatMessages`（Task 3）
- Produces: 无（页面内部）

- [ ] **Step 1: 读取开关**：`ai_chat_surface !== 'surface'` 时渲染旧组件（原样保留），否则渲染 `<AgentSurface>`。
- [ ] **Step 2: 接线**
  - `sessionId` = 当前对话 id；`initialMessages` = `toChatMessages(chat.messages)`
  - `feedback` 事件 → 现有 `feedback` 提交接口；`update:messages` → 回写 `chat.setMessages(toUiMessages(...))`
- [ ] **Step 3: 验证**：连续 5 轮（含一次工具调用、一次停止、一次反馈）；切回 `legacy` 旧 UI 正常。
- [ ] **Step 4: 提交** `feat(chat): 悬浮助手切 agent-surface（可回退）`

---

## 任务 5：工作空间对话切换

**Files:**
- Modify: `frontend/src/views/module_ai/workspace/chat.vue`

**Interfaces:** 同 Task 4；`path` 按 `agent|app` 取 `/ai/agents/{id}/run/stream` 或 `/ai/apps/{id}/run/stream`

- [ ] **Step 1:** 用同一开关切换；`buildBody` 传入 `session_id` 等现有参数。
- [ ] **Step 2:** 历史会话切换时 `reset(toChatMessages(history))`。
- [ ] **Step 3:** 验证 agent / app 两种入口各 3 轮，历史来回切 3 次不串会话。
- [ ] **Step 4:** 提交 `feat(chat): 工作空间对话切 agent-surface`

---

## 任务 6：应用对话切换

**Files:**
- Modify: `frontend/src/views/module_ai/app/index.vue`

- [ ] **Step 1:** 用 `AgnoSurfaceTransport` 替换手写 SSE（保留 401/403 提示）。
- [ ] **Step 2:** 验证工具调用与 `run.done{status:"error"}` 有可见错误条。
- [ ] **Step 3:** 提交 `feat(chat): 应用对话切 agent-surface`

---

## 任务 7：问数结果 → surface 节点

**Files:**
- Create: `frontend/src/composables/ai/surface/querySurface.ts`
- Test: `frontend/src/composables/ai/surface/__tests__/querySurface.test.ts`

**Interfaces:**
- Produces: `buildQuerySurface(msg: { sql?: string; rows?: unknown[]; columns?: string[]; path?: string; metric?: { name?: string }; cached?: boolean; took_ms?: number; error?: string }): SurfaceNode[]`
  规则：有 `error` → 只出 `callout{tone:"error"}`；有 `sql` → `code{lang:"sql"}`；有 `rows` → `table`；`path/metric/cached` → `badges`；`took_ms` → `stat`。

- [ ] **Step 1: 写失败测试**：四条（正常/sql 无 rows/error/0 行）各断言节点类型序列。
- [ ] **Step 2: 运行确认失败**  **Step 3: 实现**  **Step 4: 运行确认通过**
- [ ] **Step 5: 提交** `feat(query): 问数结果 surface 构建器`

---

## 任务 8：智能问数页接入

**Files:**
- Modify: `frontend/src/views/module_ai/query/index.vue`
- Modify: `frontend/src/api/module_ai/query.ts`（新增 `QuerySurfaceTransport`：把 `/ask/stream` 的既有事件转 `AgentEvent` + `surface`）

- [ ] **Step 1:** 新增 `QuerySurfaceTransport.stream()`：沿用现有 SSE 解析（`ask/stream` 的 `reasoning/delta/sql/rows/done` 字段），产出 text.delta 与 `surface`（用 Task 7）。
- [ ] **Step 2:** 问数页在开关为 `surface` 时用 `<AgentSurface>` 渲染；`action` 事件映射：`执行详情`/`存为报表`/`沉淀指标` 调既有函数。
- [ ] **Step 3:** 验证：金路径脚本 + 抽 5 题比对（SQL、行数、耗时、路径标签一致）；错误题（SQL 校验失败）显示错误条。
- [ ] **Step 4:** 提交 `feat(query): 智能问数切 agent-surface（surface 承载 SQL/表格）`

---

## 任务 9：全量验收与文档

- [ ] `frontend/scripts/golden_path.mjs`、`backend/scripts/query_golden_smoke.py` 全通过
- [ ] 6 个入口手动走查清单（工具、停止、重试、反馈、附件、历史回放）
- [ ] 权限：受限账号问敏感表必须被拒
- [ ] 开关切回 `legacy` 全站正常
- [ ] 更新 `docs/query-user-manual.md` 与 `AGENTS.md`（对话 UI 说明）
- [ ] 提交 `docs(chat): 对话 UI 切换说明与验收记录`
