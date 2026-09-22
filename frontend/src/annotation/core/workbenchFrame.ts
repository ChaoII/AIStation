/** 视频帧号 → 时间点（秒）。 */
export function frameIndexToTime(idx: number, fps: number): number {
  return idx / fps;
}

/** 时间点（秒） → 视频帧号（四舍五入）。 */
export function timeToFrameIndex(time: number, fps: number): number {
  return Math.round(time * fps);
}
