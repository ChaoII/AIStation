import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
import OcrCanvas from "./OcrCanvas.vue";
import OcrPreview from "./OcrPreview.vue";
import { useOcrTool } from "./useOcrTool";

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
  tool: (() => {
    const ocr = useOcrTool();
    return {
      name: "ocr",
      preview: OcrPreview,
      state: { mode: ocr.mode, quadPoints: ocr.quadPoints },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        if (ocr.mode.value === "quad") {
          ocr.addQuadPoint(p);
          return null;
        }
        return ocr.onPoint(p);
      },
      dblclick(ctx) {
        if (ocr.mode.value === "quad") return ocr.closeQuad();
        return null;
      },
      reset() {
        ocr.reset();
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
    resize(ctx: DragContext): void {
      const { ann, orig, handle, dx, dy } = ctx;
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      const ox = {
        x1: Math.min(...orig.points.map((p: any) => p.x)),
        x2: Math.max(...orig.points.map((p: any) => p.x)),
      };
      const oy = {
        y1: Math.min(...orig.points.map((p: any) => p.y)),
        y2: Math.max(...orig.points.map((p: any) => p.y)),
      };
      let x1 = ox.x1,
        y1 = oy.y1,
        x2 = ox.x2,
        y2 = oy.y2;
      if (handle.includes("l")) x1 = nc(Math.min(x2 - 0.01, x1 + dx));
      if (handle.includes("r")) x2 = nc(Math.max(x1 + 0.01, x2 + dx));
      if (handle.includes("t")) y1 = nc(Math.min(y2 - 0.01, y1 + dy));
      if (handle.includes("b")) y2 = nc(Math.max(y1 + 0.01, y2 + dy));
      ann.points = [
        { x: x1, y: y1 },
        { x: x2, y: y1 },
        { x: x2, y: y2 },
        { x: x1, y: y2 },
      ];
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
    vertexDelete(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      if (ann.points.length > 4) ann.points.splice(idx, 1);
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const xs = ann.points.map((p: any) => p.x);
      const ys = ann.points.map((p: any) => p.y);
      return { x: Math.min(...xs), y: Math.min(...ys) };
    },
  },
};
