import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import VideoTimelineCanvas from "./VideoTimelineCanvas.vue";
import { hasVideoEventOverlap, isVideoSegment, clampVideoRange } from "./useVideoEventTool";

/**
 * 视频时间轴事件标注插件（`video_event`）。
 * 使用纯时间轴（`0..duration` 秒）渲染区间，鼠标拖选生成秒级 `[start, end)` 的 `VideoSegment`，
 * 不渲染波形；区间/类别的编辑 UI 由工作台（Task 8）驱动。
 */
export const videoEventPlugin: AnnotationTaskPlugin = {
  name: "video_event",
  label: "视频事件标注",
  color: "primary",
  media: "video",
  renderer: VideoTimelineCanvas,
  tools: [{ name: "video_event", label: "拖选区间", title: "在时间轴上拖选生成视频事件" }],
  create(shape: Annotation): boolean {
    const seg = shape as { type?: string; start?: unknown; end?: unknown; label_id?: unknown };
    if (!isVideoSegment(seg as Annotation)) return false;
    if (typeof seg.start !== "number" || typeof seg.end !== "number") return false;
    if (seg.end <= seg.start) return false;
    if (typeof seg.label_id !== "number") return false;
    return true;
  },
};

export { hasVideoEventOverlap, isVideoSegment, clampVideoRange };
