import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import TimeSeriesCanvas from "./TimeSeriesCanvas.vue";
import { hasTimeSeriesOverlap, isTimeSeriesSegment } from "./useTimeSeriesEventTool";

/**
 * 时间序列事件标注插件（`time_series_event`）。
 * 使用 echarts 折线图渲染序列数据，`markArea` 高亮已标注区间，鼠标拖选生成时间戳 `[start, end)` 的 `TimeSeriesSegment`。
 * 不在 SVG 几何坐标系内进行；区间/类别的编辑 UI 由工作台（Task 8）驱动。
 */
export const timeSeriesEventPlugin: AnnotationTaskPlugin = {
  name: "time_series_event",
  label: "时间序列事件标注",
  color: "primary",
  media: "time_series",
  renderer: TimeSeriesCanvas,
  tools: [{ name: "time_series_event", label: "拖选区间", title: "在折线图上拖选生成时间序列事件" }],
  create(shape: Annotation): boolean {
    const seg = shape as { type?: string; start?: unknown; end?: unknown; label_id?: unknown };
    if (!isTimeSeriesSegment(seg as Annotation)) return false;
    if (typeof seg.start !== "number" || typeof seg.end !== "number") return false;
    if (seg.end <= seg.start) return false;
    if (typeof seg.label_id !== "number") return false;
    return true;
  },
};

export { hasTimeSeriesOverlap, isTimeSeriesSegment };
