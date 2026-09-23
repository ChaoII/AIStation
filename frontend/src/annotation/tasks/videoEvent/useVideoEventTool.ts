import type { VideoSegment } from "../../../api/module_annotation/videoEvent";

/** 视频时间区间（秒），`[start, end)` 左闭右开。 */
export interface VideoRange {
  start: number;
  end: number;
}

/**
 * 由区间参数生成一个视频事件片段标注。
 * `start`/`end` 为视频时间轴秒级浮点，`[start, end)`；`label_id` 归属任务事件类别。
 */
export function createVideoSegment(
  start: number,
  end: number,
  labelId: number,
  id?: string
): VideoSegment {
  return {
    id: id ?? crypto.randomUUID(),
    type: "VideoSegment",
    start,
    end,
    label_id: labelId,
  };
}

/**
 * 判断新区间 `[start, end)` 是否与已有任一视频片段相交。
 * 相邻（`start === s.end` 或 `end === s.start`）不算重叠。
 */
export function hasVideoEventOverlap(
  segments: readonly Pick<VideoSegment, "start" | "end">[],
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
  segments: readonly Pick<VideoSegment, "id" | "start" | "end">[],
  excludeId: string,
  start: number,
  end: number
): boolean {
  return hasVideoEventOverlap(
    segments.filter((s) => s.id !== excludeId),
    start,
    end
  );
}

/**
 * 返回与新区间 `[start, end)` 重叠的第一个片段（用于提示冲突来源）。
 */
export function findOverlappingSegment(
  segments: readonly VideoSegment[],
  start: number,
  end: number
): VideoSegment | null {
  return segments.find((s) => start < s.end && end > s.start) ?? null;
}

/**
 * 将区间钳制到 `[0, duration]`，并在 `start > end` 时交换两端。
 */
export function clampVideoRange(start: number, end: number, duration: number): VideoRange {
  let s = Math.max(0, Math.min(duration, start));
  let e = Math.max(0, Math.min(duration, end));
  if (s > e) [s, e] = [e, s];
  return { start: s, end: e };
}

/** 还原片段为 `{start, end}` 区间（供外层工具/面板使用）。 */
export function segmentToRange(segment: Pick<VideoSegment, "start" | "end">): VideoRange {
  return { start: segment.start, end: segment.end };
}

/** 判别对象是否为一个合法视频片段（type 与必备数值字段）。 */
export function isVideoSegment(value: unknown): value is VideoSegment {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    v.type === "VideoSegment" &&
    typeof v.start === "number" &&
    typeof v.end === "number" &&
    typeof v.label_id === "number"
  );
}
