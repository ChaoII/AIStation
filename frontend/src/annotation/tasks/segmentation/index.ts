import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
import SegmentCanvas from "./SegmentCanvas.vue";

export const segmentationPlugin: AnnotationTaskPlugin = {
  name: "segmentation",
  label: "多边形分割",
  color: "success",
  renderer: SegmentCanvas,
  tools: [{ name: "polygon", label: "多边形", title: "逐点绘制，双击闭合" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Polygon") return false;
    if (!Array.isArray(shape.points) || shape.points.length < 3) return false;
    return shape.points.every((p: any) => 0 <= p.x && p.x <= 1 && 0 <= p.y && p.y <= 1);
  },
  interaction: {
    move(ctx: DragContext): void {
      const movePoints = (pts: any[]) =>
        pts.map((p: any) => ({
          ...p,
          x: Math.max(0, Math.min(1, p.x + ctx.dx)),
          y: Math.max(0, Math.min(1, p.y + ctx.dy)),
        }));
      ctx.ann.points = movePoints(ctx.orig.points);
      ctx.trigger();
    },
    vertexMove(ctx: DragContext): void {
      if (!ctx.point || !ctx.ann.points?.[Number(ctx.handle)]) return;
      ctx.ann.points[Number(ctx.handle)] = {
        ...ctx.ann.points[Number(ctx.handle)],
        x: Math.max(0, Math.min(1, ctx.point.x)),
        y: Math.max(0, Math.min(1, ctx.point.y)),
      };
      ctx.trigger();
    },
    vertexInsert(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      const a = ann.points[idx],
        b = ann.points[(idx + 1) % ann.points.length];
      ann.points.splice(idx + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    },
    vertexDelete(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      if (ann.points.length > 3) ann.points.splice(idx, 1);
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const xs = ann.points.map((p: any) => p.x);
      const ys = ann.points.map((p: any) => p.y);
      return { x: Math.min(...xs), y: Math.min(...ys) };
    },
  },
};
