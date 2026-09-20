import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

// 三步旋转框：p1(边起点) → p2(边终点) → p3(垂直方向点)
export function rotatedBoxFromEdgeAndPoint(p1: Point, p2: Point, p3: Point) {
  const vx = p2.x - p1.x;
  const vy = p2.y - p1.y;
  const width = Math.hypot(vx, vy);
  if (width < 1e-6) return null;
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  const tx = vx / width;
  const ty = vy / width;
  const t = (p3.x - p1.x) * tx + (p3.y - p1.y) * ty;
  const footX = p1.x + t * tx;
  const footY = p1.y + t * ty;
  const offx = p3.x - footX;
  const offy = p3.y - footY;
  const height = Math.hypot(offx, offy);
  if (height < 1e-6) return null;
  const nx = offx / height;
  const ny = offy / height;
  return {
    cx: mx + (height / 2) * nx,
    cy: my + (height / 2) * ny,
    width,
    height,
    angle: Math.atan2(vy, vx),
  };
}

export function useRotatedTool() {
  const step = ref(0); // 0=idle,1=置p1,2=拖边,3=置p3
  const pt1 = ref<Point | null>(null);
  const pt2 = ref<Point | null>(null);

  function onStep(p: Point): Annotation | null {
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
      const geom = rotatedBoxFromEdgeAndPoint(pt1.value!, pt2.value!, p);
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
