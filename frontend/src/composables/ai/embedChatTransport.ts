import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { mapAgnoEvent, parseAgnoFrame, type MapCtx } from "./agnoChatTransport";

/**
 * 嵌入对话传输层：Bearer access_token（非 JWT）+ 单消息请求体 + 双协议帧映射。
 *
 * 与 `AgnoChatTransport` 的差异：
 * - 凭证：只带嵌入 `access_token`，绝不带平台 JWT；
 * - 请求体：`{ sid, message }`（上下文在服务端会话，客户端不上传 messages[]）；
 * - 帧映射：兼容 agent/app 的 Agno 事件帧与 workflow 的 AI SDK UI 帧；
 * - 回调：HTTP 状态（401 过期）、文本增量（reply_delta）、附属帧（sources/data-embed）。
 */
export interface EmbedChatTransportOptions {
  /** 相对 base 的流式路径，如 `/ai/embed/run`。 */
  path: string;
  /** API 前缀，默认取 VITE_APP_BASE_API 或 `/api/v1`。 */
  base?: string;
  /** 当前访问令牌（每次请求时读取，支持热替换）。 */
  getToken: () => string;
  /** 附加请求体（`sid`）。 */
  buildBody: () => Record<string, unknown>;
  /** HTTP 非 2xx 回调（401 触发 token_expired 等）。 */
  onHttpError?: (status: number) => void;
  /** 文本增量回调（供 postMessage reply_delta 使用）。 */
  onTextDelta?: (delta: string) => void;
  /** 附属帧回调（sources / data-embed；不进入消息 parts）。 */
  onAuxFrame?: (type: string, data: unknown) => void;
}

type SendOptions = Parameters<ChatTransport<UIMessage>["sendMessages"]>[0];

/** AI SDK UI Message Stream 中可直接透传的帧类型。 */
const UI_PASSTHROUGH = new Set([
  "start",
  "start-step",
  "text-start",
  "text-delta",
  "text-end",
  "reasoning-start",
  "reasoning-delta",
  "reasoning-end",
  "finish-step",
  "finish",
  "error",
]);

/** 附属帧（页面自用，不进 useChat 消息）：sources / data-* / 工具与节点状态。 */
const AUX_PREFIXES = ["data-", "tool-", "node-status", "tool-approval"];

/**
 * 帧分类（纯函数，便于单测）：`ui` 透传 / `aux` 附属 / `agno` 事件转换 / `drop` 丢弃。
 */
export function classifyEmbedFrame(parsed: {
  event: string;
  data: any;
}): "ui" | "aux" | "agno" | "drop" {
  const t = typeof parsed.data?.type === "string" ? parsed.data.type : "";
  if (t && UI_PASSTHROUGH.has(t)) return "ui";
  if (t === "sources" || AUX_PREFIXES.some((p) => t.startsWith(p))) return "aux";
  // 非 type 帧：可能是 Agno 原生事件（event: RunContent 等）
  if (parsed.event && parsed.event !== "message") return "agno";
  if (parsed.data && typeof parsed.data.event === "string") return "agno";
  return "drop";
}

/** 取最后一条用户消息的纯文本（嵌入契约只传这一条）。 */
export function lastUserText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user") continue;
    return (m.parts || [])
      .filter((p: any) => p.type === "text")
      .map((p: any) => String(p.text || ""))
      .join("\n")
      .trim();
  }
  return "";
}

export class EmbedChatTransport implements ChatTransport<UIMessage> {
  constructor(private opts: EmbedChatTransportOptions) {}

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }

  async sendMessages(options: SendOptions): Promise<ReadableStream<UIMessageChunk>> {
    const { messages, abortSignal, messageId } = options;
    const opts = this.opts; // 闭包捕获：ReadableStream.start 内 this 非类实例
    const base = opts.base || import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const url = `${base}${opts.path}`;
    const msgId = messageId || `asst-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const body = {
      message: lastUserText(messages as UIMessage[]),
      ...opts.buildBody(),
    };

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        const ctx: MapCtx = { messageId: msgId, seq: 0 };
        try {
          const res = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${opts.getToken()}`,
            },
            body: JSON.stringify(body),
            signal: abortSignal,
          });
          if (!res.ok || !res.body) {
            opts.onHttpError?.(res.status);
            throw new Error(`请求失败（HTTP ${res.status}）`);
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder("utf-8");
          let buffer = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split(/\r?\n\r?\n/);
            buffer = frames.pop() || "";
            for (const raw of frames) {
              const parsed = parseAgnoFrame(raw);
              if (!parsed) continue;
              // 终止符（data: [DONE]）不会解析成 JSON，直接跳过
              const kind = classifyEmbedFrame(parsed);
              if (kind === "ui") {
                const chunk = parsed.data as UIMessageChunk;
                if ((chunk as any).type === "text-delta") {
                  opts.onTextDelta?.(String((chunk as any).delta || ""));
                }
                controller.enqueue(chunk);
              } else if (kind === "aux") {
                opts.onAuxFrame?.(String(parsed.data?.type || ""), parsed.data);
              } else if (kind === "agno") {
                for (const c of mapAgnoEvent(parsed.event, parsed.data, ctx)) {
                  if (c.type === "text-delta") opts.onTextDelta?.(c.delta);
                  controller.enqueue(c);
                }
              }
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
