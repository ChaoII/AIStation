import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import ClassificationCanvas from "./ClassificationCanvas.vue";

export const classificationPlugin: AnnotationTaskPlugin = {
  name: "classification",
  label: "图像分类",
  color: "primary",
  renderer: ClassificationCanvas,
  tools: [],
  create(shape: Annotation): boolean {
    if (shape.type !== "Classification") return false;
    if (Array.isArray(shape.class_ids) && shape.class_ids.length) return true;
    return typeof shape.class_id === "number" && shape.class_id >= 0;
  },
};
