import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import KeypointCanvas from "./KeypointCanvas.vue";

export const keypointPlugin: AnnotationTaskPlugin = {
  name: "keypoint",
  label: "关键点",
  color: "danger",
  renderer: KeypointCanvas,
  tools: [{ name: "keypoint", label: "关键点", title: "依次放点，双击后拉出包围框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Keypoint") return false;
    const kps = shape.keypoints || [];
    if (kps.length === 0) return false;
    return kps.every((k: any) => 0 <= k.x && k.x <= 1 && 0 <= k.y && k.y <= 1);
  },
};
