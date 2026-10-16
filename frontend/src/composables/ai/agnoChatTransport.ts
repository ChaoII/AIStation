import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { Auth } from "@/utils/auth";

/** mapAgnoEvent 的可变状态上下文（每个流一个）。 */
export interface MapCtx {
  /** 当前 assistant 消息的 id（chunk 的 part id 与之绑定）。 */
  messageId: string;
  /** 用于生成缺失 tool_call_id 的自增序号。 */
  seq: number;
  /** 文本 part 是否已 start。 */
  textStarted?: boolean;
  /** 思维 part 是否已 start。 */
  reasoningStarted?: boolean;
  /** 按工具名缓存 tool_call_id 队列（FIFO，保证多个同名工具的 input/output 成对）。 */
  toolIds?: Record<string, string[]>;
}

export interface ParsedFrame {
  event: string;
  data: any;
}

/** 解析单个 Agno SSE 帧（`event:`/`data:` + 空行分隔）。非法或无数据返回 null。 */
export function parseAgnoFrame(raw: string): ParsedFrame | null {
  if (!raw.trim()) return null;
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    const s = line.replace(/\r$/, "");
    if (!s || s.startsWith(":")) continue;
    if (s.startsWith("event:")) event = s.slice(6).trim();
    else if (s.startsWith("data:")) dataLines.push(s.slice(5).trim());
  }
  if (!dataLines.length) return null;
  let data: any;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  if (event === "message" && data?.event) event = String(data.event);
  return { event, data };
}

const isStr = (v: unknown): v is string => typeof v === "string";

/** 判断工具结果是否表达失败（保守启发式），返回错误文本或 null。 */
function toolResultError(result: unknown): string | null {
  if (result == null) return null;
  if (typeof result === "string") {
    const s = result.trim();
    if (/^(错误|失败|error|Error|ERROR|fail|Fail)/.test(s)) return s;
    return null;
  }
  if (typeof result === "object") {
    const r = result as Record<string, unknown>;
    if (r.success === false || r.ok === false) {
      return String(r.error ?? r.message ?? r.reason ?? "工具调用失败");
    }
    if (r.error || r.__error__) {
      return String(r.error ?? r.__error__);
    }
  }
  return null;
}

/**
 * 把一个 Agno 事件映射为 AI SDK 的 `UIMessageChunk` 序列（纯函数，可测）。
 *
 * 语义为状态机：文本/思维 `RunContent`/`ReasoningContentDelta` 是**增量**，
 * 首次事件发 `-start`，后续仅发 `-delta`；`RunCompleted` 时补 `-end`。
 */
export function mapAgnoEvent(eventName: string, data: any, ctx: MapCtx): UIMessageChunk[] {
  const id = ctx.messageId;
  const out: UIMessageChunk[] = [];

  switch (eventName) {
    case "RunContent": {
      const text = isStr(data?.content) ? data.content : "";
      if (!text) return [];
      if (!ctx.textStarted) {
        ctx.textStarted = true;
        out.push({ type: "text-start", id });
      }
      out.push({ type: "text-delta", id, delta: text });
      return out;
    }
    case "ReasoningContentDelta": {
      const text = isStr(data?.reasoning_content) ? data.reasoning_content : "";
      if (!text) return [];
      if (!ctx.reasoningStarted) {
        ctx.reasoningStarted = true;
        out.push({ type: "reasoning-start", id });
      }
      out.push({ type: "reasoning-delta", id, delta: text });
      return out;
    }
    case "ToolCallStarted": {
      const tool = (data?.tool || {}) as Record<string, unknown>;
      const toolName = String(tool.tool_name ?? tool.toolName ?? "工具");
      const provided = String(tool.tool_call_id ?? tool.toolCallId ?? "");
      const toolCallId = provided || `tool-${toolName}-${++ctx.seq}`;
      (ctx.toolIds ||= {})[toolName] = [...(ctx.toolIds[toolName] || []), toolCallId];
      out.push({
        type: "tool-input-available",
        toolCallId,
        toolName,
        input: tool.tool_args ?? tool.input,
      });
      return out;
    }
    case "ToolCallCompleted": {
      const tool = (data?.tool || {}) as Record<string, unknown>;
      const toolName = String(tool.tool_name ?? tool.toolName ?? "工具");
      const provided = String(tool.tool_call_id ?? tool.toolCallId ?? "");
      const queue = ctx.toolIds?.[toolName];
      const toolCallId =
        provided || (queue && queue.length ? queue.shift()! : `tool-${toolName}-${++ctx.seq}`);
      const result = tool.result ?? tool.output;
      const errText = toolResultError(result);
      if (errText) {
        out.push({ type: "tool-output-error", toolCallId, errorText: errText });
      } else {
        out.push({ type: "tool-output-available", toolCallId, output: result });
      }
      return out;
    }
    case "RunError": {
      out.push({
        type: "error",
        errorText: String(data?.error ?? data?.message ?? "运行失败"),
      });
      return out;
    }
    case "RunStarted":
      return [{ type: "start-step" }];
    case "RunCompleted": {
      if (ctx.textStarted) {
        ctx.textStarted = false;
        out.push({ type: "text-end", id });
      }
      if (ctx.reasoningStarted) {
        ctx.reasoningStarted = false;
        out.push({ type: "reasoning-end", id });
      }
      out.push({ type: "finish-step" });
      return out;
    }
    default:
      return [];
  }
}

export interface AgnoChatTransportOptions {
  /** 相对 base 的流式路径，如 `/ai/assistant/stream`。 */
  path: string;
  /** API 前缀，默认取 VITE_APP_BASE_API 或 `/api/v1`。 */
  base?: string;
  /** 附加请求体（如 session_id / knowledge_ids / model_id）。 */
  buildBody?: () => Record<string, unknown>;
}

type SendOptions = Parameters<ChatTransport<UIMessage>["sendMessages"]>[0];

/** 把 Agno 原生 SSE 事件流转成 AI SDK `UIMessageChunk` 流的自定义传输层。 */
export class AgnoChatTransport implements ChatTransport<UIMessage> {
  constructor(private opts: AgnoChatTransportOptions) {}

  /** Agno 流不可恢复：始终返回 null（无活跃可续传流）。 */
  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }

  async sendMessages(options: SendOptions): Promise<ReadableStream<UIMessageChunk>> {
    const { messages, abortSignal, body, messageId } = options;
    const base = this.opts.base || import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const url = `${base}${this.opts.path}`;
    const msgId = messageId || `asst-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    // 请求体：仅透传 text parts，保留历史对话
    const outbound = messages.map((m) => ({
      role: m.role,
      parts: (m.parts || [])
        .filter((p: any) => p.type === "text")
        .map((p: any) => ({ type: "text", text: String(p.text || "") })),
    }));
    const bodyObj: Record<string, unknown> = { messages: outbound };
    Object.assign(
      bodyObj,
      this.opts.buildBody ? this.opts.buildBody() : {},
      (body as Record<string, unknown>) || {}
    );

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        const ctx: MapCtx = { messageId: msgId, seq: 0 };
        try {
          const res = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
              "X-Forwarded-For": "127.0.0.1",
            },
            body: JSON.stringify(bodyObj),
            signal: abortSignal,
          });
          if (!res.ok || !res.body) {
            throw new Error(`请求失败（HTTP ${res.status}）`);
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder("utf-8");
          let buffer = "";
          let completed = false;
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            // 兼容 LF 与 CRLF 帧分隔（\n\n / \r\n\r\n）
            const frames = buffer.split(/\r?\n\r?\n/);
            buffer = frames.pop() || "";
            for (const raw of frames) {
              const parsed = parseAgnoFrame(raw);
              if (!parsed) continue;
              if (parsed.event === "RunCompleted") completed = true;
              for (const c of mapAgnoEvent(parsed.event, parsed.data, ctx)) {
                controller.enqueue(c);
              }
            }
          }
          // 流自然结束但未收到 RunCompleted：补齐 text/reasoning end 与 finish-step
          if (!completed) {
            for (const c of mapAgnoEvent("RunCompleted", {}, ctx)) {
              controller.enqueue(c);
            }
          }
        } catch (e: any) {
          if (e?.name !== "AbortError") {
            controller.enqueue({ type: "error", errorText: String(e?.message || e) });
          }
        } finally {
          try {
            controller.close();
          } catch {
            /* 已关闭则忽略 */
          }
        }
      },
    });
  }
}
