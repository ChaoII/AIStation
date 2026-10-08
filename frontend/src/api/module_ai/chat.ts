import request from "@/utils/request";

const API_PATH = "/ai/chat";

export const AiChatAPI = {
  getSessionList(query: {
    page_no: number;
    page_size: number;
    title?: string;
    created_at?: string[];
    updated_at?: string[];
  }) {
    return request<ApiResponse<PageResult<ChatSession[]>>>({
      url: `${API_PATH}/list`,
      method: "get",
      params: query,
    });
  },

  chat(body: { message: string; session_id?: number | null }) {
    return request<ApiResponse<AiChatResponse>>({
      url: `${API_PATH}/ai-chat`,
      method: "post",
      data: body,
    });
  },

  getSessionDetail(sessionId: number) {
    return request<ApiResponse<ChatSessionDetail>>({
      url: `${API_PATH}/detail/${sessionId}`,
      method: "get",
    });
  },
};

export default AiChatAPI;

export interface ChatSessionMessage {
  id: string;
  role: string;
  content: string;
  created_at: number | null;
}

export interface ChatSession {
  id: number;
  session_id: number;
  team_name: string | null;
  title: string | null;
  created_time: string | null;
  updated_time: string | null;
  message_count: number;
  messages: ChatSessionMessage[];
}

export interface UserInfo {
  id: number;
  name: string;
  username: string;
  avatar: string;
  email: string;
}

export interface AiChatResponse {
  response: string;
  session_id: number;
  function_calls: Array<{
    name: string;
    arguments: Record<string, any>;
  }> | null;
}

export interface ChatSessionDetail {
  id: number;
  session_id: number;
  team_name: string | null;
  title: string | null;
  created_time: string | null;
  updated_time: string | null;
  message_count: number;
  messages: ChatSessionMessage[];
}
