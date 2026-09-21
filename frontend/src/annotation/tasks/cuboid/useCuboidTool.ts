import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

// 三步旋转底框：p1(边起点) → p2(边终点) → p3(垂直方向点)
export function cuboidFromEdgeAndPoint(p1: Point, p2: Point, p3: Point) {
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

export function useCuboidTool() {
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
      const geom = cuboidFromEdgeAndPoint(pt1.value!, pt2.value!, p);
      step.value = 0;
      pt1.value = null;
      pt2.value = null;
      if (!geom) return null;
      return {
        id: crypto.randomUUID(),
        type: "Cuboid",
        class_id: 0,
        cx: geom.cx,
        cy: geom.cy,
        w: geom.width,
        h: geom.height,
        yaw: geom.angle,
        depth: 0.5,
        top_cy: 0.15,
      };
    }
    return null;
  }

  return { step, pt1, pt2, onStep };
}
