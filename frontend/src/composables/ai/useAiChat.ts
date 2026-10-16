import { computed, unref, type MaybeRef } from "vue";
import { useChat } from "@ai-sdk/vue";
import type { UIMessage } from "ai";
import { AgnoChatTransport } from "./agnoChatTransport";

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
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
  const transport = new AgnoChatTransport({
    path: baseOpts.path || "/ai/assistant/stream",
    buildBody: baseOpts.body,
  });

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

  const isStreaming = computed(
    () => status.value === "submitted" || status.value === "streaming"
  );

  async function sendMessage(input: { text: string }) {
    await chat.sendMessage({ text: input.text });
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
