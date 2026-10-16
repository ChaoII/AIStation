import { computed } from "vue";
import { useChat } from "@ai-sdk/vue";
import { AgnoChatTransport } from "./agnoChatTransport";

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
  /** 附加请求体（如 app_id / session_id / knowledge_ids / model_id）。 */
  body?: () => Record<string, unknown>;
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
  const opts = getOptions();

  const chat = useChat({
    transport: new AgnoChatTransport({
      path: opts.path || "/ai/assistant/stream",
      buildBody: opts.body,
    }),
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
