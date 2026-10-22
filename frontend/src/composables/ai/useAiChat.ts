import { computed, unref, type MaybeRef } from "vue";
import { useChat } from "@ai-sdk/vue";
import type { ChatTransport, UIMessage, ChatRequestOptions } from "ai";
import { DefaultChatTransport } from "ai";
import { Auth } from "@/utils/auth";
import { AgnoChatTransport } from "./agnoChatTransport";

/** 随消息上传的文件载荷（data URL）。 */
export interface AiChatFilePayload {
  name: string;
  type: string;
  dataUrl: string;
}

/** 引用个人空间文件的载荷（后端 _process_uploaded_files 按 type=workspace 处理）。 */
export interface AiChatWorkspaceFilePayload {
  type: "workspace";
  file_id: number;
  name: string;
}

export type AiChatAnyFilePayload = AiChatFilePayload | AiChatWorkspaceFilePayload;

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
  /**
   * 帧协议：
   * - `agno`（默认）：Agno 原生事件流（assistant / agent / app 的 run 端点）；
   * - `ui`：AI SDK UI Message Stream（workflow 端点，编排帧 node-status/data-run 等
   *   依赖此协议）—— 由 SDK 原生 `DefaultChatTransport` 消费。
   */
  protocol?: "agno" | "ui";
  /** 附加请求体（如 app_id / session_id / knowledge_ids / model_id）。 */
  body?: () => Record<string, unknown>;
  /** 会话 id（useChat 的 chat id），支持响应式（切换会话时重建）。 */
  id?: MaybeRef<string | number | null>;
  /** 初始历史消息（切换会话时用于恢复）。 */
  initialMessages?: MaybeRef<UIMessage[]>;
}

/**
 * 基于 Vercel AI SDK `useChat` + 自定义 `AgnoChatTransport` 的聊天组合式函数。
 *
 * 保留既有调用方（AiAssistant / chat 页）的签名与返回形状：
 * - `messages`：SDK 标准 `UIMessage[]`（按 parts 渲染）。
 * - `status`：兼容旧枚举 `ready | submitted | streaming | error`（`generating → submitted`）。
 * - `error`、`isStreaming`、`sendMessage({text})`、`stop`、`regenerate`。
 */
export function useAiChat(options: UseAiChatOptions | (() => UseAiChatOptions) = {}) {
  const getOptions = typeof options === "function" ? options : () => options;
  // transport 固定（path/body 稳定）；body 为函数，每次请求时动态读取会话/知识等
  const baseOpts = getOptions();
  const apiBase = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const apiPath = baseOpts.path || "/ai/assistant/stream";
  const transport: ChatTransport<UIMessage> =
    baseOpts.protocol === "ui"
      ? // UI Message Stream：SDK 原生 DefaultChatTransport（与后端 ui_stream_response 对齐）
        new DefaultChatTransport<UIMessage>({
          api: `${apiBase}${apiPath}`,
          prepareSendMessagesRequest: ({ messages, body }) => ({
            body: {
              // 仅透传 text parts，与 AgnoChatTransport 出参保持一致
              messages: messages.map((m) => ({
                role: m.role,
                parts: (m.parts || [])
                  .filter((p: any) => p.type === "text")
                  .map((p: any) => ({ type: "text", text: String(p.text || "") })),
              })),
              ...(baseOpts.body ? baseOpts.body() : {}),
              ...((body as Record<string, unknown>) || {}),
            },
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
              "X-Forwarded-For": "127.0.0.1",
            },
          }),
        })
      : new AgnoChatTransport({ path: apiPath, buildBody: baseOpts.body });

  const chat = useChat(() => {
    const o = getOptions();
    const chatId = unref(o.id);
    const initMsgs = unref(o.initialMessages);
    return {
      id: chatId != null ? String(chatId) : undefined,
      messages: (initMsgs || []) as UIMessage[],
      transport,
    };
  });

  // useChat 的 ChatStatus 与旧枚举一致（submitted/streaming/ready/error），直接透传
  const status = computed(() => chat.status.value);

  const error = computed<string | null>(() => chat.error.value?.message || null);

  const isStreaming = computed(() => status.value === "submitted" || status.value === "streaming");

  async function sendMessage(input: { text: string; files?: AiChatAnyFilePayload[] }) {
    const opts: ChatRequestOptions = {};
    if (input.files?.length) opts.body = { files: input.files };
    await chat.sendMessage({ text: input.text }, opts);
  }

  function stop() {
    chat.stop();
  }

  async function regenerate() {
    await chat.regenerate();
  }

  return {
    messages: chat.messages,
    status,
    error,
    isStreaming,
    sendMessage,
    stop,
    regenerate,
  };
}
