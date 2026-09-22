import { describe, it, expect } from "vitest";
import {
  createAudioSegment,
  hasAudioOverlap,
  hasOverlapExcluding,
  findOverlappingSegment,
  clampAudioRange,
  segmentToRange,
  isAudioSegment,
  hasSegmentWithId,
} from "../useAudioEventTool";
import type { AudioSegment } from "../../../../api/module_annotation/audio";

describe("useAudioEventTool 音频事件工具", () => {
  it("createAudioSegment 用 start/end/label_id 生成 AudioSegment", () => {
    const seg = createAudioSegment(1.5, 3.25, 7, "id-a");
    expect(seg).toEqual({
      id: "id-a",
      type: "AudioSegment",
      start: 1.5,
      end: 3.25,
      label_id: 7,
    });
    expect(seg.type).toBe("AudioSegment");
  });

  it("createAudioSegment 未传 id 时自动生成", () => {
    const seg = createAudioSegment(0, 1.2, 0);
    expect(seg.id).toBeTruthy();
    expect(seg.type).toBe("AudioSegment");
  });

  it("createAudioSegment 保留 label_id=0（事件类别 id 从 0 起）", () => {
    const seg = createAudioSegment(2, 4, 0, "id-0");
    expect(seg.label_id).toBe(0);
  });

  it("hasAudioOverlap 相邻（仅接触端点）区间不算重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as AudioSegment];
    expect(hasAudioOverlap(segs, 4, 6)).toBe(false);
    expect(hasAudioOverlap(segs, -2, 0)).toBe(false);
  });

  it("hasAudioOverlap 真正相交的区间判定为重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as AudioSegment];
    expect(hasAudioOverlap(segs, 3, 5)).toBe(true);
    expect(hasAudioOverlap(segs, -1, 2)).toBe(true);
    expect(hasAudioOverlap(segs, 4, 6)).toBe(false);
  });

  it("hasAudioOverlap 顺序无关（两个方向均检测）", () => {
    const segs = [{ start: 2, end: 5, id: "s1" } as AudioSegment];
    expect(hasAudioOverlap(segs, 4, 6)).toBe(true);
    expect(hasAudioOverlap(segs, 1, 3)).toBe(true);
    expect(hasAudioOverlap(segs, 5, 7)).toBe(false);
  });

  it("findOverlappingSegment 返回第一个相交片段，无则 null", () => {
    const segs = [
      { start: 0, end: 2, id: "s1" } as AudioSegment,
      { start: 3, end: 5, id: "s2" } as AudioSegment,
    ];
    expect(findOverlappingSegment(segs, 3.5, 4.5)?.id).toBe("s2");
    expect(findOverlappingSegment(segs, 9, 10)).toBeNull();
  });

  it("clampAudioRange 将区间钳制到 [0, duration]", () => {
    expect(clampAudioRange(-1, 10, 8)).toEqual({ start: 0, end: 8 });
    expect(clampAudioRange(5, 99, 8)).toEqual({ start: 5, end: 8 });
    expect(clampAudioRange(3, 1, 8)).toEqual({ start: 1, end: 3 });
  });

  it("segmentToRange 还原 {start, end}", () => {
    expect(segmentToRange({ start: 1.5, end: 3.5 } as AudioSegment)).toEqual({
      start: 1.5,
      end: 3.5,
    });
  });

  it("isAudioSegment 判别 type 与必备数值字段", () => {
    const seg = createAudioSegment(0, 1, 1, "a");
    expect(isAudioSegment(seg)).toBe(true);
    expect(isAudioSegment({ ...seg, type: "EntitySpan" })).toBe(false);
    expect(isAudioSegment({ ...seg, end: "x" })).toBe(false);
    expect(isAudioSegment({ ...seg, start: null })).toBe(false);
  });

  it("hasSegmentWithId 判定 region id 是否已存在于外部 segments（同步产生）", () => {
    const segs = [
      { id: "s1", start: 0, end: 1 } as AudioSegment,
      { id: "s2", start: 2, end: 3 } as AudioSegment,
    ];
    // 已存在的 id → 视为同步产生，不应触发 createRegion
    expect(hasSegmentWithId(segs, "s1")).toBe(true);
    expect(hasSegmentWithId(segs, "s2")).toBe(true);
    // 新 id → 拖选产生，应移除并触发 createRegion
    expect(hasSegmentWithId(segs, "region-x")).toBe(false);
    // 空 / undefined segments 均返回 false
    expect(hasSegmentWithId([], "s1")).toBe(false);
    expect(hasSegmentWithId(undefined, "s1")).toBe(false);
  });

  it("hasOverlapExcluding 编辑时排除自身片段后判断与其它片段重叠", () => {
    const segs = [
      { id: "s1", start: 0, end: 2 } as AudioSegment,
      { id: "s2", start: 4, end: 6 } as AudioSegment,
    ];
    // 排除自身后，区间落在其它片段间隙内不算重叠
    expect(hasOverlapExcluding(segs, "s1", 0, 3)).toBe(false);
    // 与其它片段相交则判定重叠
    expect(hasOverlapExcluding(segs, "s1", 5, 7)).toBe(true);
    expect(hasOverlapExcluding(segs, "s1", 4.5, 5.5)).toBe(true);
    // 与不存在的 id 视为不排除任何片段
    expect(hasOverlapExcluding(segs, "not-exist", 1, 1.5)).toBe(true);
  });
});
