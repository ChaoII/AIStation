import { describe, it, expect } from "vitest";
import { mapAgnoEvent } from "../agnoChatTransport";

/** 每次测试用独立 ctx，避免共享状态污染。 */
const makeCtx = (messageId = "m1") => ({ messageId, seq: 0 });

it("RunContent 首次 → text-start + text-delta（无 end，end 由 RunCompleted 补）", () => {
  const ctx = makeCtx();
  const out = mapAgnoEvent("RunContent", { content: "Hi" }, ctx);
  expect(out.map((c) => c.type)).toEqual(["text-start", "text-delta"]);
  expect(out[1]).toMatchObject({ type: "text-delta", delta: "Hi" });
});
it("RunContent 连续 → 仅 text-delta（增量累积）", () => {
  const ctx = makeCtx();
  mapAgnoEvent("RunContent", { content: "Hi" }, ctx);
  const out = mapAgnoEvent("RunContent", { content: " there" }, ctx);
  expect(out.map((c) => c.type)).toEqual(["text-delta"]);
});
it("ReasoningContentDelta 首次 → reasoning-start + reasoning-delta", () => {
  const ctx = makeCtx();
  const out = mapAgnoEvent("ReasoningContentDelta", { reasoning_content: "分析" }, ctx);
  expect(out.map((c) => c.type)).toEqual(["reasoning-start", "reasoning-delta"]);
});
it("ReasoningContentDelta 连续 → 仅 reasoning-delta", () => {
  const ctx = makeCtx();
  mapAgnoEvent("ReasoningContentDelta", { reasoning_content: "分析" }, ctx);
  const out = mapAgnoEvent("ReasoningContentDelta", { reasoning_content: "中" }, ctx);
  expect(out.map((c) => c.type)).toEqual(["reasoning-delta"]);
});
it("ToolCallStarted → tool-input-available（生成 id 防缺失）", () => {
  const ctx = makeCtx();
  const out = mapAgnoEvent(
    "ToolCallStarted",
    { tool: { tool_name: "ai_query", tool_args: { q: "x" } } },
    ctx
  );
  expect(out[0]).toMatchObject({
    type: "tool-input-available",
    toolName: "ai_query",
    input: { q: "x" },
  });
  expect((out[0] as any).toolCallId).toBeTruthy();
});
it("ToolCallCompleted → tool-output-available（与 input 同 id）", () => {
  const ctx = makeCtx();
  const started = mapAgnoEvent(
    "ToolCallStarted",
    { tool: { tool_name: "ai_query", tool_args: {} } },
    ctx
  );
  const tid = (started[0] as any).toolCallId;
  const out = mapAgnoEvent(
    "ToolCallCompleted",
    { tool: { tool_name: "ai_query", tool_call_id: tid, result: { rows: 1 } } },
    ctx
  );
  expect(out[0]).toMatchObject({
    type: "tool-output-available",
    toolCallId: tid,
    output: { rows: 1 },
  });
});
it("RunError → error chunk", () => {
  expect(mapAgnoEvent("RunError", { error: "boom" }, makeCtx())[0]).toMatchObject({
    type: "error",
    errorText: "boom",
  });
});
it("RunStarted → start-step；RunCompleted（无文本时）→ finish-step", () => {
  expect(mapAgnoEvent("RunStarted", {}, makeCtx())).toEqual([{ type: "start-step" }]);
  expect(mapAgnoEvent("RunCompleted", {}, makeCtx())).toEqual([{ type: "finish-step" }]);
});
it("RunCompleted（文本进行中）→ 先补 text-end + finish-step", () => {
  const ctx = makeCtx();
  mapAgnoEvent("RunContent", { content: "Hi" }, ctx);
  const out = mapAgnoEvent("RunCompleted", {}, ctx);
  expect(out.map((c) => c.type)).toEqual(["text-end", "finish-step"]);
});
it("未知事件类型返回空（跳过不中断）", () => {
  expect(mapAgnoEvent("FooEvent", {}, makeCtx())).toEqual([]);
});
it("content 非字符串跳过 text（解析失败容错）", () => {
  expect(mapAgnoEvent("RunContent", { content: 123 }, makeCtx())).toEqual([]);
});
