import { describe, expect, it } from "vitest";

import {
  buildAgnoBody,
  chatMessagesToBackend,
  flushSurfaceRun,
  mapAgnoFrame,
  newSurfaceCtx,
} from "../agnoSurfaceTransport";

const ctx = () => newSurfaceCtx("m1");

describe("agno → AgentEvent 映射", () => {
  it("RunStarted / RunContent / RunCompleted", () => {
    const c = ctx();
    expect(mapAgnoFrame("RunStarted", {}, c)).toEqual([
      { type: "run.started", messageId: "m1", runId: c.runId },
    ]);
    expect(mapAgnoFrame("RunContent", { content: "你好" }, c)).toEqual([
      { type: "text.delta", text: "你好" },
    ]);
    expect(mapAgnoFrame("RunCompleted", {}, c)).toEqual([{ type: "run.done", status: "done" }]);
    expect(c.finished).toBe(true);
  });

  it("思考内容映射为 reasoning.delta", () => {
    const out = mapAgnoFrame("ReasoningContentDelta", { reasoning_content: "想一下" }, ctx());
    expect(out).toEqual([{ type: "reasoning.delta", text: "想一下" }]);
  });

  it("工具开始映射 tool.start（无 id 时自动生成）", () => {
    const out = mapAgnoFrame(
      "ToolCallStarted",
      { tool: { tool_name: "run_sql", tool_args: { q: "1" } } },
      ctx()
    );
    expect(out).toHaveLength(1);
    const ev: any = out[0];
    expect(ev.type).toBe("tool.start");
    expect(ev.name).toBe("run_sql");
    expect(ev.id).toMatch(/^tool-run_sql-/);
    expect(ev.args).toEqual({ q: "1" });
  });

  it("工具结束：成功带 result，失败带 error", () => {
    const c = ctx();
    mapAgnoFrame("ToolCallStarted", { tool: { tool_name: "run_sql" } }, c);
    const ok = mapAgnoFrame(
      "ToolCallCompleted",
      { tool: { tool_name: "run_sql", result: { rows: 1 } } },
      c
    );
    expect(ok).toEqual([
      { type: "tool.end", id: expect.any(String), status: "done", result: { rows: 1 } },
    ]);

    const c2 = ctx();
    mapAgnoFrame("ToolCallStarted", { tool: { tool_name: "run_sql" } }, c2);
    const bad = mapAgnoFrame(
      "ToolCallCompleted",
      { tool: { tool_name: "run_sql", result: { success: false, error: "权限不足" } } },
      c2
    );
    expect(bad).toEqual([
      { type: "tool.end", id: expect.any(String), status: "error", error: "权限不足" },
    ]);
  });

  it("RunError → run.done(error) 并保留文案", () => {
    const c = ctx();
    expect(mapAgnoFrame("RunError", { error: "模型不可用" }, c)).toEqual([
      { type: "run.done", status: "error", error: "模型不可用" },
    ]);
    expect(c.finished).toBe(true);
  });

  it("流中断时补 run.done(stopped)，且只补一次", () => {
    const c = ctx();
    expect(flushSurfaceRun(c)).toEqual([{ type: "run.done", status: "stopped" }]);
    expect(flushSurfaceRun(c)).toEqual([]);
  });

  it("已正常结束的流不会再补收尾", () => {
    const c = ctx();
    mapAgnoFrame("RunCompleted", {}, c);
    expect(flushSurfaceRun(c)).toEqual([]);
  });
});

describe("请求体契约", () => {
  it("按后端要求发 messages[{role,parts}]，并拼上历史", () => {
    const body: any = buildAgnoBody({ kind: "message", text: "你好" }, [
      { role: "assistant", parts: [{ type: "text", text: "在" }] },
    ]);
    expect(body.messages).toHaveLength(2);
    expect(body.messages[1]).toEqual({
      role: "user",
      parts: [{ type: "text", text: "你好" }],
    });
    expect(body.message).toBeUndefined();
  });
});

describe("历史快照（库的 opts.messages）", () => {
  it("只保留对话文本，丢掉思考与工具轨迹", () => {
    const history = chatMessagesToBackend([
      {
        id: "a",
        role: "assistant",
        createdAt: 0,
        status: "done",
        parts: [
          { id: "r", type: "reasoning", text: "想", status: "done" },
          { id: "t", type: "text", text: "答案" },
          { id: "x", type: "tool", name: "run_sql", status: "done" },
        ],
      } as any,
      {
        id: "u",
        role: "user",
        createdAt: 0,
        status: "done",
        parts: [{ id: "u1", type: "text", text: "问题" }],
      } as any,
      {
        id: "s",
        role: "system",
        createdAt: 0,
        status: "done",
        parts: [{ id: "s1", type: "text", text: "系统" }],
      } as any,
    ]);
    expect(history).toEqual([
      { role: "assistant", parts: [{ type: "text", text: "答案" }] },
      { role: "user", parts: [{ type: "text", text: "问题" }] },
    ]);
  });
});
