import { ref } from "vue";
import type { AnnotationTaskPlugin, Annotation, DragContext, Point } from "../../core/types";
import CuboidCanvas from "./CuboidCanvas.vue";
import CuboidPreview from "./CuboidPreview.vue";
import CuboidPanel from "./CuboidPanel.vue";
import { useCuboidTool, cuboidFromEdgeAndPoint } from "./useCuboidTool";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export const cuboidPlugin: AnnotationTaskPlugin = {
  name: "cuboid",
  label: "3D 目标检测",
  color: "danger",
  renderer: CuboidCanvas,
  tools: [
    { name: "cuboid", label: "3D 目标检测", title: "分 4 步画：放底面 3 个角点（平行四边形）→ 向上拖出高度" },
  ],
  panel: CuboidPanel,
  create(shape: Annotation): boolean {
    if (shape.type !== "Cuboid") return false;
    if (shape.w <= 0 || shape.h <= 0) return false;
    if (shape.cx < 0 || shape.cy < 0 || shape.cx > 1 || shape.cy > 1) return false;
    // 底面平行四边形按两条边方向展开，取 4 角 x/y 范围做边缘校验（非方形图片用像素空间）
    const a1 = shape.angle1 ?? shape.yaw ?? 0;
    const a2 = shape.angle2 ?? a1 + Math.PI / 2;
    const cos1 = Math.cos(a1);
    const sin1 = Math.sin(a1);
    const cos2 = Math.cos(a2);
    const sin2 = Math.sin(a2);
    const hx = (Math.abs(shape.w * cos1) + Math.abs(shape.h * cos2)) / 2;
    const hy = (Math.abs(shape.w * sin1) + Math.abs(shape.h * sin2)) / 2;
    if (shape.cx - hx < 0 || shape.cx + hx > 1) return false;
    if (shape.cy - hy < 0 || shape.cy + hy > 1) return false;
    if (shape.depth < 0 || shape.depth > 1) return false;
    if (shape.top_cy < 0 || shape.top_cy > 1) return false;
    return true;
  },
  tool: (() => {
    const cub = useCuboidTool();
    const preview = ref<any>(null);
    const buildPreview = (p?: any, cw = 1, ch = 1) => {
      const s = cub.step.value;
      const parts: any = {
        step: s,
        pt1: cub.pt1.value,
        pt2: cub.pt2.value,
        pt3: cub.pt3.value,
        baseGeom: cub.baseGeom.value,
        height: cub.height.value,
      };
      if (s === 2 && cub.pt1.value && cub.pt2.value && p) {
        const g = cuboidFromEdgeAndPoint(cub.pt1.value, cub.pt2.value, p, cw, ch);
        if (g) {
          parts.baseGeom = g;
          parts.pt3 = p;
        }
      }
      if (s === 3 && cub.baseGeom.value) {
        const h = clamp(cub.baseGeom.value.cy - p.y, 0, 1);
        parts.height = h;
        cub.height.value = h;
      }
      return parts;
    };
    return {
      name: "cuboid",
      preview: CuboidPreview,
      state: {
        step: cub.step,
        pt1: cub.pt1,
        pt2: cub.pt2,
        pt3: cub.pt3,
        baseGeom: cub.baseGeom,
        height: cub.height,
        preview,
      },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        // 高度模式：用点击位置相对底面中心的上移量作为高度
        if (cub.step.value === 3 && cub.baseGeom.value) {
          cub.height.value = clamp(cub.baseGeom.value.cy - p.y, 0, 1);
        }
        const created = cub.onStep(p, ctx.cw ?? 1, ctx.ch ?? 1);
        if (created) {
          preview.value = null;
        } else {
          // 点击后立即刷新预览（让刚放下的点/边/底面马上显示，无需等鼠标移动）
          preview.value = buildPreview(p, ctx.cw ?? 1, ctx.ch ?? 1);
        }
        return created;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p) return;
        preview.value = buildPreview(p, ctx.cw ?? 1, ctx.ch ?? 1);
      },
      reset() {
        cub.reset();
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
      const a1 = orig.angle1 ?? orig.yaw ?? 0;
      const a2 = orig.angle2 ?? a1 + Math.PI / 2;
      const d1 = { x: Math.cos(a1), y: Math.sin(a1) };
      const d2 = { x: Math.cos(a2), y: Math.sin(a2) };
      const idx = { tl: 0, tr: 1, br: 2, bl: 3 }[handle] ?? 0;
      // 拖拽角与其对角固定
      const fixedIdx = { tl: 2, tr: 3, br: 0, bl: 1 }[handle] ?? 2;
      const F = cornerPx(orig, fixedIdx, cw, ch);
      const M = { x: point.x * cw, y: point.y * ch };
      const C = { x: (F.x + M.x) / 2, y: (F.y + M.y) / 2 };
      const v = { x: M.x - F.x, y: M.y - F.y };
      // 把 v 分解到 d1/d2 基（Gram 求解，支持非正交平行四边形）
      const det = d1.x * d2.y - d1.y * d2.x;
      const lx = Math.abs((v.x * d2.y - v.y * d2.x) / det);
      const ly = Math.abs((v.y * d1.x - v.x * d1.y) / det);
      ann.w = Math.max(0.001, lx / cw);
      ann.h = Math.max(0.001, ly / ch);
      ann.cx = clamp(C.x / cw, 0, 1);
      ann.cy = clamp(C.y / ch, 0, 1);
      void idx;
      ctx.trigger();
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const a1 = ann.angle1 ?? ann.yaw ?? 0;
      const a2 = ann.angle2 ?? a1 + Math.PI / 2;
      const hw = ann.w / 2;
      const hh = ann.h / 2;
      return {
        x: ann.cx - hw * Math.cos(a1) - hh * Math.cos(a2),
        y: ann.cy - hw * Math.sin(a1) - hh * Math.sin(a2),
      };
    },
  },
};

// 底面平行四边形 4 角（像素），idx 0..3 = p1,p2,p4,p3
function cornerPx(a: Annotation, idx: number, cw: number, ch: number): { x: number; y: number } {
  const a1 = a.angle1 ?? a.yaw ?? 0;
  const a2 = a.angle2 ?? a1 + Math.PI / 2;
  const d1 = { x: Math.cos(a1), y: Math.sin(a1) };
  const d2 = { x: Math.cos(a2), y: Math.sin(a2) };
  const hw = (a.w * cw) / 2;
  const hh = (a.h * ch) / 2;
  const cx = a.cx * cw;
  const cy = a.cy * ch;
  const local: [number, number][] = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  const [lx, ly] = local[idx] || [0, 0];
  return { x: cx + lx * d1.x + ly * d2.x, y: cy + lx * d1.y + ly * d2.y };
}
