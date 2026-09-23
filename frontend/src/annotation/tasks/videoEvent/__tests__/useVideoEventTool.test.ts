import { describe, it, expect } from "vitest";
import {
  createVideoSegment,
  hasVideoEventOverlap,
  hasOverlapExcluding,
  findOverlappingSegment,
  clampVideoRange,
  segmentToRange,
  isVideoSegment,
} from "../useVideoEventTool";
import type { VideoSegment } from "../../../../api/module_annotation/videoEvent";

describe("useVideoEventTool 视频事件工具", () => {
  it("createVideoSegment 用 start/end/label_id 生成 VideoSegment", () => {
    const seg = createVideoSegment(1.5, 3.25, 7, "id-a");
    expect(seg).toEqual({
      id: "id-a",
      type: "VideoSegment",
      start: 1.5,
      end: 3.25,
      label_id: 7,
    });
    expect(seg.type).toBe("VideoSegment");
  });

  it("createVideoSegment 未传 id 时自动生成", () => {
    const seg = createVideoSegment(0, 1.2, 0);
    expect(seg.id).toBeTruthy();
    expect(seg.type).toBe("VideoSegment");
  });

  it("createVideoSegment 保留 label_id=0（事件类别 id 从 0 起）", () => {
    const seg = createVideoSegment(2, 4, 0, "id-0");
    expect(seg.label_id).toBe(0);
  });

  it("hasVideoEventOverlap 相邻（仅接触端点）区间不算重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as VideoSegment];
    expect(hasVideoEventOverlap(segs, 4, 6)).toBe(false);
    expect(hasVideoEventOverlap(segs, -2, 0)).toBe(false);
  });

  it("hasVideoEventOverlap 真正相交的区间判定为重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as VideoSegment];
    expect(hasVideoEventOverlap(segs, 3, 5)).toBe(true);
    expect(hasVideoEventOverlap(segs, -1, 2)).toBe(true);
    expect(hasVideoEventOverlap(segs, 4, 6)).toBe(false);
  });

  it("hasVideoEventOverlap 顺序无关（两个方向均检测）", () => {
    const segs = [{ start: 2, end: 5, id: "s1" } as VideoSegment];
    expect(hasVideoEventOverlap(segs, 4, 6)).toBe(true);
    expect(hasVideoEventOverlap(segs, 1, 3)).toBe(true);
    expect(hasVideoEventOverlap(segs, 5, 7)).toBe(false);
  });

  it("findOverlappingSegment 返回第一个相交片段，无则 null", () => {
    const segs = [
      { start: 0, end: 2, id: "s1" } as VideoSegment,
      { start: 3, end: 5, id: "s2" } as VideoSegment,
    ];
    expect(findOverlappingSegment(segs, 3.5, 4.5)?.id).toBe("s2");
    expect(findOverlappingSegment(segs, 9, 10)).toBeNull();
  });

  it("clampVideoRange 将区间钳制到 [0, duration]", () => {
    expect(clampVideoRange(-1, 10, 8)).toEqual({ start: 0, end: 8 });
    expect(clampVideoRange(5, 99, 8)).toEqual({ start: 5, end: 8 });
    expect(clampVideoRange(3, 1, 8)).toEqual({ start: 1, end: 3 });
  });

  it("segmentToRange 还原 {start, end}", () => {
    expect(segmentToRange({ start: 1.5, end: 3.5 } as VideoSegment)).toEqual({
      start: 1.5,
      end: 3.5,
    });
  });

  it("isVideoSegment 判别 type 与必备数值字段", () => {
    const seg = createVideoSegment(0, 1, 1, "a");
    expect(isVideoSegment(seg)).toBe(true);
    expect(isVideoSegment({ ...seg, type: "EntitySpan" })).toBe(false);
    expect(isVideoSegment({ ...seg, end: "x" })).toBe(false);
    expect(isVideoSegment({ ...seg, start: null })).toBe(false);
  });

  it("hasOverlapExcluding 编辑时排除自身片段后判断与其它片段重叠", () => {
    const segs = [
      { id: "s1", start: 0, end: 2 } as VideoSegment,
      { id: "s2", start: 4, end: 6 } as VideoSegment,
    ];
    expect(hasOverlapExcluding(segs, "s1", 0, 3)).toBe(false);
    expect(hasOverlapExcluding(segs, "s1", 5, 7)).toBe(true);
    expect(hasOverlapExcluding(segs, "s1", 4.5, 5.5)).toBe(true);
    expect(hasOverlapExcluding(segs, "not-exist", 1, 1.5)).toBe(true);
  });
});
