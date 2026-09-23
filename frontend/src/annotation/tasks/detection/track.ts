import type { Annotation, Point } from "../../core/types";

/**
 * 轨迹相关纯函数（视频目标跟踪 track_id 关联/轨迹路径/导航）。
 * 归一化坐标约定与 AxisAlignedBox 一致（[0,1]）。
 */

/** 归一化框中心点。 */
export function boxCenter(a: Annotation): Point {
  return { x: (a.x1 + a.x2) / 2, y: (a.y1 + a.y2) / 2 };
}

/** 归一化框四角点（左上/右上/右下/左下）。 */
export function boxCorners(a: Annotation): Point[] {
  return [
    { x: a.x1, y: a.y1 },
    { x: a.x2, y: a.y1 },
    { x: a.x2, y: a.y2 },
    { x: a.x1, y: a.y2 },
  ];
}

/** 按 track_id 分组（跳过无 track_id 的框）。 */
export function groupByTrack(boxes: Annotation[]): Record<string, Annotation[]> {
  const map: Record<string, Annotation[]> = {};
  for (const b of boxes) {
    if (!b.track_id) continue;
    (map[b.track_id] ??= []).push(b);
  }
  return map;
}

/** 收集出现的 track_id（去重，保序）。 */
export function collectTrackIds(boxes: Annotation[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const b of boxes) {
    if (b.track_id && !seen.has(b.track_id)) {
      seen.add(b.track_id);
      out.push(b.track_id);
    }
  }
  return out;
}

/** 新建轨迹 id。 */
export function newTrackId(): string {
  return crypto.randomUUID();
}

/** 在某帧框集合中查找含指定 track_id 的框。 */
export function findBoxByTrack(boxes: Annotation[], trackId: string): Annotation | undefined {
  return boxes.find((b) => b.track_id === trackId);
}

/** 轨迹路径：按给定帧序的框，取其中心点连成折线。 */
export function trackPath(orderedBoxes: Annotation[]): Point[] {
  return orderedBoxes.map(boxCenter);
}

/** 跨帧轨迹点位：输入按帧序的 {frameIndex, box} 列表，按帧序排序后返回中心点。 */
export function trackPathFromFrames(
  frames: { frameIndex: number; box: Annotation }[]
): { frameIndex: number; point: Point }[] {
  return [...frames]
    .sort((a, b) => a.frameIndex - b.frameIndex)
    .map((f) => ({ frameIndex: f.frameIndex, point: boxCenter(f.box) }));
}

/** 在给定轨迹出现帧列表中，找相对当前帧的前一/后一帧（无则 null）。 */
export function nearestTrackFrame(frames: number[], current: number, dir: 1 | -1): number | null {
  const sorted = [...frames].sort((a, b) => a - b);
  if (dir > 0) {
    const next = sorted.find((f) => f > current);
    return next ?? null;
  }
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (sorted[i] < current) return sorted[i];
  }
  return null;
}

/** 轨迹色板：按 track_id 哈希取色，同一 track 恒同色。 */
const TRACK_PALETTE = [
  "#409eff",
  "#67c23a",
  "#e6a23c",
  "#f56c6c",
  "#9b59b6",
  "#00bcd4",
  "#ff9800",
  "#795548",
  "#e91e63",
  "#8bc34a",
];

/** 按 track_id 哈希到色板颜色。 */
export function trackColor(trackId: string): string {
  let h = 0;
  for (let i = 0; i < trackId.length; i++) h = (h * 31 + trackId.charCodeAt(i)) >>> 0;
  return TRACK_PALETTE[h % TRACK_PALETTE.length];
}
