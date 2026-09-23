import { describe, it, expect } from "vitest";
import {
  createTimeSeriesSegment,
  hasTimeSeriesOverlap,
  hasOverlapExcluding,
  findOverlappingSegment,
  clampTimeRange,
  segmentToRange,
  isTimeSeriesSegment,
  formatSeriesTime,
} from "../useTimeSeriesEventTool";
import type { TimeSeriesSegment } from "../../../../api/module_annotation/timeSeries";

describe("useTimeSeriesEventTool 时间序列事件工具", () => {
  it("createTimeSeriesSegment 用 start/end/label_id 生成 TimeSeriesSegment", () => {
    const seg = createTimeSeriesSegment(1700000000, 1700000010, 7, "id-a");
    expect(seg).toEqual({
      id: "id-a",
      type: "TimeSeriesSegment",
      start: 1700000000,
      end: 1700000010,
      label_id: 7,
    });
    expect(seg.type).toBe("TimeSeriesSegment");
  });

  it("createTimeSeriesSegment 未传 id 时自动生成", () => {
    const seg = createTimeSeriesSegment(0, 1.2, 0);
    expect(seg.id).toBeTruthy();
    expect(seg.type).toBe("TimeSeriesSegment");
  });

  it("createTimeSeriesSegment 保留 label_id=0（事件类别 id 从 0 起）", () => {
    const seg = createTimeSeriesSegment(2, 4, 0, "id-0");
    expect(seg.label_id).toBe(0);
  });

  it("hasTimeSeriesOverlap 相邻（仅接触端点）区间不算重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as TimeSeriesSegment];
    expect(hasTimeSeriesOverlap(segs, 4, 6)).toBe(false);
    expect(hasTimeSeriesOverlap(segs, -2, 0)).toBe(false);
  });

  it("hasTimeSeriesOverlap 真正相交的区间判定为重叠", () => {
    const segs = [{ start: 0, end: 4, id: "s1" } as TimeSeriesSegment];
    expect(hasTimeSeriesOverlap(segs, 3, 5)).toBe(true);
    expect(hasTimeSeriesOverlap(segs, -1, 2)).toBe(true);
    expect(hasTimeSeriesOverlap(segs, 4, 6)).toBe(false);
  });

  it("hasTimeSeriesOverlap 顺序无关（两个方向均检测）", () => {
    const segs = [{ start: 2, end: 5, id: "s1" } as TimeSeriesSegment];
    expect(hasTimeSeriesOverlap(segs, 4, 6)).toBe(true);
    expect(hasTimeSeriesOverlap(segs, 1, 3)).toBe(true);
    expect(hasTimeSeriesOverlap(segs, 5, 7)).toBe(false);
  });

  it("findOverlappingSegment 返回第一个相交片段，无则 null", () => {
    const segs = [
      { start: 0, end: 2, id: "s1" } as TimeSeriesSegment,
      { start: 3, end: 5, id: "s2" } as TimeSeriesSegment,
    ];
    expect(findOverlappingSegment(segs, 3.5, 4.5)?.id).toBe("s2");
    expect(findOverlappingSegment(segs, 9, 10)).toBeNull();
  });

  it("clampTimeRange 将区间钳制到 [rangeStart, rangeEnd]", () => {
    expect(clampTimeRange(-1, 10, 0, 8)).toEqual({ start: 0, end: 8 });
    expect(clampTimeRange(5, 99, 0, 8)).toEqual({ start: 5, end: 8 });
    expect(clampTimeRange(3, 1, 0, 8)).toEqual({ start: 1, end: 3 });
  });

  it("clampTimeRange start>end 时交换两端", () => {
    expect(clampTimeRange(8, 2, 0, 10)).toEqual({ start: 2, end: 8 });
    expect(clampTimeRange(12, 4, 0, 10)).toEqual({ start: 4, end: 10 });
  });

  it("segmentToRange 还原 {start, end}", () => {
    expect(segmentToRange({ start: 1.5, end: 3.5 } as TimeSeriesSegment)).toEqual({
      start: 1.5,
      end: 3.5,
    });
  });

  it("isTimeSeriesSegment 判别 type 与必备数值字段", () => {
    const seg = createTimeSeriesSegment(0, 1, 1, "a");
    expect(isTimeSeriesSegment(seg)).toBe(true);
    expect(isTimeSeriesSegment({ ...seg, type: "AudioSegment" })).toBe(false);
    expect(isTimeSeriesSegment({ ...seg, end: "x" })).toBe(false);
    expect(isTimeSeriesSegment({ ...seg, start: null })).toBe(false);
    expect(isTimeSeriesSegment(null)).toBe(false);
  });

  it("hasOverlapExcluding 编辑时排除自身片段后判断与其它片段重叠", () => {
    const segs = [
      { id: "s1", start: 0, end: 2 } as TimeSeriesSegment,
      { id: "s2", start: 4, end: 6 } as TimeSeriesSegment,
    ];
    expect(hasOverlapExcluding(segs, "s1", 0, 3)).toBe(false);
    expect(hasOverlapExcluding(segs, "s1", 5, 7)).toBe(true);
    expect(hasOverlapExcluding(segs, "s1", 4.5, 5.5)).toBe(true);
    expect(hasOverlapExcluding(segs, "not-exist", 1, 1.5)).toBe(true);
  });

  it("formatSeriesTime 按时间单位格式化时间戳", () => {
    expect(formatSeriesTime(1700000000, "s")).toBe("1700000000s");
    expect(formatSeriesTime(1700000000500, "ms")).toBe("1700000000500ms");
    expect(formatSeriesTime(NaN, "s")).toBe("-");
  });
});
