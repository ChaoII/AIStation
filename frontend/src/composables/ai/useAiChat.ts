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
