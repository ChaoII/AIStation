import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import DetectionCanvas from "./DetectionCanvas.vue";

export const detectionPlugin: AnnotationTaskPlugin = {
  name: "detection",
  label: "目标检测",
  color: "primary",
  renderer: DetectionCanvas,
  tools: [{ name: "box", label: "框选", title: "矩形框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "AxisAlignedBox") return false;
    if (shape.x2 <= shape.x1 || shape.y2 <= shape.y1) return false;
    if (shape.x1 < 0 || shape.y1 < 0 || shape.x2 > 1 || shape.y2 > 1) return false;
    return true;
  },
};
