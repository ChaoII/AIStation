import request from "@/utils/request";

export interface AssistantResult {
  reply: string;
  tool_calls: Array<{ name: string; args: any; result: any }>;
  action: {
    type: "navigate" | "confirm";
    path?: string;
    label?: string;
    reason?: string;
    api?: string;
    payload?: any;
  } | null;
  report_id: number | null;
}

export function assistantChat(message: string) {
  return request<ApiResponse<AssistantResult>>({
    url: "/ai/assistant/chat",
    method: "post",
    data: { message },
    headers: { _silent: "true" },
    timeout: 120000,
  });
}
