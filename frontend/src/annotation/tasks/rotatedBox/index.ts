import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import RotatedBoxCanvas from "./RotatedBoxCanvas.vue";

export const rotatedBoxPlugin: AnnotationTaskPlugin = {
  name: "rotated_detection",
  label: "旋转框检测",
  color: "warning",
  renderer: RotatedBoxCanvas,
  tools: [{ name: "rotated_box", label: "旋转框", title: "三步旋转框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "RotatedBox") return false;
    if (shape.width <= 0 || shape.height <= 0) return false;
    if (shape.cx < 0 || shape.cy < 0 || shape.cx > 1 || shape.cy > 1) return false;
    const half = Math.hypot(shape.width, shape.height) / 2;
    if (shape.cx - half < 0 || shape.cx + half > 1 || shape.cy - half < 0 || shape.cy + half > 1)
      return false;
    return true;
  },
};
