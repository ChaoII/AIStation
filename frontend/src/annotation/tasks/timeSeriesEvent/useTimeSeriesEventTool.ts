import type { TimeSeriesSegment } from "../../../api/module_annotation/timeSeries";

/** 时间序列时间区间（时间戳），`[start, end)` 左闭右开。 */
export interface TimeRange {
  start: number;
  end: number;
}

/**
 * 由区间参数生成一个时间序列事件片段标注。
 * `start`/`end` 为序列时间列的时间戳（`time_unit` 决定的单位），`[start, end)`；`label_id` 归属任务事件类别。
 */
export function createTimeSeriesSegment(
  start: number,
  end: number,
  labelId: number,
  id?: string
): TimeSeriesSegment {
  return {
    id: id ?? crypto.randomUUID(),
    type: "TimeSeriesSegment",
    start,
    end,
    label_id: labelId,
  };
}

/**
 * 判断新区间 `[start, end)` 是否与已有任一时间序列片段相交。
 * 相邻（`start === s.end` 或 `end === s.start`）不算重叠。
 */
export function hasTimeSeriesOverlap(
  segments: readonly Pick<TimeSeriesSegment, "start" | "end">[],
  start: number,
  end: number
): boolean {
  return segments.some((s) => start < s.end && end > s.start);
}

/**
 * 判断新区间 `[start, end)` 是否与「除 excludeId 之外」的其它片段重叠。
 * 用于编辑片段时排除自身，避免「自身与自身重叠」的误判。
 */
export function hasOverlapExcluding(
  segments: readonly Pick<TimeSeriesSegment, "id" | "start" | "end">[],
  excludeId: string,
  start: number,
  end: number
): boolean {
  return hasTimeSeriesOverlap(
    segments.filter((s) => s.id !== excludeId),
    start,
    end
  );
}

/**
 * 返回与新区间 `[start, end)` 重叠的第一个片段（用于提示冲突来源）。
 */
export function findOverlappingSegment(
  segments: readonly TimeSeriesSegment[],
  start: number,
  end: number
): TimeSeriesSegment | null {
  return segments.find((s) => start < s.end && end > s.start) ?? null;
}

/**
 * 将区间钳制到 `[rangeStart, rangeEnd]`（序列时间范围），并在 `start > end` 时交换两端。
 */
export function clampTimeRange(
  start: number,
  end: number,
  rangeStart: number,
  rangeEnd: number
): TimeRange {
  let s = Math.max(rangeStart, Math.min(rangeEnd, start));
  let e = Math.max(rangeStart, Math.min(rangeEnd, end));
  if (s > e) [s, e] = [e, s];
  return { start: s, end: e };
}

/** 还原片段为 `{start, end}` 区间（供外层工具/面板使用）。 */
export function segmentToRange(segment: Pick<TimeSeriesSegment, "start" | "end">): TimeRange {
  return { start: segment.start, end: segment.end };
}

/** 判别对象是否为一个合法时间序列片段（type 与必备数值字段）。 */
export function isTimeSeriesSegment(value: unknown): value is TimeSeriesSegment {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    v.type === "TimeSeriesSegment" &&
    typeof v.start === "number" &&
    typeof v.end === "number" &&
    typeof v.label_id === "number"
  );
}
