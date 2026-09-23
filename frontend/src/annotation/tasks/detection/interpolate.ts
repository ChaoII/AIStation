import type { Annotation } from "../../core/types";

/**
 * 视频关键帧线性插值纯函数。
 * 归一化坐标约定与 AxisAlignedBox 一致（[0,1]）。
 */

/** 单个关键帧：帧序号 + 该帧含目标 track 的框。 */
export interface InterpolateKeyframe {
  frameIndex: number;
  box: Annotation;
}

/** 插值生成的中间帧框（具体坐标 + 继承 track_id/class_id）。 */
export interface InterpolatedBox {
  id: string;
  type: "AxisAlignedBox";
  class_id: number;
  track_id?: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** 插值输出的单个中间帧：帧序号 + 该帧插值生成的框列表。 */
export interface InterpolateFrameResult {
  frame_index: number;
  annotations: InterpolatedBox[];
}

/**
 * 对同一 track_id 的两个关键帧之间的中间帧做线性插值。
 *
 * 对每个请求的中间帧 `k`，计算 `t=(k-frameA.frameIndex)/(frameB.frameIndex-frameA.frameIndex)`，
 * 依 `axis_k = axis_A + (axis_B - axis_A) * t` 插值 x1/y1/x2/y2，并继承
 * track_id / class_id / type。跳过与关键帧重合的帧（关键帧本身不生成）。
 *
 * @param frameA 关键帧 A（帧号需小于 frameB.frameIndex）
 * @param frameB 关键帧 B
 * @param interpolateFrames 要插值的中间帧号列表（跳过等于任一关键帧的帧）
 * @returns 仅中间帧的 `[{frame_index, annotations}]` 列表
 */
export function interpolateBoxes(
  frameA: InterpolateKeyframe,
  frameB: InterpolateKeyframe,
  interpolateFrames: number[]
): InterpolateFrameResult[] {
  const span = frameB.frameIndex - frameA.frameIndex;
  if (span <= 0) return [];
  const a = frameA.box;
  const b = frameB.box;
  return interpolateFrames
    .filter((k) => k !== frameA.frameIndex && k !== frameB.frameIndex)
    .map((k) => {
      const t = (k - frameA.frameIndex) / span;
      return {
        frame_index: k,
        annotations: [
          {
            id: crypto.randomUUID(),
            type: "AxisAlignedBox" as const,
            class_id: a.class_id,
            track_id: a.track_id,
            x1: a.x1 + (b.x1 - a.x1) * t,
            y1: a.y1 + (b.y1 - a.y1) * t,
            x2: a.x2 + (b.x2 - a.x2) * t,
            y2: a.y2 + (b.y2 - a.y2) * t,
          },
        ],
      };
    });
}
