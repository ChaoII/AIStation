import request from "@/utils/request";

const API_PATH = "/ai/sessions";

/** ai_sessions 会话行（运行时助手/应用持久化，主键为整数） */
export interface AiSessionItem {
  id: number;
  app_id: number | null;
  user_id: number | null;
  title: string;
  message_count: number;
  created_time: string | null;
  updated_time: string | null;
}

/** 会话消息（parts 为 AI SDK 风格分片） */
export interface AiSessionMessage {
  id: number;
  session_id: number;
  app_id: number | null;
  role: string;
  parts: Array<{ type: string; text?: string }>;
  created_time: string | null;
}

export interface AiSessionDetail extends AiSessionItem {
  messages: AiSessionMessage[];
}

export function getAiSessionList(params?: any) {
  return request<ApiResponse<AiSessionItem[]>>({
    url: `${API_PATH}/list`,
    method: "get",
    params,
  });
}

export function getAiSessionDetail(id: number) {
  return request<ApiResponse<AiSessionDetail>>({
    url: `${API_PATH}/detail/${id}`,
    method: "get",
  });
}

export function createAiSession(data: { title?: string; app_id?: number | null }) {
  return request<ApiResponse<AiSessionItem>>({
    url: `${API_PATH}/create`,
    method: "post",
    data,
  });
}

export function deleteAiSessions(ids: number[]) {
  return request({ url: `${API_PATH}/delete`, method: "delete", data: ids });
}
