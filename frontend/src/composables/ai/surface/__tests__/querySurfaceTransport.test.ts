import { describe, expect, it } from "vitest";

import { flushQueryRun, mapAskFrame, newQueryCtx } from "../querySurfaceTransport";

const ctx = () => newQueryCtx("m1");

describe("问数流 → AgentEvent", () => {
  it("result：SQL 块 + 表格 + 按钮行 + 摘要文本，并把消息 id 对齐后端", () => {
    const c = ctx();
    const out = mapAskFrame(
      "result",
      {
        path: "fast",
        sql: 'SELECT COUNT(*) FROM t',
        columns: ["合同数量"],
        rows: [{ 合同数量: 120 }],
        took_ms: 781,
        summary: "共 120 份合同",
        message_id: 987,
      },
      c,
    );
    const types = out.map((e) => e.type);
    expect(types[0]).toBe("run.started"); // 先对齐 id
    expect((out[0] as any).messageId).toBe("987");
    expect(types).toContain("surface");
    expect(types[types.length - 1]).toBe("text.delta");
    const nodes = out.filter((e) => e.type === "surface").map((e: any) => e.node.type);
    expect(nodes).toContain("code");
    expect(nodes).toContain("table");
    expect(nodes).toContain("row"); // 动作按钮
  });

  it("error：run.done(error) 并保留文案，且不再补收尾", () => {
    const c = ctx();
    expect(mapAskFrame("error", { message: "SQL 校验失败" }, c)).toEqual([
      { type: "run.done", status: "error", error: "SQL 校验失败" },
    ]);
    expect(flushQueryRun(c)).toEqual([]);
  });

  it("clarify：给出「需要补充」提示", () => {
    const out = mapAskFrame("clarify", { clarify: { question: "按哪个矿点？" } }, ctx());
    expect(out[0].type).toBe("surface");
    expect((out[0] as any).node.text).toContain("矿点");
  });

  it("reasoning 与工具事件映射", () => {
    expect(mapAskFrame("reasoning", { delta: "想" }, ctx())).toEqual([
      { type: "reasoning.delta", text: "想" },
    ]);
    expect(
      mapAskFrame("tool_start", { name: "run_sql", id: "t1" }, ctx())[0],
    ).toEqual({ type: "tool.start", id: "t1", name: "run_sql", args: undefined });
    expect(mapAskFrame("tool_error", { name: "run_sql", id: "t1", message: "超时" }, ctx())[0]).toEqual({
      type: "tool.end",
      id: "t1",
      status: "error",
      result: undefined,
      error: "超时",
    });
  });

  it("done 正常结束；中断时补 stopped 只补一次", () => {
    const c = ctx();
    expect(mapAskFrame("done", {}, c)).toEqual([{ type: "run.done", status: "done" }]);
    expect(flushQueryRun(c)).toEqual([]);

    const c2 = ctx();
    expect(flushQueryRun(c2)).toEqual([{ type: "run.done", status: "stopped" }]);
    expect(flushQueryRun(c2)).toEqual([]);
  });
});
