import { it, expect } from "vitest";
import {
  textOf,
  reasoningOf,
  toolPartsOf,
  toolNameOf,
  isToolPart,
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
    // SDK 静态 tool part 的 type 为 `tool-${toolName}`，且无 toolName 字段
    {
      type: "tool-ai_query",
      toolCallId: "t1",
      args: { q: "x" },
      state: "output-available",
      output: { rows: 2 },
    },
    {
      type: "tool-summary",
      toolCallId: "t2",
      args: {},
      state: "input-streaming",
    },
    { type: "source-url", sourceId: "s1", url: "http://a", title: "来源A" },
    { type: "data-finish", data: { action: { type: "navigate", path: "/x" } }, id: "d1" },
  ],
};

it("textOf 累积 text part", () => expect(textOf(msg)).toBe("你好"));
it("reasoningOf 累积 reasoning part", () => expect(reasoningOf(msg)).toBe("先分析"));
it("toolPartsOf 识别 `tool-${name}` 静态 part", () => expect(toolPartsOf(msg).length).toBe(2));
it("isToolPart 区分 tool-* / dynamic-tool / 非工具", () => {
  expect(isToolPart({ type: "tool-ai_query" })).toBe(true);
  expect(isToolPart({ type: "dynamic-tool", toolName: "ai_query" })).toBe(true);
  expect(isToolPart({ type: "tool" })).toBe(false);
  expect(isToolPart({ type: "text" })).toBe(false);
});
it("toolNameOf 从 `tool-${name}` 推导工具名（静态无 toolName 字段）", () => {
  expect(toolNameOf({ type: "tool-ai_query" })).toBe("ai_query");
  expect(toolNameOf({ type: "dynamic-tool", toolName: "ai_query" })).toBe("ai_query");
});
it("sourcePartsOf 返回 source-url/source-document", () =>
  expect(sourcePartsOf(msg).length).toBe(1));
it("dataPartsOf 按 type 取 data", () =>
  expect(dataPartsOf(msg, "data-finish")[0].action.type).toBe("navigate"));
it("toolPartsByState 按 state 分组", () => {
  const g = toolPartsByState(msg);
  expect(g["output-available"].length).toBe(1);
  expect(g["input-streaming"].length).toBe(1);
});
