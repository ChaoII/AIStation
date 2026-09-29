import { ref } from "vue";
import type { AnnotationTaskPlugin, Annotation, DragContext, Point } from "../../core/types";
import RotatedBoxCanvas from "./RotatedBoxCanvas.vue";
import RotatedBoxPreview from "./RotatedBoxPreview.vue";
import { useRotatedTool, rotatedBoxFromEdgeAndPoint } from "./useRotatedTool";

export const rotatedBoxPlugin: AnnotationTaskPlugin = {
  name: "rotated_detection",
  label: "旋转框检测",
  color: "warning",
  renderer: RotatedBoxCanvas,
  tools: [{ name: "rotated_box", label: "旋转框", title: "三步旋转框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "RotatedBox") return false;
    if (shape.width <= 0 || shape.height <= 0) return false;
    // 仅约束中心在图像附近并给边缘留出缓冲，允许旋转框稍微超出图像边缘，
    // 避免在靠近边缘处「第三步拖动绘制不出来」。
    if (shape.cx < -0.25 || shape.cx > 1.25 || shape.cy < -0.25 || shape.cy > 1.25) return false;
    return true;
  },
  tool: (() => {
    const rot = useRotatedTool();
    const last = ref<Point | null>(null);
    const preview = ref<any>(null);
    return {
      name: "rotated_box",
      preview: RotatedBoxPreview,
      state: { step: rot.step, pt1: rot.pt1, pt2: rot.pt2, last, preview },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        last.value = p;
        const created = rot.onStep(p, ctx.cw ?? 1, ctx.ch ?? 1);
        if (created) preview.value = null;
        return created;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p) return;
        last.value = p;
        if (rot.pt1.value && rot.pt2.value) {
          const g = rotatedBoxFromEdgeAndPoint(rot.pt1.value, rot.pt2.value, p, ctx.cw ?? 1, ctx.ch ?? 1);
          if (g) preview.value = { ...g };
        }
      },
      reset() {
        rot.step.value = 0;
        rot.pt1.value = null;
        rot.pt2.value = null;
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
      const o = orig;
      const cos = Math.cos(o.angle);
      const sin = Math.sin(o.angle);
      const fx = handle.includes("l") ? 1 : handle.includes("r") ? -1 : 1;
      const fy = handle.includes("t") ? 1 : handle.includes("b") ? -1 : 1;
      // 像素(viewBox)空间计算，避免非方形图片在归一化坐标下旋转/缩放错位
      const hw = (o.width * cw) / 2;
      const hh = (o.height * ch) / 2;
      const fixX = o.cx * cw + (fx * hw) * cos - (fy * hh) * sin;
      const fixY = o.cy * ch + (fx * hw) * sin + (fy * hh) * cos;
      const mx = point.x * cw;
      const my = point.y * ch;
      const newCxPx = (fixX + mx) / 2;
      const newCyPx = (fixY + my) / 2;
      const dvx = mx - newCxPx;
      const dvy = my - newCyPx;
      const lx = dvx * cos + dvy * sin;
      const ly = -dvx * sin + dvy * cos;
      ann.width = Math.max(0.001, (Math.abs(lx) * 2) / cw);
      ann.height = Math.max(0.001, (Math.abs(ly) * 2) / ch);
      ann.cx = Math.max(0, Math.min(1, newCxPx / cw));
      ann.cy = Math.max(0, Math.min(1, newCyPx / ch));
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
    tagAnchor(ann: Annotation, cw = 1, ch = 1): { x: number; y: number } {
      // 像素空间计算旋转框左上角，再转回归一化（非方形图片必做 cw/ch 换算），
      // 否则标签会与矩形分家
      const hw = (ann.width * cw) / 2,
        hh = (ann.height * ch) / 2;
      const cos = Math.cos(ann.angle),
        sin = Math.sin(ann.angle);
      return {
        x: (ann.cx * cw + -hw * cos - -hh * sin) / cw,
        y: (ann.cy * ch + -hw * sin + -hh * cos) / ch,
      };
    },
  },
};
