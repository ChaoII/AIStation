import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import SegmentCanvas from "./SegmentCanvas.vue";

export const segmentationPlugin: AnnotationTaskPlugin = {
  name: "segmentation",
  label: "图像分割",
  color: "success",
  renderer: SegmentCanvas,
  tools: [{ name: "polygon", label: "多边形", title: "逐点画多边形，双击闭合" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Polygon") return false;
    const pts = shape.points || [];
    if (pts.length < 3) return false;
    return pts.every((p: any) => 0 <= p.x && p.x <= 1 && 0 <= p.y && p.y <= 1);
  },
};
