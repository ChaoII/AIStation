import { computed, unref, type MaybeRef } from "vue";
import { useChat } from "@ai-sdk/vue";
import type { UIMessage } from "ai";
import { EmbedChatTransport } from "./embedChatTransport";

/** 嵌入对话组合式函数选项。 */
export interface UseEmbedChatOptions {
  /** 当前访问令牌（热替换续期）。 */
  getToken: () => string;
  /** 附加请求体（`sid`）。 */
  buildBody: () => Record<string, unknown>;
  /** 会话标识（useChat 的 chat id；meta 就绪后才有值）。 */
  id?: MaybeRef<string | number | null | undefined>;
  /** 初始历史消息（刷新恢复）。 */
  initialMessages?: MaybeRef<UIMessage[]>;
  onHttpError?: (status: number) => void;
  onTextDelta?: (delta: string) => void;
  onAuxFrame?: (type: string, data: unknown) => void;
}

/**
 * 嵌入对话：`useChat` + `EmbedChatTransport`（token 鉴权、单消息契约）。
 * 返回形状与 `useAiChat` 对齐（status: ready/submitted/streaming/error）。
 */
export function useEmbedChat(options: UseEmbedChatOptions) {
  const transport = new EmbedChatTransport({
    path: "/ai/embed/run",
    getToken: options.getToken,
    buildBody: options.buildBody,
    onHttpError: options.onHttpError,
    onTextDelta: options.onTextDelta,
    onAuxFrame: options.onAuxFrame,
  });

  const chat = useChat(() => {
    const chatId = unref(options.id);
    const initMsgs = unref(options.initialMessages);
    return {
      id: chatId != null ? String(chatId) : undefined,
      messages: (initMsgs || []) as UIMessage[],
      transport,
    };
  });

  const status = computed(() => chat.status.value);
  const error = computed<string | null>(() => chat.error.value?.message || null);
  const isStreaming = computed(() => status.value === "submitted" || status.value === "streaming");

  async function sendMessage(input: { text: string }) {
    await chat.sendMessage({ text: input.text });
  }

  function stop() {
    chat.stop();
  }

  return { messages: chat.messages, status, error, isStreaming, sendMessage, stop };
}
