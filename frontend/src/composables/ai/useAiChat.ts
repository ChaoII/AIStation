import { computed, ref, shallowRef } from "vue";
import { Auth } from "@/utils/auth";

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
  /** 附加请求体（如 app_id / session_id）。 */
  body?: () => Record<string, unknown>;
}

/** Agno 原生 SSE 事件（宽松类型，事件字段为 event: <RunEvent>）。 */
interface AgnoEvent {
  event?: string;
  content?: unknown;
  reasoning_content?: string;
  tool?: Record<string, unknown> | null;
  error?: string;
  message?: string;
  [k: string]: unknown;
}

interface UiPart {
  type: string;
  text?: string;
  delta?: string;
  toolName?: string;
  toolCallId?: string;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  data?: unknown;
  sources?: unknown[];
  [k: string]: unknown;
}

interface UiMessage {
  id: string;
  role: "user" | "assistant";
  parts: UiPart[];
}

/**
 * 基于 Agno 原生事件流（SSE：event: <RunEvent> / data: {...}）的聊天组合式函数。
 *
 * 后端 `assistant /stream` 已改为直出 Agno 原生事件流，客户端用 fetch + ReadableStream
 * 逐帧解析，并把 RunContent / ReasoningContentDelta / ToolCall* 映射为兼容的
 * UIMessage parts（text / reasoning / dynamic-tool / data-finish），使既有消费方
 * （`chat/index.vue`、`AiAssistant/index.vue`）无需改动即可消费。
 */
export function useAiChat(options: UseAiChatOptions | (() => UseAiChatOptions) = {}) {
  const getOptions = typeof options === "function" ? options : () => options;
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";

  const messages = ref<UiMessage[]>([]);
  const status = ref<"ready" | "submitted" | "streaming" | "error">("ready");
  const error = ref<string | null>(null);
  const abortCtrl = shallowRef<{ abort: () => void } | null>(null);

  // 当前正在流式构建的 assistant 消息（parts 容器）
  let streamingMsg: UiMessage | null = null;

  /** 把一条 src 级别的文本追加到 streamingMsg 的指定 part 类型。 */
  function appendPart(messageId: string, part: UiPart) {
    const target = messages.value.find((m) => m.id === messageId);
    if (!target) return;
    const last = target.parts[target.parts.length - 1];
    if (last && last.type === part.type) {
      last.text = (last.text || "") + (part.text || "");
    } else {
      target.parts.push(part);
    }
  }

  /** 从 Agno 工具执行结果里提取 __action__ / __report_id__ / 正文。 */
  function extractMeta(result: unknown): { action?: unknown; reportId?: unknown } {
    // result 可能是 JSON 字符串或对象
    let obj = result;
    if (typeof result === "string") {
      try {
        obj = JSON.parse(result);
      } catch {
        return {};
      }
    }
    if (obj && typeof obj === "object") {
      const d = obj as Record<string, unknown>;
      return { action: d["__action__"], reportId: d["__report_id__"] };
    }
    return {};
  }

  async function sendMessage(input: { text: string }) {
    const opts = getOptions();
    const path = opts.path || "/ai/assistant/stream";
    const text = (input?.text || "").trim();
    if (!text || status.value === "submitted" || status.value === "streaming") return;

    status.value = "submitted";
    error.value = null;

    // 追加用户消息
    const userMsg: UiMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      parts: [{ type: "text", text }],
    };
    messages.value = [...messages.value, userMsg];

    // 预留 assistant 消息（流式填充）
    const asstId = `a-${Date.now()}`;
    streamingMsg = { id: asstId, role: "assistant", parts: [] };
    messages.value = [...messages.value, streamingMsg];

    // 把历史消息（含本轮 user）转成后端 UIMessage 请求体
    const payloadMessages = messages.value
      .filter((m) => (m.parts || []).some((p) => p.type === "text"))
      .map((m) => ({
        role: m.role,
        parts: (m.parts || [])
          .filter((p) => p.type === "text" && p.text)
          .map((p) => ({ type: "text", text: String(p.text || "") })),
      }));

    const body: Record<string, unknown> = { messages: payloadMessages };
    if (opts.body) {
      Object.assign(body, opts.body());
    }

    const ctrl = new AbortController();
    abortCtrl.value = ctrl;

    try {
      const res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
        },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`请求失败（HTTP ${res.status}）`);
      }

      status.value = "streaming";

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      // 累积的正文 / reasoning / 工具汇总，供结束帧合成
      let accText = "";
      let accAction: unknown;
      let accReportId: unknown;
      const toolParts: unknown[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 按空行分隔的 SSE 帧解析
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";

        for (const rawFrame of frames) {
          let eventName = "message";
          const dataLines: string[] = [];
          for (const line of rawFrame.split("\n")) {
            if (line.startsWith(":")) continue;
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataLines.push(line.slice(5).trim());
            }
          }
          if (dataLines.length === 0) continue;
          let data: AgnoEvent;
          try {
            data = JSON.parse(dataLines.join("\n"));
          } catch {
            continue;
          }

          const type = eventName || data.event || "message";

          if (type === "RunContent") {
            const text = typeof data.content === "string" ? data.content : "";
            if (text) {
              accText += text;
              appendPart(asstId, { type: "text", text });
            }
          } else if (type === "ReasoningContentDelta") {
            const text = data.reasoning_content || "";
            if (text) {
              appendPart(asstId, { type: "reasoning", text });
            }
          } else if (type === "ToolCallStarted" || type === "ToolCallCompleted") {
            const tool = (data.tool || {}) as Record<string, unknown>;
            if (tool) {
              const toolName = String(tool.tool_name || tool.toolName || "工具");
              const toolCallId = String(tool.tool_call_id || tool.toolCallId || toolName);
              appendPart(asstId, {
                type: "dynamic-tool",
                toolName,
                toolCallId,
                input: tool.tool_args ?? tool.input,
                output: tool.result ?? tool.output,
              });
              const meta = extractMeta(tool.result);
              if (meta.action) accAction = meta.action;
              if (meta.reportId != null) accReportId = meta.reportId;
              toolParts.push({ toolName, toolCallId, result: tool.result });
            }
          } else if (type === "RunError" || type === "error") {
            error.value = data.error || data.message || "运行失败";
            status.value = "error";
          }
        }
      }

      // 流结束：合成 data-finish part（兼容旧 UI 消费方）
      const finPart: UiPart = {
        type: "data-finish",
        data: {
          reply: accText,
          action: accAction,
          report_id: accReportId,
          tool_calls: toolParts,
        },
      };
      const target = messages.value.find((m) => m.id === asstId);
      if (target) target.parts.push(finPart);
    } catch (e: any) {
      if (e?.name === "AbortError") {
        status.value = "ready";
      } else {
        error.value = e?.message || String(e);
        status.value = "error";
      }
    } finally {
      abortCtrl.value = null;
      if (status.value !== "error") status.value = "ready";
      streamingMsg = null;
    }
  }

  function stop() {
    if (abortCtrl.value) abortCtrl.value.abort();
  }

  async function regenerate() {
    // 重新生成：找到最后一条 user 文本，重发
    const lastUser = [...messages.value].reverse().find((m) => m.role === "user");
    if (lastUser) {
      const text = (lastUser.parts.find((p) => p.type === "text")?.text || "").trim();
      // 移除最后一条 assistant 与最后一条 user，再重发
      messages.value = messages.value.filter((m) => m.id !== lastUser.id);
      const lastAssistant = messages.value[messages.value.length - 1];
      if (lastAssistant && lastAssistant.role === "assistant") {
        messages.value = messages.value.slice(0, -1);
      }
      await sendMessage({ text });
    }
  }

  const isStreaming = computed(() => status.value === "submitted" || status.value === "streaming");

  return {
    messages,
    status,
    error,
    isStreaming,
    sendMessage,
    stop,
    regenerate,
  };
}
