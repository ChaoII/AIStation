import { ref } from "vue";
import type { AnnotationTaskPlugin, Annotation, DragContext, Point } from "../../core/types";
import CuboidCanvas from "./CuboidCanvas.vue";
import CuboidPreview from "./CuboidPreview.vue";
import CuboidPanel from "./CuboidPanel.vue";
import { useCuboidTool, cuboidFromEdgeAndPoint } from "./useCuboidTool";

export const cuboidPlugin: AnnotationTaskPlugin = {
  name: "cuboid",
  label: "3D 目标检测",
  color: "danger",
  renderer: CuboidCanvas,
  tools: [
    { name: "cuboid", label: "3D 目标检测", title: "三步拖底部旋转矩形，选中后在面板填深度" },
  ],
  panel: CuboidPanel,
  create(shape: Annotation): boolean {
    if (shape.type !== "Cuboid") return false;
    if (shape.w <= 0 || shape.h <= 0) return false;
    if (shape.cx < 0 || shape.cy < 0 || shape.cx > 1 || shape.cy > 1) return false;
    const half = Math.hypot(shape.w, shape.h) / 2;
    if (shape.cx - half < 0 || shape.cx + half > 1) return false;
    if (shape.cy - half < 0 || shape.cy + half > 1) return false;
    if (shape.depth < 0 || shape.depth > 1) return false;
    if (shape.top_cy < 0 || shape.top_cy > 1) return false;
    return true;
  },
  tool: (() => {
    const cub = useCuboidTool();
    const last = ref<Point | null>(null);
    const preview = ref<any>(null);
    return {
      name: "cuboid",
      preview: CuboidPreview,
      state: { step: cub.step, pt1: cub.pt1, pt2: cub.pt2, last, preview },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        last.value = p;
        const created = cub.onStep(p);
        if (created) preview.value = null;
        return created;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p) return;
        last.value = p;
        if (cub.pt1.value && cub.pt2.value) {
          const g = cuboidFromEdgeAndPoint(cub.pt1.value, cub.pt2.value, p);
          if (g) preview.value = { ...g, pt1: cub.pt1.value, pt2: cub.pt2.value };
        }
      },
      reset() {
        cub.step.value = 0;
        cub.pt1.value = null;
        cub.pt2.value = null;
        last.value = null;
        preview.value = null;
      },
    };
  })(),
  interaction: {
    move(ctx: DragContext): void {
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      ctx.ann.cx = nc(ctx.orig.cx + ctx.dx);
      ctx.ann.cy = nc(ctx.orig.cy + ctx.dy);
      ctx.trigger();
    },
    resize(ctx: DragContext): void {
      const { ann, orig, handle, point, cw, ch } = ctx;
      if (!point) return;
      const aspect = ch / cw;
      const o = orig;
      const cos = Math.cos(o.yaw);
      const sin = Math.sin(o.yaw);
      const fx = handle.includes("l") ? 1 : handle.includes("r") ? -1 : 1;
      const fy = handle.includes("t") ? 1 : handle.includes("b") ? -1 : 1;
      const fix_x = o.cx + ((fx * o.w) / 2) * cos - ((fy * o.h) / 2) * aspect * sin;
      const fix_y = o.cy + ((fx * o.w) / 2 / aspect) * sin + ((fy * o.h) / 2) * cos;
      const newCx = (fix_x + point.x) / 2;
      const newCy = (fix_y + point.y) / 2;
      const dvx = (point.x - newCx) * cw;
      const dvy = (point.y - newCy) * ch;
      const lx = dvx * cos + dvy * sin;
      const ly = -dvx * sin + dvy * cos;
      ann.w = Math.max(0.001, (Math.abs(lx) * 2) / cw);
      ann.h = Math.max(0.001, (Math.abs(ly) * 2) / ch);
      ann.cx = Math.max(0, Math.min(1, newCx));
      ann.cy = Math.max(0, Math.min(1, newCy));
      ctx.trigger();
    },
    rotate(ctx: DragContext): void {
      const { ann, center, start, client } = ctx;
      if (!center || !start || !client) return;
      const prev = Math.atan2(start.y - center.y, start.x - center.x);
      const cur = Math.atan2(client.y - center.y, client.x - center.x);
      ann.yaw = ann.yaw + (cur - prev);
      ctx.trigger();
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const hw = ann.w / 2;
      const hh = ann.h / 2;
      const cos = Math.cos(ann.yaw);
      const sin = Math.sin(ann.yaw);
      return { x: ann.cx + -hw * cos - -hh * sin, y: ann.cy + -hw * sin + -hh * cos };
    },
  },
};
