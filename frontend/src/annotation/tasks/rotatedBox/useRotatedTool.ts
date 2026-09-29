import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

// 三步旋转框：p1(边起点) → p2(边终点) → p3(垂直方向点)
// 全部在像素(viewBox)空间计算，避免非方形图片在归一化坐标下旋转/距离失真，
// 使生成的框底边即为 p1-p2 线段、宽高/角度与像素几何严格一致。
export function rotatedBoxFromEdgeAndPoint(p1: Point, p2: Point, p3: Point, cw: number, ch: number) {
  const p1x = p1.x * cw;
  const p1y = p1.y * ch;
  const p2x = p2.x * cw;
  const p2y = p2.y * ch;
  const p3x = p3.x * cw;
  const p3y = p3.y * ch;
  const vx = p2x - p1x;
  const vy = p2y - p1y;
  const widthPx = Math.hypot(vx, vy);
  if (widthPx < 1e-6) return null;
  const tx = vx / widthPx;
  const ty = vy / widthPx;
  const mx = (p1x + p2x) / 2;
  const my = (p1y + p2y) / 2;
  const t = (p3x - p1x) * tx + (p3y - p1y) * ty;
  const footX = p1x + t * tx;
  const footY = p1y + t * ty;
  const offx = p3x - footX;
  const offy = p3y - footY;
  const heightPx = Math.hypot(offx, offy);
  if (heightPx < 1e-6) return null;
  const nx = offx / heightPx;
  const ny = offy / heightPx;
  const cxPx = mx + (heightPx / 2) * nx;
  const cyPx = my + (heightPx / 2) * ny;
  return {
    cx: cxPx / cw,
    cy: cyPx / ch,
    width: widthPx / cw,
    height: heightPx / ch,
    angle: Math.atan2(vy, vx),
  };
}

export function useRotatedTool() {
  const step = ref(0); // 0=idle,1=置p1,2=拖边,3=置p3
  const pt1 = ref<Point | null>(null);
  const pt2 = ref<Point | null>(null);

  function onStep(p: Point, cw: number, ch: number): Annotation | null {
    if (step.value === 0) {
      pt1.value = p;
      step.value = 1;
      return null;
    }
    if (step.value === 1) {
      pt2.value = p;
      step.value = 2;
      return null;
    }
    if (step.value === 2) {
      const geom = rotatedBoxFromEdgeAndPoint(pt1.value!, pt2.value!, p, cw, ch);
      step.value = 0;
      pt1.value = null;
      pt2.value = null;
      if (!geom) return null;
      return {
        id: crypto.randomUUID(),
        type: "RotatedBox",
        class_id: 0,
        cx: geom.cx,
        cy: geom.cy,
        width: geom.width,
        height: geom.height,
        angle: geom.angle,
      };
    }
    return null;
  }

  // 角点缩放：固定对角，按鼠标移动重算宽高/中心（基于 orig 快照，避免累积）
  function onDragResize(
    ann: Annotation,
    orig: any,
    handle: string,
    mouse: Point,
    cw: number,
    ch: number,
    aspect: number
  ) {
    const o = orig;
    const cos = Math.cos(o.angle);
    const sin = Math.sin(o.angle);
    const fx = handle.includes("l") ? 1 : handle.includes("r") ? -1 : 1;
    const fy = handle.includes("t") ? 1 : handle.includes("b") ? -1 : 1;
    const fix_x = o.cx + ((fx * o.width) / 2) * cos - ((fy * o.height) / 2) * aspect * sin;
    const fix_y = o.cy + ((fx * o.width) / 2 / aspect) * sin + ((fy * o.height) / 2) * cos;
    const newCx = (fix_x + mouse.x) / 2;
    const newCy = (fix_y + mouse.y) / 2;
    const dvx = (mouse.x - newCx) * cw;
    const dvy = (mouse.y - newCy) * ch;
    const lx = dvx * cos + dvy * sin;
    const ly = -dvx * sin + dvy * cos;
    ann.width = Math.max(0.001, (Math.abs(lx) * 2) / cw);
    ann.height = Math.max(0.001, (Math.abs(ly) * 2) / ch);
    ann.cx = Math.max(0, Math.min(1, newCx));
    ann.cy = Math.max(0, Math.min(1, newCy));
  }

  // 旋转：绕中心
  function onRotate(
    ann: Annotation,
    centerX: number,
    centerY: number,
    startX: number,
    startY: number,
    curX: number,
    curY: number
  ) {
    const prev = Math.atan2(startY - centerY, startX - centerX);
    const cur = Math.atan2(curY - centerY, curX - centerX);
    ann.angle = JSON.parse(JSON.stringify(ann)).angle + (cur - prev);
  }

  return { step, pt1, pt2, onStep, onDragResize, onRotate };
}
