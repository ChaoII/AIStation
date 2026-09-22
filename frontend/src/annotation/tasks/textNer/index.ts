import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import TextNerCanvas from "./TextNerCanvas.vue";
import { createEntitySpan, hasOverlap } from "./useTextNerTool";

/**
 * 文本实体关系标注插件（`text_ner`）。
 * 使用 CodeMirror 6 只读文本渲染，拖动选区生成字符级 `EntitySpan`，
 * 不依赖 SVG 几何坐标系；实体/关系的编辑 UI 由工作台（Task 8）驱动。
 */
export const textNerPlugin: AnnotationTaskPlugin = {
  name: "text_ner",
  label: "文本实体关系标注",
  color: "primary",
  media: "text",
  renderer: TextNerCanvas,
  tools: [{ name: "text", label: "拖选", title: "拖选文本生成实体" }],
  create(shape: Annotation): boolean {
    if ((shape as { type?: string }).type !== "EntitySpan") return false;
    if (!Number.isInteger(shape.start) || !Number.isInteger(shape.end)) return false;
    if (shape.end <= shape.start) return false;
    if (shape.label_id == null) return false;
    return true;
  },
};

export { createEntitySpan, hasOverlap };
