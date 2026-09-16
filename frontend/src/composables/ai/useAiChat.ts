import { computed } from "vue";
import { useChat } from "@ai-sdk/vue";
import { DefaultChatTransport } from "ai";
import { Auth } from "@/utils/auth";

export interface UseAiChatOptions {
  /** 相对 VITE_APP_BASE_API 的流式路径，默认助手流。 */
  path?: string;
  /** 附加请求体（如 app_id / session_id）。 */
  body?: () => Record<string, unknown>;
}

/**
 * 基于 Vercel AI SDK 的聊天组合式函数（流式 UI Message Stream）。
 *
 * options 可传对象或 getter：传 getter 时内部用 computed 包一层，
 * 仅当其读取的响应式依赖（如所选应用 path）变化时才重建 transport 与聊天实例，
 * 因此可安全切换应用；无参/对象调用保持向后兼容。
 */
export function useAiChat(options: UseAiChatOptions | (() => UseAiChatOptions) = {}) {
  const getOptions = typeof options === "function" ? options : () => options;
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const chatInit = computed(() => {
    const opts = getOptions();
    return {
      transport: new DefaultChatTransport({
        api: `${base}${opts.path || "/ai/assistant/stream"}`,
        headers: { Authorization: `Bearer ${Auth.getAccessToken() || ""}` },
        body: opts.body,
      }),
    };
  });
  return useChat(chatInit);
}
