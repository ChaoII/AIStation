import { describe, expect, it } from "vitest";

import { toChatMessages, toUiMessages } from "../messageMap";

const ui = (parts: any[], role = "assistant", status = "done") =>
  ({ id: "m1", role, parts, status }) as any;

describe("UIMessage ↔ ChatMessage", () => {
  it("user 文本 → 一个 text part", () => {
    const [m] = toChatMessages([ui([{ type: "text", text: "你好" }], "user")]);
    expect(m.role).toBe("user");
    expect(m.parts).toEqual([{ id: expect.any(String), type: "text", text: "你好" }]);
    expect(m.status).toBe("done");
  });

  it("assistant 的 reasoning / text / tool 按序映射", () => {
    const [m] = toChatMessages([
      ui([
        { type: "reasoning", text: "想一想", state: "done" },
        { type: "text", text: "答案", state: "done" },
        { type: "tool-run_sql", toolCallId: "t1", state: "output-available", input: { q: 1 }, output: { rows: 2 } },
      ]),
    ]);
    expect(m.parts.map((p) => p.type)).toEqual(["reasoning", "text", "tool"]);
    const tool: any = m.parts[2];
    expect(tool.name).toBe("run_sql");
    expect(tool.status).toBe("done");
    expect(tool.result).toEqual({ rows: 2 });
  });

  it("工具失败 → status=error 且保留错误文案", () => {
    const [m] = toChatMessages([
      ui([{ type: "tool-run_sql", toolCallId: "t1", state: "output-error", errorText: "权限不足" }]),
    ]);
    const tool: any = m.parts[0];
    expect(tool.status).toBe("error");
    expect(tool.error).toBe("权限不足");
  });

  it("未知 part（source/data）被丢弃但不抛错", () => {
    const [m] = toChatMessages([
      ui([
        { type: "source-url", url: "http://x" },
        { type: "data-weather", data: { t: 1 } },
        { type: "text", text: "只剩我" },
      ]),
    ]);
    expect(m.parts).toHaveLength(1);
    expect((m.parts[0] as any).text).toBe("只剩我");
  });

  it("回写：text/reasoning/tool 能还原为 UIMessage parts", () => {
    const back = toUiMessages([
      {
        id: "m1",
        role: "assistant",
        createdAt: 0,
        status: "done",
        parts: [
          { id: "a", type: "text", text: "答案" },
          { id: "b", type: "reasoning", text: "想", status: "done" },
          { id: "c", type: "tool", name: "run_sql", status: "done", result: { rows: 1 } },
        ],
      } as any,
    ]);
    const types = (back[0] as any).parts.map((p: any) => p.type);
    expect(types).toEqual(["text", "reasoning", "tool-run_sql"]);
    expect((back[0] as any).parts[2].state).toBe("output-available");
  });
});
