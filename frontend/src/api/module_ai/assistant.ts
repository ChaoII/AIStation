import request from "@/utils/request";
import { Auth } from "@/utils/auth";

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

/** SSE 流式助手：逐事件回调（delta/tool/done/error）。 */
export async function assistantStream(
  message: string,
  onEvent: (event: string, data: any) => void
): Promise<void> {
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const token = Auth.getAccessToken() || "";
  const resp = await fetch(`${base}/ai/assistant/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  if (!resp.ok || !resp.body) throw new Error(`请求失败 HTTP ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx = buf.indexOf("\n\n");
    while (idx >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        try {
          onEvent(event, JSON.parse(dataLines.join("\n")));
        } catch {
          /* 忽略非法块 */
        }
      }
      idx = buf.indexOf("\n\n");
    }
  }
}
