/**
 * AIStation（Vercel AI SDK `UIMessage`）与 agent-surface（`ChatMessage`）之间的双向映射。
 *
 * 用途：
 * - 进：打开历史会话 → `toChatMessages()` 交给 `<AgentSurface :initial-messages>`
 * - 出：`update:messages` 回写 → `toUiMessages()` 交回现有持久化/反馈逻辑
 *
 * 只做「能对上的部分」：source / data-* 这类 AIStation 专有 part 在 surface 里没有对应物，
 * 直接丢弃并**不抛错**（丢一个富文本片段，好过整个会话打不开）。
 */
import type { ChatMessage, Part, TextPart, ReasoningPart, ToolPart } from "agent-surface";
import type { UIMessage } from "ai";

type AnyPart = Record<string, any>;

function partStatus(state: unknown, streaming: boolean): "streaming" | "done" {
  return streaming || state === "streaming" ? "streaming" : "done";
}

function toolStatus(state: unknown): ToolPart["status"] {
  if (state === "output-available") return "done";
  if (state === "output-error") return "error";
  return "running";
}

/** UIMessage[] → ChatMessage[] */
export function toChatMessages(messages: UIMessage[]): ChatMessage[] {
  return (messages || []).map((m, mi) => {
    const streaming = (m as AnyPart).status === "streaming";
    const parts: Part[] = [];
    const rawParts: AnyPart[] = ((m as AnyPart).parts || []) as AnyPart[];

    for (const p of rawParts) {
      if (p.type === "reasoning") {
        const rp: ReasoningPart = {
          id: `${m.id}-r${parts.length}`,
          type: "reasoning",
          text: String(p.text || ""),
          status: partStatus(p.state, streaming),
        };
        if (typeof p.durationMs === "number") rp.durationMs = p.durationMs;
        parts.push(rp);
      } else if (p.type === "text") {
        const tp: TextPart = {
          id: `${m.id}-t${parts.length}`,
          type: "text",
          text: String(p.text || ""),
        };
        parts.push(tp);
      } else if (typeof p.type === "string" && p.type.startsWith("tool-")) {
        const name = p.type.slice(5);
        const st = toolStatus(p.state);
        const tp: ToolPart = {
          id: String(p.toolCallId || `${m.id}-tool${parts.length}`),
          type: "tool",
          name,
          args: p.input,
          status: st,
        };
        if (st === "done") tp.result = p.output;
        if (st === "error") tp.error = String(p.errorText || "工具调用失败");
        parts.push(tp);
      }
      // source-* / data-* / file：surface 无对应物，丢弃
    }

    return {
      id: String(m.id || `m-${mi}`),
      role: (m as AnyPart).role === "user" ? "user" : (m as AnyPart).role === "system" ? "system" : "assistant",
      parts,
      createdAt: Number((m as AnyPart).createdAt) || 0,
      status: streaming ? "streaming" : "done",
    } as ChatMessage;
  });
}

/** ChatMessage[] → UIMessage[]（回写持久化用；surface 的 surface part 转成文本兜底） */
export function toUiMessages(messages: ChatMessage[]): UIMessage[] {
  return (messages || []).map((m) => {
    const parts: AnyPart[] = [];
    for (const p of m.parts || []) {
      if (p.type === "text") {
        parts.push({ type: "text", text: p.text, state: "done" });
      } else if (p.type === "reasoning") {
        parts.push({ type: "reasoning", text: p.text, state: p.status === "streaming" ? "streaming" : "done" });
      } else if (p.type === "tool") {
        const state =
          p.status === "running" ? "input-available" : p.status === "error" ? "output-error" : "output-available";
        parts.push({
          type: `tool-${p.name}`,
          toolCallId: p.id,
          state,
          input: p.args,
          output: p.result,
          errorText: p.error,
        });
      } else if (p.type === "surface") {
        // surface 节点没有 UIMessage 对应物：留一段可读文本，避免回放时完全空白
        parts.push({ type: "text", text: JSON.stringify(p.node), state: "done" });
      }
    }
    return {
      id: m.id,
      role: m.role,
      parts,
    } as unknown as UIMessage;
  });
}
