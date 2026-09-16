# AI 管理 v2（AI SDK 流式 + 提示词/应用/工具/会话/日志）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把聊天/运行台迁移到 `@ai-sdk/vue` 的 `useChat` + 后端 AI SDK UI Message Stream 协议；随后完成提示词工作台（B）、工具中心（C1）、AI 应用（C2）、会话与日志（D）、报告增强与全量回归（E）。

**Architecture:** 后端在 `app/plugin/module_ai/` 下新增 `streaming.py` 统一产出 AI SDK UI Message Stream（SSE `data: {json}\n\n` + `[DONE]`）帧；`assistant` 与新的 `apps` 共用函数调用循环。新增 `prompts`/`tools`/`apps`/`sessions`/`logs` 子模块（自动发现，前缀 `/ai`）。前端统一用 Element Plus 组件与 `--el-*` 变量，流式统一走 `useChat`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2；`openai` 异步客户端；Vue 3 + Element Plus；`ai@7` + `@ai-sdk/vue@4`（已安装，勿新增依赖）；Playwright。

**Spec:** `docs/superpowers/specs/2026-09-13-ai-platform-v2-design.md`

## Global Constraints

- 后端：不新增依赖；`cd backend && uv run pytest -q` 全绿；新增/改动文件 `uv run ruff check` clean；中文注释。
- 前端：**不新增依赖**（`ai`/`@ai-sdk/vue`/`vuedraggable` 已装）；`pnpm type-check` 新增/改动文件 0 错误；目标文件 eslint/prettier clean。
- 视觉：AI 页面**只用 Element Plus 组件**（`el-card/el-descriptions/el-table/el-form/el-tag/el-statistic/el-row/el-col` 等）与 `--el-*` 变量，**禁止自定义主题化配色/指标卡外壳**；布局优先 `el-row/el-col`。
- AI SDK 协议常量（后端必须逐字匹配）：响应头 `content-type: text/event-stream`、`cache-control: no-cache`、`connection: keep-alive`、`x-vercel-ai-ui-message-stream: v1`、`x-accel-buffering: no`，另加 `Content-Encoding: identity`（跳过 GZip 缓冲）；帧为 `data: {json}` + 空行，结束 `data: [DONE]`。
- 提交信息 `feat(ai): 中文描述`；禁 `git add -A`，按任务列文件精确 add。
- 新表靠 `create_all` 创建：必须在 `app/scripts/initialize.py::__init_create_table` 显式 import 模型；新列（仅 `ai_call_logs.user_id`）加入 `app/scripts/init_app.py::_ensure_missing_columns`。
- 菜单/权限统一由 `app/scripts/init_app.py::_ensure_ai_menus()` 运行时补齐（改 `AI_BUTTON_PERMS` 与 `pages`）。
- 旧路由保留：`/ai/chat`、`/ai/memory`、`/ai/chat/ws` 不删；父菜单 redirect 维持现状（`/ai/chat`）。

### 关键协议参考（AI SDK UI Message Stream v1）

客户端 `useChat` 发送 `POST`，body 含 `{ id, messages: UIMessage[], trigger, messageId }`；后端只读 `messages`（每项 `{ id, role, parts: [{type:"text",text}, ...] }`）。后端需回：

```
data: {"type":"start","messageId":"<hex>"}
data: {"type":"reasoning-start","id":"<r>"}
data: {"type":"reasoning-delta","id":"<r>","delta":"..."}
data: {"type":"reasoning-end","id":"<r>"}
data: {"type":"text-start","id":"<t>"}
data: {"type":"text-delta","id":"<t>","delta":"..."}
data: {"type":"text-end","id":"<t>"}
data: {"type":"tool-input-available","toolCallId":"<c>","toolName":"navigate","input":{...},"dynamic":true}
data: {"type":"data-finish","data":{"reply":"...","tool_calls":[...],"action":{...}|null,"report_id":1|null}}
data: {"type":"error","errorText":"..."}
data: {"type":"finish"}
data: [DONE]
```

约束：`*-delta` 前必须有同 id 的 `*-start`；`tool-output-*` 前必须有同 `toolCallId` 的 `tool-input-available`；工具一律 `"dynamic": true`（客户端无需预注册），渲染为 `dynamic-tool` part；`data-finish` 承载旧的 `done` 语义（`action`/`report_id`/`tool_calls`），在 `finish` 之前发送。

---

### Task 1: 后端 UI Message Stream 协议 + 运行时按模型 + 调用日志修复

**Files:**
- Create: `backend/app/plugin/module_ai/streaming.py`
- Modify: `backend/app/plugin/module_ai/provider/service.py`（`get_runtime_model` 支持 `model_id`）
- Modify: `backend/app/plugin/module_ai/assistant/schema.py`（`AssistantUIStreamSchema`）
- Modify: `backend/app/plugin/module_ai/assistant/service.py`（改为 UI 流 + 消息提取）
- Modify: `backend/app/plugin/module_ai/assistant/controller.py`（`/stream` 改用 UI 协议）
- Modify: `backend/app/plugin/module_ai/overview/model.py`（新增 `user_id` 列）
- Modify: `backend/app/plugin/module_ai/overview/service.py`（修 `add_log` 的 `created_id` bug，写 `user_id`）
- Modify: `backend/app/scripts/init_app.py`（`_ensure_missing_columns` 增 `ai_call_logs.user_id`）
- Test: `backend/tests/test_ai_ui_stream.py`

**Interfaces:**
- Produces：
  - `streaming.UI_STREAM_HEADERS: dict`
  - `streaming.UiMessageStream`：`start(message_id=None)->str`、`reasoning(text)->str`、`reasoning_end()->str`、`text(text)->str`、`text_end()->str`、`tool(tool_call_id, name, args=None, output=None, error=None)->str`、`data(name, payload)->str`、`error(text)->str`、`finish()->str`、`done()->str`（静态）
  - `streaming.ui_stream_response(agen) -> StreamingResponse`
  - `assistant.service.extract_openai_messages(ui_messages: list[dict]) -> list[dict]`
  - `assistant.service.run_assistant_ui_stream(ui_messages: list[dict], auth) -> AsyncIterator[str]`
  - `AiModelService.get_runtime_model(usage=None, model_id=None) -> dict|None`

- [ ] **Step 1: 新建 `streaming.py`**

```python
"""AI SDK UI Message Stream（v1）SSE 输出工具。"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

UI_STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",
    # 让 GZipMiddleware 跳过压缩（否则 SSE 被缓冲，前端无法逐字）
    "Content-Encoding": "identity",
}


def _frame(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


class UiMessageStream:
    """按 AI SDK UI Message Stream v1 产出 SSE 帧；结束时发送 data: [DONE]。"""

    def __init__(self) -> None:
        self._text_id: str | None = None
        self._reason_id: str | None = None

    def start(self, message_id: str | None = None) -> str:
        return _frame({"type": "start", "messageId": message_id or uuid.uuid4().hex})

    def reasoning(self, text: str) -> str:
        if not text:
            return ""
        out = ""
        if self._reason_id is None:
            self._reason_id = uuid.uuid4().hex
            out += _frame({"type": "reasoning-start", "id": self._reason_id})
        out += _frame({"type": "reasoning-delta", "id": self._reason_id, "delta": text})
        return out

    def reasoning_end(self) -> str:
        if self._reason_id is None:
            return ""
        out = _frame({"type": "reasoning-end", "id": self._reason_id})
        self._reason_id = None
        return out

    def text(self, text: str) -> str:
        if not text:
            return ""
        out = ""
        if self._text_id is None:
            self._text_id = uuid.uuid4().hex
            out += _frame({"type": "text-start", "id": self._text_id})
        out += _frame({"type": "text-delta", "id": self._text_id, "delta": text})
        return out

    def text_end(self) -> str:
        if self._text_id is None:
            return ""
        out = _frame({"type": "text-end", "id": self._text_id})
        self._text_id = None
        return out

    def tool(
        self,
        tool_call_id: str,
        name: str,
        args: dict | None = None,
        output: object | None = None,
        error: str | None = None,
    ) -> str:
        out = ""
        if args is not None:
            out += _frame(
                {
                    "type": "tool-input-available",
                    "toolCallId": tool_call_id,
                    "toolName": name,
                    "input": args,
                    "dynamic": True,
                }
            )
        if error is not None:
            out += _frame(
                {
                    "type": "tool-output-error",
                    "toolCallId": tool_call_id,
                    "errorText": error,
                    "dynamic": True,
                }
            )
        else:
            out += _frame(
                {
                    "type": "tool-output-available",
                    "toolCallId": tool_call_id,
                    "output": output,
                    "dynamic": True,
                }
            )
        return out

    def error(self, text: str) -> str:
        return _frame({"type": "error", "errorText": text})

    def data(self, name: str, payload: object) -> str:
        return _frame({"type": f"data-{name}", "data": payload})

    def finish(self) -> str:
        return _frame({"type": "finish"})

    @staticmethod
    def done() -> str:
        return "data: [DONE]\n\n"


def ui_stream_response(body: AsyncIterator[str]):
    from fastapi.responses import StreamingResponse

    return StreamingResponse(body, media_type="text/event-stream", headers=UI_STREAM_HEADERS)
```

- [ ] **Step 2: `get_runtime_model` 支持按模型 ID 解析**

在 `provider/service.py::AiModelService.get_runtime_model` 增加 `model_id: int | None = None` 参数。当 `model_id` 给定：改为 `db.get(AiModelModel, model_id)` 且校验 `enabled and not is_deleted`，跳过 `usage` 过滤；否则维持现有查询。provider 解析逻辑（`base_url or p.base_url` 等）保持不变。签名：

```python
@classmethod
async def get_runtime_model(cls, usage: str | None = None, model_id: int | None = None) -> dict | None:
```

- [ ] **Step 3: `assistant/schema.py` 增 UI 请求体**

```python
class AssistantUIStreamSchema(BaseModel):
    """AI SDK useChat 请求体（只取 messages，其余字段忽略）。"""
    messages: list[dict] = Field(default_factory=list)
```

用于 `/ai/assistant/stream`。旧 `AssistantChatSchema` 保留给 `/chat`。

- [ ] **Step 4: `assistant/service.py` 增消息提取与 UI 流**

新增（保留旧 `run_assistant`，删除旧 `_sse`/`run_assistant_stream`）：

```python
def extract_openai_messages(ui_messages: list[dict]) -> list[dict]:
    """把 AI SDK UIMessage 列表转成 OpenAI messages（只取 user/assistant 的 text part）。"""
    out: list[dict] = []
    for m in ui_messages or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = ""
        for part in m.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text") or ""
        if text:
            out.append({"role": role, "content": text})
    return out


async def run_assistant_ui_stream(ui_messages: list[dict], auth):
    """AI SDK UI Message Stream 版助手：reasoning/text/tool/finish 分片。"""
    from openai import AsyncOpenAI

    from app.plugin.module_ai.provider.service import build_headers
    from app.plugin.module_ai.streaming import UiMessageStream

    ms = UiMessageStream()
    runtime = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    yield ms.start()
    if not runtime:
        yield ms.error("未配置大模型，请在 AI 管理→模型配置 中添加并启用")
        yield ms.finish()
        yield ms.done()
        return

    client = AsyncOpenAI(
        base_url=runtime["base_url"],
        api_key=runtime["api_key"] or "sk-none",
        default_headers=build_headers(
            runtime["base_url"], runtime.get("extra_headers"), "aistation-assistant"
        ),
    )
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += extract_openai_messages(ui_messages)
    user_id = getattr(getattr(auth, "user", None), "id", None)
    tool_log: list[dict] = []
    action = None
    report_id = None

    for _ in range(MAX_ROUNDS):
        try:
            stream = await client.chat.completions.create(
                model=runtime["model"],
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=runtime["temperature"],
                max_tokens=runtime["max_tokens"],
                stream=True,
            )
        except Exception as e:  # noqa: BLE001
            yield ms.error(f"大模型调用失败：{e}")
            yield ms.data("finish", {"reply": "", "tool_calls": tool_log, "action": action, "report_id": report_id})
            yield ms.finish()
            yield ms.done()
            return

        content = ""
        tool_calls: dict = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                yield ms.reasoning(rc)
            if getattr(delta, "content", None):
                content += delta.content
                yield ms.text(delta.content)
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_calls.setdefault(
                    tc.index, {"id": "", "name": "", "arguments": ""}
                )
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments

        yield ms.reasoning_end()
        yield ms.text_end()

        if not tool_calls:
            yield ms.data(
                "finish",
                {"reply": content, "tool_calls": tool_log, "action": action, "report_id": report_id},
            )
            yield ms.finish()
            yield ms.done()
            return

        messages.append(
            {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": s["id"],
                        "type": "function",
                        "function": {"name": s["name"], "arguments": s["arguments"]},
                    }
                    for s in tool_calls.values()
                ],
            }
        )
        for s in tool_calls.values():
            name = s["name"]
            try:
                args = json.loads(s["arguments"] or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            result = await _call_tool(name, args, user_id)
            if isinstance(result, dict):
                if result.get("__action__"):
                    action = result["__action__"]
                if result.get("__report_id__"):
                    report_id = result["__report_id__"]
            tool_log.append({"name": name, "args": args, "result": result})
            yield ms.tool(s["id"], name, args=args, output=result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": s["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                }
            )

    yield ms.text("工具调用次数已达上限，请缩小问题范围后重试。")
    yield ms.text_end()
    yield ms.data(
        "finish",
        {
            "reply": "工具调用次数已达上限，请缩小问题范围后重试。",
            "tool_calls": tool_log,
            "action": action,
            "report_id": report_id,
        },
    )
    yield ms.finish()
    yield ms.done()
```

- [ ] **Step 5: `assistant/controller.py` 改 `/stream`**

```python
@AssistantRouter.post("/stream", summary="AI 助手对话（AI SDK UI Message Stream）")
async def assistant_stream(
    data: AssistantUIStreamSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> StreamingResponse:
    import time

    from app.plugin.module_ai.streaming import ui_stream_response

    uid = getattr(getattr(auth, "user", None), "id", None)

    async def _gen():
        t0 = time.perf_counter()
        ok, err = True, None
        try:
            async for item in run_assistant_ui_stream(data.messages, auth):
                if '"type": "error"' in item:
                    ok = False
                    err = item
                yield item
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
            raise
        finally:
            await AiOverviewService.add_log(
                "assistant", "chat", int((time.perf_counter() - t0) * 1000),
                "success" if ok else "error", err, user_id=uid,
            )

    return ui_stream_response(_gen())
```

- [ ] **Step 6: 修复 `ai_call_logs` 落库**

`overview/model.py` 的 `AiCallLogModel` 增加 `user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="调用用户ID")`。`overview/service.py::add_log` 把 `created_id=user_id` 改为 `user_id=user_id`（去掉不存在的 `created_id`）。`init_app.py::_ensure_missing_columns` 的 `new_columns` 增加 `"ai_call_logs": [("user_id", "INTEGER")]`。

- [ ] **Step 7: 测试 `backend/tests/test_ai_ui_stream.py`**

覆盖：
1. `extract_openai_messages` 只取 text part、忽略 tool part、保留多轮。
2. 用 monkeypatch 一个假 `AsyncOpenAI`（`chat.completions.create(stream=True)` 返回 async 生成器，先 yield `reasoning_content` 再 yield `content`，无 tool_calls），POST `/api/v1/ai/assistant/stream`（`auth_headers`），断言文本包含 `"type": "reasoning-delta"`、`"type": "text-delta"`、`"type": "finish"`、`data: [DONE]`，且响应头 `x-vercel-ai-ui-message-stream == "v1"`。
3. 假 LLM 首次返回一个 `navigate` tool_call、第二次返回文本；断言出现 `tool-input-available` + `tool-output-available`。
4. `AiOverviewService.add_log(...)` 后查 `ai_call_logs` 有一条且 `user_id` 正确（回归 bug）。

参考 `backend/tests/test_ai_assistant.py` 现有的 `AsyncOpenAI` monkeypatch 写法。

- [ ] **Step 8: 运行 + 提交**

Run: `cd backend && uv run pytest tests/test_ai_ui_stream.py tests/test_ai_assistant.py -q && uv run ruff check app/plugin/module_ai/streaming.py app/plugin/module_ai/assistant app/plugin/module_ai/provider/service.py app/plugin/module_ai/overview app/scripts/init_app.py`

```bash
git add backend/app/plugin/module_ai/streaming.py backend/app/plugin/module_ai/provider/service.py backend/app/plugin/module_ai/assistant backend/app/plugin/module_ai/overview backend/app/scripts/init_app.py backend/tests/test_ai_ui_stream.py
git commit -m "feat(ai): 后端改用 AI SDK UI Message Stream 协议并修复调用日志落库"
```

---

### Task 2: 前端迁移到 `useChat` + 控制台/运行台/聊天页 Element Plus 化

**Files:**
- Create: `frontend/src/composables/ai/useAiChat.ts`
- Create: `frontend/src/composables/ai/uiMessage.ts`（parts 类型与渲染辅助）
- Modify: `frontend/src/views/module_ai/playground/index.vue`（重建）
- Modify: `frontend/src/views/module_ai/overview/index.vue`（Element Plus 化）
- Modify: `frontend/src/views/module_ai/chat/index.vue`（发送/接收改 `useAiChat`，侧栏保留）
- Modify: `frontend/src/components/AiAssistant/index.vue`（悬浮球主路径改 `useAiChat` + `data-finish`，保留 Agno 回退）
- Modify: `frontend/src/api/module_ai/assistant.ts`（移除 `assistantStream` 手写解析，保留 `assistantChat`）
- Modify: `frontend/src/main.ts`（移除 `@/styles/ai-console.css` 引用）
- Delete: `frontend/src/styles/ai-console.css`
- Test: `frontend/e2e/ai-console.spec.ts`（更新断言）

**Interfaces:**
- Consumes: Task 1 的 `/api/v1/ai/assistant/stream`（UI Message Stream，含 `data-finish`）。
- Produces:
  - `useAiChat(options?: { path?: string; body?: () => Record<string, unknown> })` → `useChat` 返回值。
  - `uiMessage.ts`：`textOf(msg)`、`reasoningOf(msg)`、`toolPartsOf(msg)`、`dataPartsOf(msg, type)`、`partText(part)`。

- [ ] **Step 1: `useAiChat.ts`**

```ts
import { useChat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { Auth } from "@/utils/auth";

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
  /** 附加请求体（如 app_id / session_id）。 */
  body?: () => Record<string, unknown>;
}

/** 基于 Vercel AI SDK 的聊天组合式函数（流式 UI Message Stream）。 */
export function useAiChat(options: UseAiChatOptions = {}) {
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const transport = new DefaultChatTransport({
    api: `${base}${options.path || "/ai/assistant/stream"}`,
    headers: { Authorization: `Bearer ${Auth.getAccessToken() || ""}` },
    body: options.body,
  });
  return useChat({ transport });
}
```

- [ ] **Step 2: `uiMessage.ts` 渲染辅助**

```ts
export interface AiUIPart {
  type: string;
  text?: string;
  delta?: string;
  toolName?: string;
  toolCallId?: string;
  state?: string;
  input?: any;
  output?: any;
  errorText?: string;
  data?: any;
  [k: string]: any;
}

/** 取消息的纯文本（累加 text part）。 */
export function textOf(msg: any): string {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === "text")
    .map((p: AiUIPart) => p.text || "")
    .join("");
}

/** 取思考文本（累加 reasoning part）。 */
export function reasoningOf(msg: any): string {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === "reasoning")
    .map((p: AiUIPart) => p.text || "")
    .join("");
}

/** 取工具类 part（dynamic-tool）。 */
export function toolPartsOf(msg: any): AiUIPart[] {
  return (msg?.parts || []).filter((p: AiUIPart) => p.type === "dynamic-tool");
}

/** 取指定 data-* part 的 data（如 "data-finish"）。 */
export function dataPartsOf(msg: any, type: string): any[] {
  return (msg?.parts || [])
    .filter((p: AiUIPart) => p.type === type)
    .map((p: AiUIPart) => p.data);
}
```

- [ ] **Step 3: 重建 `playground/index.vue`（Element Plus）**

结构（单一根 `<div class="app-container">`，避免多根 + Transition 白屏）：
- `el-row :gutter="16"` 两列：左 `el-col :xs="24" :md="16"`，右 `el-col :xs="24" :md="8"`。
- 左：`el-card` 内 `el-scrollbar`（高度 `calc(100vh - 260px)`）遍历 `chat.messages`；用户气泡右对齐，助手 part 渲染：`text` 走 `markdown-it`，`reasoning` 用 `el-collapse` 折叠，`dynamic-tool` 用 `el-tag` + `el-collapse` 展示 input/output。
- 右：`el-card`「工具调用」遍历所有 `dynamic-tool` part，`el-timeline`/`el-tag` 展示 `state`（input-streaming/input-available/output-available/output-error）。
- 底部：`el-input type="textarea"` + `el-button`（`:loading="status==='streaming'||status==='submitted'"`）；Enter 发送、Shift+Enter 换行；生成中显示「停止」调 `chat.stop()`。
- 逻辑：
  ```ts
  const chat = useAiChat();
  async function send() {
    const text = input.value.trim();
    if (!text || busy.value) return;
    input.value = "";
    await chat.sendMessage({ text });
  }
  ```
- 不再使用 `.ai-console`/`.ai-grid`/`.ai-table` 等自定义类。

- [ ] **Step 4: 重做 `overview/index.vue`（Element Plus）**

- 根 `<div class="app-container">`；顶部 `el-card` 放 `el-descriptions`（提供商/模型/调用/错误/平均耗时，数据来自 `getAiOverviewStats`）。
- 最近调用用 `el-table`（列：模型/用途/耗时/结果 `el-tag`/时间）。
- 快捷入口用 `el-button`（provider/model/playground/report）。
- 移除 `.ai-signal`/`.ai-panel` 等自定义类。

- [ ] **Step 5: `chat/index.vue` 接入 `useAiChat`**

保留 `el-container` 布局与 `Sidebar`（Agno 历史只读）。把 `handleSendMessage` 的自写 SSE 改为 `const chat = useAiChat(); await chat.sendMessage({ text });`。消息渲染改为基于 `chat.messages`（复用 `MessageItem`，content 用 `textOf`，think 用 `reasoningOf`，工具用 `toolPartsOf`）。删除对 `assistantStream` 的 import。

- [ ] **Step 6: `components/AiAssistant/index.vue` 迁移到 `useAiChat`**

把 `handleExecute` 的主路径（原 `assistantStream` 块）改为：

```ts
const chat = useAiChat();
await chat.sendMessage({ text: rawCommand });
const last = chat.messages.value[chat.messages.value.length - 1];
const fin: any = dataPartsOf(last, "data-finish")[0] || {};
const action = fin.action;
const reportId = fin.report_id;
```

`action?.type === "navigate"` → `router.push(action.path)`；`confirm` → `confirmAssistantAction(action)`；`reportId` → 成功提示。保留 `catch` 回退到 `AiChatAPI.chat`（Agno）。移除 `assistantStream` import。工具调用提示可由 `toolPartsOf(last)` 汇总。

- [ ] **Step 7: `assistant.ts` 移除手写 SSE**

删除 `assistantStream` 函数与不再使用的类型；保留 `assistantChat` 与 `AssistantResult`。确认 `rg "assistantStream" frontend/src` 无残留（`chat/index.vue` 与 `components/AiAssistant/index.vue` 已在 Step 5/6 迁移）。

- [ ] **Step 8: 移除 `ai-console.css`**

删除 `frontend/src/styles/ai-console.css`；从 `frontend/src/main.ts` 移除该 import；确认 `rg "ai-console" frontend/src` 无残留。

- [ ] **Step 9: E2E + 类型检查**

更新 `frontend/e2e/ai-console.spec.ts`：
- `/#/ai/overview` 可见 `el-card`，标题「大模型控制台」。
- `/#/ai/playground` 可见输入框与发送按钮（不再断言 `.ai-console`）。

Run: `cd frontend && pnpm type-check && pnpm e2e e2e/ai-console.spec.ts`

- [ ] **Step 10: 无头截图 + 视觉验收**

启动前端与后端后，用 Playwright 脚本截 `/#/ai/overview`、`/#/ai/playground` 两图；用 `vision-recognition` 技能核对：与 `module_system/param` 风格一致、无自定义深色指标卡。

- [ ] **Step 11: 提交**

```bash
git add frontend/src/composables/ai frontend/src/views/module_ai frontend/src/components/AiAssistant/index.vue frontend/src/api/module_ai/assistant.ts frontend/src/main.ts frontend/e2e/ai-console.spec.ts
git rm frontend/src/styles/ai-console.css
git commit -m "feat(ai): 聊天/运行台迁移到 @ai-sdk/vue useChat 并统一 Element Plus 样式"
```

---

### Task 3: B 提示词工作台（`ai_prompts` + 工作台页）

**Files:**
- Create: `backend/app/plugin/module_ai/prompts/__init__.py|model.py|schema.py|service.py|controller.py`
- Modify: `backend/app/scripts/initialize.py`（import `AiPromptModel`）
- Modify: `backend/app/scripts/init_app.py`（`_ensure_ai_menus` 加 `/ai/prompt` + 按钮权限）
- Create: `frontend/src/api/module_ai/prompt.ts`
- Create: `frontend/src/views/module_ai/prompt/index.vue`
- Test: `backend/tests/test_ai_prompts.py`；`frontend/e2e/ai-prompt.spec.ts`

**Interfaces:**
- Produces:
  - `AiPromptModel`(表 `ai_prompts`)：`name(uniq)`、`category`、`blocks`(JSONB `[{type,content}]`)、`variables`(JSONB)、`version`(int)、`enabled`。
  - `AiPromptService.list_prompts()/create/update/delete/get_prompt(id)`。
  - `render_prompt(blocks, values) -> str`（`{{var}}` 替换；未知变量原样保留）。
  - 路由 `/ai/prompts/list|create|update/{id}|delete|detail/{id}`，权限 `module_ai:prompt:{query,create,update,delete}`。

- [ ] **Step 1: 后端模型 + schema + service**（`blocks` 校验为 `list[dict]`，每项含 `type`∈{system,context,instruction,example,output} 与 `content`；`variables` 为 `list[str]`）。
- [ ] **Step 2: `render_prompt` 工具函数（供 C 使用）**

```python
import re

_VAR_RE = re.compile(r"\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}")


def render_prompt(blocks: list[dict], values: dict | None = None) -> str:
    values = values or {}
    parts = []
    for b in blocks or []:
        text = b.get("content") or ""
        text = _VAR_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
        parts.append(f"【{b.get('type', 'instruction')}】\n{text}")
    return "\n\n".join(parts)
```

- [ ] **Step 3: controller + 菜单权限**（`pages` 增 `("提示词", "AiPrompt", "/ai/prompt", "module_ai/prompt/index", "module_ai:prompt:query", 13)`；`AI_BUTTON_PERMS` 增 create/update/delete）。
- [ ] **Step 4: 后端测试**：create → list 含 blocks/variables；`render_prompt` 替换 `{{name}}`、未知变量保留；update/delete。
- [ ] **Step 5: 前端 API + 页面**

页面三栏 `el-row`：
- 左 `el-col :span="6"`：块列表，`vuedraggable`（已装）拖拽排序，`el-button` 添加块（类型下拉）。
- 中 `el-col :span="12"`：`el-form` 名称/分类/启用；每块 `el-input type="textarea"`；保存调 `create/update`。
- 右 `el-col :span="6"`：自动识别变量（正则 `{{x}}`）`el-tag` 列表 + 示例值 `el-input` + `el-card` 预览（前端本地替换）。

- [ ] **Step 6: E2E + 提交**：`/#/ai/prompt` 打开 → 新增块 → 预览出现变量。`pnpm type-check`。

---

### Task 4: C1 工具中心（`ai_tools` 内置开关 + 自定义 HTTP 工具）

**Files:**
- Create: `backend/app/plugin/module_ai/tools_catalog/__init__.py|model.py|schema.py|service.py|controller.py`
- Modify: `backend/app/scripts/initialize.py`（import `AiToolModel`）
- Modify: `backend/app/scripts/init_app.py`（菜单 `/ai/tool` + 权限；启动兜底把 `TOOL_REGISTRY` 内置工具写入 `ai_tools`）
- Create: `frontend/src/api/module_ai/tool.ts`
- Create: `frontend/src/views/module_ai/tool/index.vue`
- Test: `backend/tests/test_ai_tools.py`；`frontend/e2e/ai-tool.spec.ts`

**Interfaces:**
- Produces:
  - `AiToolModel`(表 `ai_tools`)：`name(uniq)`、`kind`(builtin/http)、`method`、`url`、`headers`(JSONB)、`params_schema`(JSONB)、`enabled`。
  - `AiToolService.list_tools()/create/update/delete/toggle(id, enabled)`。
  - `get_enabled_tool_schemas() -> list[dict]`（内置工具用 `TOOL_REGISTRY[name]["schema"]`；HTTP 工具按 `params_schema` 生成 JSON schema）。
  - `build_http_tool_fn(tool) -> callable`：`httpx.AsyncClient` 调 `method/url`，`headers` + 参数替换。
  - 路由 `/ai/tools/list|create|update/{id}|delete|toggle/{id}|test/{id}`，权限 `module_ai:tool:*`。

- [ ] **Step 1: 模型 + schema + service + controller。**
- [ ] **Step 2: 内置工具同步**：在 `_ensure_ai_menus` 同处新增 `_ensure_ai_tools()`（或就地），遍历 `TOOL_REGISTRY` 写入缺失的 `ai_tools(kind="builtin", enabled=True)`。
- [ ] **Step 3: HTTP 工具执行器**（`service.py`）：

```python
async def execute_http_tool(tool: AiToolModel, args: dict) -> object:
    import httpx
    url = tool.url or ""
    headers = {str(k): str(v) for k, v in (tool.headers or {}).items()}
    remaining = {k: v for k, v in (args or {}).items() if f"{{{k}}}" in url}
    for k, v in remaining.items():
        url = url.replace(f"{{{k}}}", str(v))
    query = {k: v for k, v in (args or {}).items() if k not in remaining}
    async with httpx.AsyncClient(timeout=30) as c:
        if (tool.method or "GET").upper() == "POST":
            resp = await c.post(url, json=query, headers=headers)
        else:
            resp = await c.get(url, params=query, headers=headers)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"status": resp.status_code, "text": resp.text[:2000]}
```

- [ ] **Step 4: 后端测试**：内置同步存在；HTTP 工具 `test/{id}` 用 monkeypatched `httpx` 断言 URL/参数；toggle 生效。
- [ ] **Step 5: 前端页面**：`el-tabs` 两个 tab：内置工具（`el-table` + `el-switch` 调 toggle）、自定义 HTTP 工具（`el-table` + `EnhancedDialog` 表单 name/method/url/headers(JSON)/params_schema(JSON)/enabled）。
- [ ] **Step 6: E2E + 提交**。

---

### Task 5: C2 AI 应用（`ai_apps` + `/ai/apps/{id}/run/stream`）

**Files:**
- Create: `backend/app/plugin/module_ai/apps/__init__.py|model.py|schema.py|service.py|controller.py`
- Modify: `backend/app/scripts/initialize.py`（import `AiAppModel`）
- Modify: `backend/app/scripts/init_app.py`（菜单 `/ai/app` + 权限）
- Create: `frontend/src/api/module_ai/app.ts`
- Create: `frontend/src/views/module_ai/app/index.vue`
- Test: `backend/tests/test_ai_apps.py`；`frontend/e2e/ai-app.spec.ts`

**Interfaces:**
- Consumes: `AiPromptService.get_prompt` + `render_prompt`；`AiToolService.get_enabled_tool_schemas`/`execute_http_tool`；`AiModelService.get_runtime_model(model_id=...)`；`streaming.UiMessageStream`。
- Produces:
  - `AiAppModel`(表 `ai_apps`)：`name(uniq)`、`icon`、`description`、`model_id`(int, 可空)、`prompt_id`(int, 可空)、`tools`(JSONB `list[str]` 工具名)、`output_format`(text/table/report)、`input_schema`(JSONB)、`enabled`、`order`。
  - `AiAppService.list_apps/create/update/delete/get_app(id)`。
  - `run_app_ui_stream(app_id, ui_messages, auth) -> AsyncIterator[str]`。
  - 路由 `/ai/apps/list|create|update/{id}|delete|detail/{id}|run/stream`，权限 `module_ai:app:{query,create,update,delete}` + run 用 `module_ai:app:query`。

- [ ] **Step 1: 模型 + schema + service + controller。**
- [ ] **Step 2: `run_app_ui_stream`**：解析 app → system prompt = `render_prompt(prompt.blocks, values)`（values 从 body `variables` 或 input_schema 默认取）；model runtime = `get_runtime_model(model_id=app.model_id)` else 默认；工具集 = app.tools 中 enabled 的内置/HTTP 工具（`TOOL_REGISTRY` 或 `execute_http_tool`）；执行与 Task 1 相同的 function-calling 循环，产出 `UiMessageStream` 帧（含末尾 `data-finish`）；用 `add_log(..., app_id=app.id, user_id=uid)`。
- [ ] **Step 3: 后端测试**：创建 app（绑定 prompt+内置工具）→ `POST /ai/apps/{id}/run/stream`（假 LLM）→ 断言 system prompt 含渲染后的提示词、SSE 帧含 text-delta、日志有 `app_id`。
- [ ] **Step 4: 前端 API + 页面**：`el-table` 列（图标/名称/模型/提示词/工具数/输出格式/启用/操作）；`EnhancedDialog` 表单（模型下拉 `getAiModelList`、提示词下拉 `getPromptList`、工具多选、输出格式、入参 JSON）；行内「运行」→ `router.push({ path: '/ai/playground', query: { app_id } })`。
- [ ] **Step 5: E2E + 提交**。

---

### Task 6: D 会话与日志（`ai_sessions`/`ai_messages` + 日志页 + 运行台会话）

**Files:**
- Create: `backend/app/plugin/module_ai/sessions/__init__.py|model.py|schema.py|service.py|controller.py`
- Create: `backend/app/plugin/module_ai/logs_center/__init__.py|controller.py`（复用 `AiCallLogModel`）
- Modify: `backend/app/scripts/initialize.py`（import `AiSessionModel`/`AiMessageModel`）
- Modify: `backend/app/scripts/init_app.py`（菜单 `/ai/logs`；可合并到 `_ensure_ai_menus`）
- Create: `frontend/src/api/module_ai/session.ts`、`frontend/src/api/module_ai/logs.ts`
- Create: `frontend/src/views/module_ai/logs/index.vue`
- Modify: `frontend/src/views/module_ai/playground/index.vue`（选应用 + 会话历史侧栏）
- Modify: `frontend/src/composables/ai/useAiChat.ts`（支持 `session_id` 回填与持久化）
- Test: `backend/tests/test_ai_sessions_logs.py`；`frontend/e2e/ai-logs.spec.ts`

**Interfaces:**
- Produces:
  - `AiSessionModel`(表 `ai_sessions`)：`app_id`、`title`、`user_id`、`message_count`。
  - `AiMessageModel`(表 `ai_messages`)：`session_id`、`role`、`parts`(JSONB)、`app_id`。
  - `AiSessionService.list_sessions()/get_messages(id)/create(title, app_id)/append_message(session_id, role, parts)/delete(ids)`。
  - 路由 `/ai/sessions/list|detail/{id}|delete` 权限 `module_ai:assistant:query`；`/ai/logs/list`（`page_no/page_size/usage/result/keyword`）权限 `module_ai:assistant:query`。
- Consumes: Task 1/5 的流式接口在结束时落 `ai_sessions`/`ai_messages`（在 controller 的 generator `finally` 中调用 `append_message`，assistant 内容取最终文本）。

- [ ] **Step 1: 模型 + service + controller（sessions/logs）。** `/ai/logs/list` 返回分页 `{page_no,page_size,total,has_next,items}`，按 `created_time desc`，支持 `usage`/`result`/`keyword` 过滤。
- [ ] **Step 2: 流式落会话**：给 `run_assistant_ui_stream` 与 `run_app_ui_stream` 增加可选 `session_id`（来自 body）；在流结束时把 user 文本与 assistant 聚合文本写入 `ai_messages` 并 upsert `ai_sessions.message_count`。body schema 相应加 `session_id: int|None`。
- [ ] **Step 3: 后端测试**：创建会话 → 追加消息 → list/detail 正确；传 `session_id` 跑一次流式后该会话多 2 条消息；`/ai/logs/list` 分页与过滤。
- [ ] **Step 4: 前端日志页**：`PageSearch`（用途/结果/关键字）+ `PageContent` + `el-table`（时间/模型/用途/耗时/结果/错误），复用 CURD 模式。
- [ ] **Step 5: 运行台增强**：顶部应用下拉（`getAiAppList`，默认空=通用助手）+ 「新建会话/历史会话」`el-drawer`；调用 `useAiChat({ body: () => ({ app_id, session_id }) })`；切会话时用 `chat.messages.value = restored` 回填。
- [ ] **Step 6: E2E + 提交**。

---

### Task 7: E 报告增强 + 全量回归 + 视觉验收

**Files:**
- Modify: `backend/app/plugin/module_ai/report/model.py|service.py|controller.py`（`AiReportModel` 增 `app_id`/`session_id` 可空列，`init_app._ensure_missing_columns` 补列）
- Modify: `frontend/src/views/module_ai/report/index.vue`（来源筛选 + 导出已有；无则补 Markdown 导出）
- Test: `backend/tests/test_ai_report_enhance.py`

- [ ] **Step 1: 报告关联应用/会话**：模型加可空 `app_id`/`session_id`，`list_reports` 返回；`generate_report` 工具可将当前 app/session 写入 source。
- [ ] **Step 2: 后端测试**：带 `app_id` 创建报告 → list 含 `app_id`。
- [ ] **Step 3: 全量后端回归**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_ai/ app/scripts/init_app.py`

- [ ] **Step 4: 全量前端回归**

Run: `cd frontend && pnpm type-check && pnpm e2e`（记录既有 pre-existing 错误，新增文件必须 0 错误）

- [ ] **Step 5: 无头截图 + 视觉验收**（overview/playground/prompt/tool/app/logs 六页），用 `vision-recognition` 核对与 `module_system/param` 风格一致。

- [ ] **Step 6: 更新账本 + 提交**

在 `.superpowers/sdd/progress.md` 追加 AI v2 各任务完成记录；提交。

```bash
git add docs/superpowers/plans/2026-09-13-ai-platform-v2.md .superpowers/sdd/progress.md
git commit -m "docs(ai): AI 管理 v2 计划与进度账本"
```

---

## Self-Review

- Spec §1（多提供商/多模型）→ Task 1（按 model_id 解析）；§1.2 提示词 → Task 3；§1.3 应用 → Task 5；§1.4 工具 → Task 4；§1.5 运行台 + 流式 → Task 1/2/6；§1.6 会话/日志 → Task 6；§1.7 报告 → Task 7。
- Spec §2 数据模型：`ai_prompts`(T3)、`ai_apps`(T5)、`ai_tools`(T4)、`ai_sessions/ai_messages`(T6)、`ai_call_logs.user_id`(T1)、`ai_reports.app_id`(T7)。
- Spec §3 运行时与流式：`get_runtime_model(model_id)`(T1)、`build_headers`(已有)、UI Message Stream(T1)、`/ai/apps/{id}/run/stream`(T5)。
- Spec §4 前端页面：provider/model 已有；prompt(T3)、app(T5)、tool(T4)/playground(T2,T6)、report(T7)/overview(T2)。
- Spec §5 交付顺序：AI SDK 迁移(T1/T2) → B(T3) → C(T4/T5) → D(T6) → E(T7)。
- 命名一致：`UiMessageStream`、`ui_stream_response`、`extract_openai_messages`、`run_assistant_ui_stream`、`run_app_ui_stream`、`useAiChat`、`textOf/reasoningOf/toolPartsOf/dataPartsOf`、`render_prompt`、`execute_http_tool` 全计划统一。
- 风险：`useChat` 请求体默认字段多于 `{messages}`（Pydantic 默认忽略额外字段，已确认）；SSE 仍需 `Content-Encoding: identity` 防 GZip 缓冲；Element Plus 布局用 `el-row/el-col` 规避全局 CSS Grid 覆盖。
