import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import AudioTimelineCanvas from "./AudioTimelineCanvas.vue";
import { hasAudioOverlap, isAudioSegment, clampAudioRange } from "./useAudioEventTool";

/**
 * 音频事件标注插件（`audio_event`）。
 * 使用 wavesurfer.js v7 + regions 插件渲染波形，拖选生成秒级 `[start, end)` 的 `AudioSegment`，
 * 不在 SVG 几何坐标系内进行；区间/类别的编辑 UI 由工作台（Task 8）驱动。
 */
export const audioEventPlugin: AnnotationTaskPlugin = {
  name: "audio_event",
  label: "音频事件标注",
  color: "primary",
  media: "audio",
  renderer: AudioTimelineCanvas,
  tools: [{ name: "audio_event", label: "拖选区间", title: "在波形上拖选生成音频事件" }],
  create(shape: Annotation): boolean {
    const seg = shape as { type?: string; start?: unknown; end?: unknown; label_id?: unknown };
    if (!isAudioSegment(seg as Annotation)) return false;
    if (typeof seg.start !== "number" || typeof seg.end !== "number") return false;
    if (seg.end <= seg.start) return false;
    if (typeof seg.label_id !== "number") return false;
    return true;
  },
};

export { hasAudioOverlap, isAudioSegment, clampAudioRange };
