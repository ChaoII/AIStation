import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
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
  interaction: {
    move(ctx: DragContext): void {
      const { ann, orig, dx, dy } = ctx;
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      ann.x1 = nc(orig.x1 + dx);
      ann.x2 = nc(orig.x2 + dx);
      ann.y1 = nc(orig.y1 + dy);
      ann.y2 = nc(orig.y2 + dy);
      ctx.trigger();
    },
    resize(ctx: DragContext): void {
      const { ann, orig, handle, dx, dy } = ctx;
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      if (handle.includes("l")) ann.x1 = nc(Math.min(orig.x2 - 0.01, orig.x1 + dx));
      if (handle.includes("r")) ann.x2 = nc(Math.max(orig.x1 + 0.01, orig.x2 + dx));
      if (handle.includes("t")) ann.y1 = nc(Math.min(orig.y2 - 0.01, orig.y1 + dy));
      if (handle.includes("b")) ann.y2 = nc(Math.max(orig.y1 + 0.01, orig.y2 + dy));
      ctx.trigger();
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      return { x: ann.x1, y: ann.y1 };
    },
  },
};
