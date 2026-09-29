import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

// 底面为平行四边形，由 3 个角点确定（p1 公共角 → p2 沿第 1 条边（长） → p3 沿第 2 条边（宽/高））。
// 第 4 角 = p2 + p3 - p1。全程在像素空间计算再回归一化，非方形图片不错位。
export function cuboidFromEdgeAndPoint(p1: Point, p2: Point, p3: Point, cw: number, ch: number) {
  const P1 = { x: p1.x * cw, y: p1.y * ch };
  const P2 = { x: p2.x * cw, y: p2.y * ch };
  const P3 = { x: p3.x * cw, y: p3.y * ch };
  const v1x = P2.x - P1.x;
  const v1y = P2.y - P1.y;
  const v2x = P3.x - P1.x;
  const v2y = P3.y - P1.y;
  const width = Math.hypot(v1x, v1y);
  const height = Math.hypot(v2x, v2y);
  if (width < 1e-6 || height < 1e-6) return null;
  const angle1 = Math.atan2(v1y, v1x);
  const angle2 = Math.atan2(v2y, v2x);
  // 平行四边形中心 = (p2 + p3)/2
  const cxPix = (P2.x + P3.x) / 2;
  const cyPix = (P2.y + P3.y) / 2;
  return {
    cx: cxPix / cw,
    cy: cyPix / ch,
    width: width / cw,
    height: height / ch,
    angle1,
    angle2,
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export function useCuboidTool() {
  // step: 0=idle, 1=已放p1, 2=已放p2(拖第2条边), 3=底面确定(向上拖高度)
  const step = ref(0);
  const pt1 = ref<Point | null>(null);
  const pt2 = ref<Point | null>(null);
  const pt3 = ref<Point | null>(null);
  const baseGeom = ref<any>(null); // 固定的底面几何 {cx,cy,width,height,angle1,angle2}
  const height = ref(0); // 归一化高度 0..1（高度模式由鼠标驱动）

  function reset() {
    step.value = 0;
    pt1.value = null;
    pt2.value = null;
    pt3.value = null;
    baseGeom.value = null;
    height.value = 0;
  }

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
      const g = cuboidFromEdgeAndPoint(pt1.value!, pt2.value!, p, cw, ch);
      if (!g) {
        reset();
        return null;
      }
      pt3.value = p;
      baseGeom.value = g;
      step.value = 3;
      return null;
    }
    // step 3：向上拖出高度，点击确认生成
    const g = baseGeom.value;
    if (!g) return null;
    const h = clamp(g.cy - p.y, 0, 1);
    reset();
    return {
      id: crypto.randomUUID(),
      type: "Cuboid",
      class_id: 0,
      cx: g.cx,
      cy: g.cy,
      w: g.width,
      h: g.height,
      yaw: g.angle1,
      angle1: g.angle1,
      angle2: g.angle2,
      depth: h,
      top_cy: h,
    };
  }

  return { step, pt1, pt2, pt3, baseGeom, height, onStep, reset };
}
