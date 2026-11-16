/**
 * agno（RunStarted / RunContent / ToolCall* / RunCompleted）→ AgentSurface 的 `AgentEvent`。
 *
 * 为什么单独一层：AIStation 后端有两条协议（agno 与工作流 UI 帧），
 * agent-surface 只认自己的 `AgentEvent`。把映射做成**纯函数**，既能单测，
 * 也能让 4 个对话入口共用，不必各写一遍。
 *
 * 原则：这里只做转发，不写业务；反馈/存报表等由页面接 `feedback`/`action` 事件。
 */
import type { AgentEvent, AgentTransport, SendInput } from "agent-surface";

import { Auth } from "@/utils/auth";
import { parseAgnoFrame } from "../agnoChatTransport";

export interface SurfaceMapCtx {
  /** 当前 assistant 消息 id（AgentSurface 用 run.started 里的 id 定位） */
  messageId: string;
  /** 一次运行的 id（没有就自增） */
  runId: string;
  seq: number;
  /** 是否已收到 run.done（用于流中断时收尾） */
  finished: boolean;
  /** 工具调用：同名多次时按 FIFO 配对 start/end */
  toolIds?: Record<string, string[]>;
}

export function newSurfaceCtx(messageId: string): SurfaceMapCtx {
  return {
    messageId,
    runId: `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq: 0,
    finished: false,
  };
}

function isStr(v: unknown): v is string {
  return typeof v === "string";
}

/** 工具结果里是否表达了失败（与 agnoChatTransport 的判断保持一致） */
function toolResultError(result: unknown): string | null {
  if (result == null) return null;
  if (typeof result === "string") {
    const s = result.trim();
    if (/^(失败|错误|error|Error|ERROR|fail|Fail)/.test(s)) return s;
    return null;
  }
  if (typeof result === "object") {
    const r = result as Record<string, unknown>;
    if (r.success === false || r.ok === false) {
      return String(r.error ?? r.message ?? r.reason ?? "工具调用失败");
    }
    if (r.error || r.__error__) return String(r.error ?? r.__error__);
  }
  return null;
}

/** 单帧映射（纯函数，便于单测） */
export function mapAgnoFrame(event: string, data: any, ctx: SurfaceMapCtx): AgentEvent[] {
  switch (event) {
    case "RunStarted":
      return [{ type: "run.started", messageId: ctx.messageId, runId: ctx.runId }];
    case "ReasoningContentDelta": {
      const text = isStr(data?.reasoning_content) ? data.reasoning_content : "";
      return text ? [{ type: "reasoning.delta", text }] : [];
    }
    case "RunContent": {
      const text = isStr(data?.content) ? data.content : "";
      return text ? [{ type: "text.delta", text }] : [];
    }
    case "ToolCallStarted": {
      const tool = (data?.tool || {}) as Record<string, unknown>;
      const name = String(tool.tool_name ?? tool.toolName ?? "工具");
      const provided = String(tool.tool_call_id ?? tool.toolCallId ?? "");
      const id = provided || `tool-${name}-${++ctx.seq}`;
      (ctx.toolIds ||= {})[name] = [...(ctx.toolIds[name] || []), id];
      return [
        {
          type: "tool.start",
          id,
          name,
          args: tool.tool_args ?? tool.input,
        },
      ];
    }
    case "ToolCallCompleted": {
      const tool = (data?.tool || {}) as Record<string, unknown>;
      const name = String(tool.tool_name ?? tool.toolName ?? "工具");
      const provided = String(tool.tool_call_id ?? tool.toolCallId ?? "");
      const queue = ctx.toolIds?.[name];
      const id = provided || (queue?.length ? queue.shift()! : `tool-${name}-${++ctx.seq}`);
      const result = tool.result ?? tool.output;
      const err = toolResultError(result);
      return [
        err
          ? { type: "tool.end", id, status: "error", error: err }
          : { type: "tool.end", id, status: "done", result },
      ];
    }
    case "RunError":
      ctx.finished = true;
      return [
        {
          type: "run.done",
          status: "error",
          error: String(data?.error ?? data?.message ?? "运行失败"),
        },
      ];
    case "RunCompleted":
      ctx.finished = true;
      return [{ type: "run.done", status: "done" }];
    default:
      return [];
  }
}

/** 流被中断（没收到 RunCompleted/RunError）时，必须补一个收尾事件，否则消息永远停在 streaming */
export function flushSurfaceRun(ctx: SurfaceMapCtx, status: "stopped" | "done" = "stopped"): AgentEvent[] {
  if (ctx.finished) return [];
  ctx.finished = true;
  return [{ type: "run.done", status }];
}

export interface AgnoSurfaceTransportOptions {
  /** 相对 base 的路径，如 `/ai/assistant/stream` 或 `/ai/agents/3/run/stream` */
  path: string;
  /** 每次请求动态构造的 body（会话 id、模型、知识库等） */
  buildBody?: () => Record<string, unknown>;
  /** 历史消息（`{role, parts}` 形式），后端要用它做多轮上下文 */
  buildMessages?: () => Array<Record<string, unknown>>;
  /** 额外请求头 */
  headers?: () => Record<string, string>;
}

/** 把 surface 的发送输入转成 AIStation 后端的 `messages` 契约
 *
 * 后端（`/assistant/stream`、`/agents/{id}/run/stream`、`/apps/{id}/run/stream`）
 * 都要 `messages: [{role, parts:[{type:"text", text}]}]`；
 * 早先按 `{message: text}` 发送会被判「输入不能为空」——实测踩过。
 */
export function buildAgnoBody(
  input: SendInput,
  history: Array<Record<string, unknown>> = []
): Record<string, unknown> {
  const text =
    input.kind === "message"
      ? input.text
      : String((input as Record<string, unknown>).displayText ?? "");
  const userMsg = { role: "user", parts: [{ type: "text", text }] };
  return { messages: [...history, userMsg] };
}

/** 把 agno SSE 端点包成 AgentSurface 可消费的 transport */
export class AgnoSurfaceTransport implements AgentTransport {
  constructor(private readonly opts: AgnoSurfaceTransportOptions) {}

  async *stream(input: SendInput, runOpts?: { signal?: AbortSignal }): AsyncGenerator<AgentEvent> {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const token = Auth.getAccessToken();
    const body = {
      ...buildAgnoBody(input, this.opts.buildMessages?.() || []),
      ...(this.opts.buildBody?.() || {}),
    };

    const resp = await fetch(`${base}${this.opts.path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(this.opts.headers?.() || {}),
      },
      body: JSON.stringify(body),
      signal: runOpts?.signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`请求失败（${resp.status}）`);
    }

    const ctx = newSurfaceCtx(`msg-${Date.now()}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE 以空行分隔帧
        let idx = buffer.indexOf("\n\n");
        while (idx >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const frame = parseAgnoFrame(raw);
          if (frame) {
            for (const ev of mapAgnoFrame(frame.event, frame.data, ctx)) yield ev;
            if (ctx.finished) return;
          }
          idx = buffer.indexOf("\n\n");
        }
      }
      for (const ev of flushSurfaceRun(ctx, "done")) yield ev;
    } finally {
      for (const ev of flushSurfaceRun(ctx, "stopped")) yield ev;
    }
  }
}
