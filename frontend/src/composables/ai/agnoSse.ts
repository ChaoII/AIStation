/**
 * Agno 原生 SSE 帧读取器（前端消费层）。
 *
 * 后端 /assistant/stream、/apps/{id}/run/stream、/agents/{id}/run/stream 均直出
 * Agno 原生事件流：``event: <RunEvent>\ndata: {event, ...}\n\n``。
 * 本工具用 fetch 的 ReadableStream 逐帧解析为 ``{ event, data }``，
 * 供各消费方（聊天页 useAiChat、应用/智能体管理页的「运行」调试面板、
 * 智能体试跑/内嵌对话）统一消费，避免各自手写旧 AI SDK 协议解析。
 */
export interface AgnoFrame {
  /** 事件名，如 RunStarted / RunContent / ReasoningContentDelta / ToolCall* / RunError / RunCompleted。 */
  event: string;
  /** 事件负载（含 content / reasoning_content / tool / error 等字段）。 */
  data: Record<string, unknown>;
}

/** 逐帧读取 Agno 原生 SSE 事件的异步生成器。 */
export async function* readAgnoFrames(res: Response): AsyncGenerator<AgnoFrame> {
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以空行分隔帧
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const rawFrame of frames) {
      if (!rawFrame.trim()) continue;
      let event = "message";
      const dataLines: string[] = [];
      for (const line of rawFrame.split("\n")) {
        const s = line.replace(/\r$/, "");
        if (s.startsWith(":")) continue;
        if (s.startsWith("event:")) event = s.slice(6).trim();
        else if (s.startsWith("data:")) dataLines.push(s.slice(5).trim());
      }
      if (!dataLines.length) continue;
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataLines.join("\n"));
      } catch {
        continue;
      }
      if (event === "message" && data.event) event = String(data.event);
      yield { event, data };
    }
  }
}

/** 从 Agno 工具事件里提取工具名 / 参数（兼容 tool_name / tool_args 命名）。 */
export function agnoToolInfo(data: Record<string, unknown>): {
  name: string;
  args?: unknown;
  result?: unknown;
} {
  const tool = (data.tool || {}) as Record<string, unknown>;
  const name = String(tool.tool_name ?? tool.toolName ?? data.tool_name ?? "工具");
  return {
    name,
    args: tool.tool_args ?? tool.input ?? data.tool_args,
    result: tool.result ?? data.result,
  };
}
