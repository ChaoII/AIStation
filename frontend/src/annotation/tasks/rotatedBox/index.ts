import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
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
      const cos = Math.cos(o.angle);
      const sin = Math.sin(o.angle);
      const fx = handle.includes("l") ? 1 : handle.includes("r") ? -1 : 1;
      const fy = handle.includes("t") ? 1 : handle.includes("b") ? -1 : 1;
      const fix_x = o.cx + ((fx * o.width) / 2) * cos - ((fy * o.height) / 2) * aspect * sin;
      const fix_y = o.cy + ((fx * o.width) / 2 / aspect) * sin + ((fy * o.height) / 2) * cos;
      const newCx = (fix_x + point.x) / 2;
      const newCy = (fix_y + point.y) / 2;
      const dvx = (point.x - newCx) * cw;
      const dvy = (point.y - newCy) * ch;
      const lx = dvx * cos + dvy * sin;
      const ly = -dvx * sin + dvy * cos;
      ann.width = Math.max(0.001, (Math.abs(lx) * 2) / cw);
      ann.height = Math.max(0.001, (Math.abs(ly) * 2) / ch);
      ann.cx = Math.max(0, Math.min(1, newCx));
      ann.cy = Math.max(0, Math.min(1, newCy));
      ctx.trigger();
    },
    rotate(ctx: DragContext): void {
      const { ann, center, start, client } = ctx;
      if (!center || !start || !client) return;
      const prev = Math.atan2(start.y - center.y, start.x - center.x);
      const cur = Math.atan2(client.y - center.y, client.x - center.x);
      ann.angle = JSON.parse(JSON.stringify(ann)).angle + (cur - prev);
      ctx.trigger();
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const hw = ann.width / 2,
        hh = ann.height / 2;
      const cos = Math.cos(ann.angle),
        sin = Math.sin(ann.angle);
      return { x: ann.cx + -hw * cos - -hh * sin, y: ann.cy + -hw * sin + -hh * cos };
    },
  },
};
