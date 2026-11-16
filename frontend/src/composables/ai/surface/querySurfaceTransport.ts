/**
 * 问数流（`/ai/query/ask/stream`）→ AgentSurface 的 `AgentEvent`。
 *
 * 与 agno 那套的区别：问数事件是**业务事件**（reasoning / sql_delta / result / clarify），
 * 所以这里要把 SQL、结果表、路径标签、耗时都转成 surface 节点；否则界面上只剩一句话。
 *
 * 另一个关键点：`result.message_id` 是后端消息 id。拿到后补一个 `run.started` 把消息 id
 * **改成后端 id**——这样组件发出的 `feedback.messageId` 能直接对上库里那条消息
 * （库的协议文档明确：run.started 给的 id 就是 feedback 的 id）。
 */
import type {
  AgentEvent,
  AgentStreamOptions,
  AgentTransport,
  SendInput,
  SurfaceNode,
} from "agent-surface";

import { Auth } from "@/utils/auth";
import { parseAgnoFrame } from "../agnoChatTransport";
import { buildQuerySurface } from "./querySurface";

export interface QueryMapCtx {
  messageId: string;
  runId: string;
  finished: boolean;
  applied: string[];
}

export function newQueryCtx(messageId: string): QueryMapCtx {
  return {
    messageId,
    runId: `q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    finished: false,
    applied: [],
  };
}

/** 结果区按钮：由页面接 `action` 事件（kind="event"）执行原逻辑 */
function actionRow(): SurfaceNode {
  return {
    type: "row",
    gap: "sm",
    children: [
      { type: "button", label: "执行详情", action: { kind: "event", value: "trace" } },
      {
        type: "button",
        label: "存为报表",
        action: { kind: "event", value: "report" },
        variant: "secondary",
      },
      {
        type: "button",
        label: "沉淀指标",
        action: { kind: "event", value: "promote" },
        variant: "secondary",
      },
    ],
  };
}

/** 单帧映射（纯函数，便于单测） */
export function mapAskFrame(type: string, data: any, ctx: QueryMapCtx): AgentEvent[] {
  switch (type) {
    case "run_start":
      return [{ type: "run.started", messageId: ctx.messageId, runId: ctx.runId }];
    case "reasoning":
      return data?.delta ? [{ type: "reasoning.delta", text: String(data.delta) }] : [];
    case "tool_start":
      return [
        {
          type: "tool.start",
          id: String(data?.id ?? data?.tool_call_id ?? `tool-${data?.name ?? "sql"}`),
          name: String(data?.name ?? "工具"),
          args: data?.args,
        },
      ];
    case "tool_result":
    case "tool_error":
      return [
        {
          type: "tool.end",
          id: String(data?.id ?? data?.tool_call_id ?? `tool-${data?.name ?? "sql"}`),
          status: type === "tool_error" ? "error" : "done",
          result: data?.result,
          error:
            type === "tool_error" ? String(data?.message ?? data?.error ?? "工具失败") : undefined,
        },
      ];
    case "result": {
      const nodes = buildQuerySurface({
        sql: data?.sql || "",
        rows: data?.rows || [],
        columns: data?.columns || [],
        path: data?.path || "",
        metric: data?.metric,
        took_ms: typeof data?.took_ms === "number" ? data.took_ms : undefined,
      });
      // 有 SQL/结果才给动作按钮（空结果给按钮没意义）
      if (data?.sql) nodes.push(actionRow());
      const out: AgentEvent[] = [];
      // 先把消息 id 对齐到后端 id（feedback 才能对上库里的消息）
      if (data?.message_id) {
        out.push({ type: "run.started", messageId: String(data.message_id), runId: ctx.runId });
      }
      for (const node of nodes) out.push({ type: "surface", node });
      if (data?.summary) out.push({ type: "text.delta", text: String(data.summary) });
      return out;
    }
    case "clarify": {
      const q = data?.clarify?.question || data?.clarify?.text || "需要补充信息";
      return [
        {
          type: "surface",
          node: { type: "callout", tone: "info", title: "需要补充", text: String(q) },
        },
      ];
    }
    case "error":
      ctx.finished = true;
      return [{ type: "run.done", status: "error", error: String(data?.message ?? "查询失败") }];
    case "done":
      ctx.finished = true;
      return [{ type: "run.done", status: "done" }];
    default:
      return [];
  }
}

/** 流中断时收尾（问数同样不能停在 streaming） */
export function flushQueryRun(ctx: QueryMapCtx): AgentEvent[] {
  if (ctx.finished) return [];
  ctx.finished = true;
  return [{ type: "run.done", status: "stopped" }];
}

export interface QuerySurfaceTransportOptions {
  /** 默认 `/ai/query/ask/stream` */
  path?: string;
  /** 每次请求动态构造（question 之外的字段：datasource / session_id / object_code） */
  buildBody?: () => Record<string, unknown>;
  /** 拿到 result 时回调（页面用它开「执行详情 / 存报表 / 沉淀指标」） */
  onResult?: (data: Record<string, any>) => void;
}

export class QuerySurfaceTransport implements AgentTransport {
  constructor(private readonly opts: QuerySurfaceTransportOptions = {}) {}

  async *stream(input: SendInput, runOpts?: AgentStreamOptions): AsyncGenerator<AgentEvent> {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const token = Auth.getAccessToken();
    const question =
      input.kind === "message" ? input.text : String((input as any).displayText ?? "");
    const body = { question, ...(this.opts.buildBody?.() || {}) };

    const resp = await fetch(`${base}${this.opts.path || "/ai/query/ask/stream"}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: runOpts?.signal,
    });
    if (!resp.ok || !resp.body) throw new Error(`请求失败（${resp.status}）`);

    const ctx = newQueryCtx(`q-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx = buffer.indexOf("\n\n");
        while (idx >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const frame = parseAgnoFrame(raw);
          if (frame) {
            if (frame.event === "result" && frame.data) this.opts.onResult?.(frame.data);
            for (const ev of mapAskFrame(frame.event, frame.data, ctx)) yield ev;
            if (ctx.finished) return;
          }
          idx = buffer.indexOf("\n\n");
        }
      }
      // 正常 EOF：没收到 done 也补一个，避免消息卡在 streaming
      for (const ev of flushQueryRun(ctx)) yield ev;
    } finally {
      for (const ev of flushQueryRun(ctx)) yield ev;
    }
  }
}
