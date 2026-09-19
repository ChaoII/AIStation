import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import OcrCanvas from "./OcrCanvas.vue";

export const ocrPlugin: AnnotationTaskPlugin = {
  name: "ocr",
  label: "OCR 文本",
  color: "info",
  renderer: OcrCanvas,
  tools: [{ name: "ocr", label: "OCR", title: "框选文字区域" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Ocr") return false;
    const pts = shape.points || [];
    if (pts.length < 4) return false;
    return pts.every((p: any) => 0 <= p.x && p.x <= 1 && 0 <= p.y && p.y <= 1);
  },
};
