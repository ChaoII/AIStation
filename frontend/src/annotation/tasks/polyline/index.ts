import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
import PolylineCanvas from "./PolylineCanvas.vue";
import PolylinePreview from "./PolylinePreview.vue";
import { usePolylineTool } from "./usePolylineTool";

export const polylinePlugin: AnnotationTaskPlugin = {
  name: "polyline",
  label: "折线",
  color: "warning",
  renderer: PolylineCanvas,
  tools: [{ name: "polyline", label: "折线", title: "逐点绘制折线，双击结束" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Polyline") return false;
    if (!Array.isArray(shape.points) || shape.points.length < 2) return false;
    return shape.points.every((p: any) => 0 <= p.x && p.x <= 1 && 0 <= p.y && p.y <= 1);
  },
  tool: (() => {
    const line = usePolylineTool();
    return {
      name: "polyline",
      preview: PolylinePreview,
      state: { points: line.points },
      down(ctx) {
        const p = ctx.point;
        if (p) line.addPoint(p);
        return null;
      },
      dblclick() {
        return line.finish();
      },
      reset() {
        line.points.value = [];
      },
    };
  })(),
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
      if (idx + 1 >= ann.points.length) return; // 开放折线：末尾不循环插入
      const a = ann.points[idx];
      const b = ann.points[idx + 1];
      ann.points.splice(idx + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    },
    vertexDelete(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      if (ann.points.length > 2) ann.points.splice(idx, 1);
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const xs = ann.points.map((p: any) => p.x);
      const ys = ann.points.map((p: any) => p.y);
      return { x: Math.min(...xs), y: Math.min(...ys) };
    },
  },
};
