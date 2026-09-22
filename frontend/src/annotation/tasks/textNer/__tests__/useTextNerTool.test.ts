import { describe, it, expect } from "vitest";
import {
  createEntitySpan,
  hasOverlap,
  findSpanAt,
  spanToRange,
  buildSentenceLineStarts,
  lineIndexOf,
  sameSentence,
} from "../useTextNerTool";
import type { EntitySpan } from "../../../../api/module_annotation/document";

describe("useTextNerTool 文本实体工具", () => {
  it("createEntitySpan 用 UTF-16 偏移切片生成实体（中文安全）", () => {
    const content = "你好世界，文本NER";
    const span = createEntitySpan(content, { from: 1, to: 3 }, 7, "id-1");
    expect(span).toEqual({
      id: "id-1",
      type: "EntitySpan",
      start: 1,
      end: 3,
      label_id: 7,
      text: "好世",
    });
  });

  it("createEntitySpan 未传 id 时自动生成", () => {
    const span = createEntitySpan("hello", { from: 0, to: 2 }, 1);
    expect(span.id).toBeTruthy();
    expect(span.type).toBe("EntitySpan");
  });

  it("createEntitySpan 保留 label_id=0（实体类默认 id 从 0 起）", () => {
    const span = createEntitySpan("你好世界", { from: 0, to: 2 }, 0, "id-0");
    expect(span.label_id).toBe(0);
    expect(span.type).toBe("EntitySpan");
    expect(span.start).toBe(0);
    expect(span.end).toBe(2);
    expect(span.text).toBe("你好");
  });

  it("createEntitySpan 对越界区间做钳制", () => {
    const content = "abcd";
    expect(createEntitySpan(content, { from: -2, to: 100 }, 1, "a").start).toBe(0);
    expect(createEntitySpan(content, { from: -2, to: 100 }, 1, "a").end).toBe(4);
    expect(createEntitySpan(content, { from: 3, to: 1 }, 1, "b").end).toBe(3);
  });

  it("hasOverlap 相邻（仅接触端点）区间不算重叠", () => {
    const spans = [{ start: 0, end: 4, id: "s1" } as EntitySpan];
    expect(hasOverlap(spans, 4, 6)).toBe(false);
    expect(hasOverlap(spans, -2, 0)).toBe(false);
  });

  it("hasOverlap 真正相交的区间判定为重叠", () => {
    const spans = [{ start: 0, end: 4, id: "s1" } as EntitySpan];
    expect(hasOverlap(spans, 3, 5)).toBe(true);
    expect(hasOverlap(spans, -1, 2)).toBe(true);
    expect(hasOverlap(spans, 4, 6)).toBe(false);
  });

  it("findSpanAt 命中光标所在实体，区间外返回 null", () => {
    const spans = [
      { start: 1, end: 4, id: "s1" } as EntitySpan,
      { start: 6, end: 9, id: "s2" } as EntitySpan,
    ];
    expect(findSpanAt(spans, 2)?.id).toBe("s1");
    expect(findSpanAt(spans, 6)?.id).toBe("s2");
    expect(findSpanAt(spans, 4)).toBeNull();
    expect(findSpanAt(spans, 0)).toBeNull();
  });

  it("spanToRange 还原区间", () => {
    const span = { start: 1, end: 3 } as EntitySpan;
    expect(spanToRange(span)).toEqual({ from: 1, to: 3 });
  });

  it("buildSentenceLineStarts 按 \\n 切分并含空行", () => {
    expect(buildSentenceLineStarts("ab\ncd\n\nef")).toEqual([0, 3, 6, 7]);
    expect(buildSentenceLineStarts("")).toEqual([0]);
    expect(buildSentenceLineStarts("abc")).toEqual([0]);
  });

  it("lineIndexOf 二分定位偏移所在行", () => {
    const starts = buildSentenceLineStarts("ab\ncd\n\nef");
    expect(lineIndexOf(starts, 0)).toBe(0);
    expect(lineIndexOf(starts, 2)).toBe(0);
    expect(lineIndexOf(starts, 3)).toBe(1);
    expect(lineIndexOf(starts, 6)).toBe(2);
    expect(lineIndexOf(starts, 7)).toBe(3);
  });

  it("sameSentence 同句为真、跨行为假、空行边界正确", () => {
    const content = "今天天气不错\n上海是座大城市";
    expect(sameSentence(content, { start: 0 }, { start: 4 })).toBe(true);
    expect(sameSentence(content, { start: 1 }, { start: 7 })).toBe(false);
    // 第 2 行开头 offset 6（"上海" 首字符），与第 1 行末尾实体不同句
    expect(sameSentence(content, { start: 7 }, { start: 6 })).toBe(false);
    expect(sameSentence(content, { start: 7 }, { start: 8 })).toBe(true);
  });
});
