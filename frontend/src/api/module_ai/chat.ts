import request from "@/utils/request";

const API_PATH = "/ai/chat";

/** /ai/chat 仅保留非流式对话执行；会话管理（列表/详情/新建/重命名/删除）统一走 /ai/sessions。 */
export const AiChatAPI = {
  chat(body: { message: string; session_id?: number | null }) {
    return request<ApiResponse<AiChatResponse>>({
      url: `${API_PATH}/ai-chat`,
      method: "post",
      data: body,
    });
  },
};

export default AiChatAPI;

export interface AiChatResponse {
  response: string;
  session_id: number;
  function_calls: Array<{
    name: string;
    arguments: Record<string, any>;
  }> | null;
}
