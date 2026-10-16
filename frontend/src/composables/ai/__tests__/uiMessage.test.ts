import { describe, it, expect } from "vitest";
import {
  textOf,
  reasoningOf,
  toolPartsOf,
  sourcePartsOf,
  dataPartsOf,
  toolPartsByState,
} from "../uiMessage";

const msg = {
  id: "a",
  role: "assistant",
  parts: [
    { type: "text", text: "你好" },
    { type: "reasoning", text: "先分析", state: "done" },
    {
      type: "tool",
      toolCallId: "t1",
      toolName: "ai_query",
      args: { q: "x" },
      state: "output-available",
      output: { rows: 2 },
    },
    { type: "tool", toolCallId: "t2", toolName: "ai_query", args: {}, state: "input-streaming" },
    { type: "source-url", sourceId: "s1", url: "http://a", title: "来源A" },
    { type: "data-finish", data: { action: { type: "navigate", path: "/x" } }, id: "d1" },
  ],
};

it("textOf 累积 text part", () => expect(textOf(msg)).toBe("你好"));
it("reasoningOf 累积 reasoning part", () => expect(reasoningOf(msg)).toBe("先分析"));
it("toolPartsOf 返回 tool part", () => expect(toolPartsOf(msg).length).toBe(2));
it("sourcePartsOf 返回 source-url/source-document", () => expect(sourcePartsOf(msg).length).toBe(1));
it("dataPartsOf 按 type 取 data", () =>
  expect(dataPartsOf(msg, "data-finish")[0].action.type).toBe("navigate"));
it("toolPartsByState 按 state 分组", () => {
  const g = toolPartsByState(msg);
  expect(g["output-available"].length).toBe(1);
  expect(g["input-streaming"].length).toBe(1);
});
