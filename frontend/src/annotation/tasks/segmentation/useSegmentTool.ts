import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export function useSegmentTool() {
  const points = ref<Point[]>([]);
  // 当前鼠标位置（归一化），用于绘制「末点→鼠标」的跟随预览线与首点闭合提示。
  const cursor = ref<Point | null>(null);
  // 判定「鼠标靠近首点可闭合」的半径（屏幕像素，视觉恒定）。
  const closeRadiusPx = 16;

  function addPoint(p: Point) {
    points.value.push(p);
  }

  /** 鼠标（归一化）是否靠近首点（按屏幕像素距离判定，与闭合提示一致）。 */
  function isNearFirst(p: Point | null | undefined, cw: number, ch: number, zoom = 1): boolean {
    const first = points.value[0];
    if (!p || !first || !cw || !ch) return false;
    const dx = (p.x - first.x) * cw * zoom;
    const dy = (p.y - first.y) * ch * zoom;
    return Math.sqrt(dx * dx + dy * dy) <= closeRadiusPx;
  }

  function closePolygon(): Annotation | null {
    if (points.value.length < 3) {
      points.value = [];
      return null;
    }
    const ann: Annotation = {
      id: crypto.randomUUID(),
      type: "Polygon",
      class_id: 0,
      points: [...points.value],
    };
    points.value = [];
    return ann;
  }

  function moveVertex(ann: Annotation, idx: number, p: Point) {
    if (!ann.points?.[idx]) return;
    ann.points[idx] = p;
  }

  function insertVertex(ann: Annotation, afterIdx: number, p: Point) {
    if (!ann.points) return;
    ann.points.splice(afterIdx + 1, 0, p);
  }

  function deleteVertex(ann: Annotation, idx: number) {
    if (!ann.points) return;
    const min = 3;
    if (ann.points.length > min) ann.points.splice(idx, 1);
  }

  // 多边形路径
  function polygonPath(ann: Annotation, cw: number, ch: number): string {
    const pts = ann.points || [];
    if (pts.length === 0) return "";
    return (
      pts.map((p: Point, i: number) => `${i === 0 ? "M" : "L"}${p.x * cw},${p.y * ch}`).join(" ") +
      " Z"
    );
  }

  // 外接 bbox
  function polyBBox(ann: Annotation, cw: number, ch: number) {
    const pts = ann.points || [];
    const xs = pts.map((p: Point) => p.x * cw);
    const ys = pts.map((p: Point) => p.y * ch);
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    };
  }

  return {
    points,
    cursor,
    closeRadiusPx,
    isNearFirst,
    addPoint,
    closePolygon,
    moveVertex,
    insertVertex,
    deleteVertex,
    polygonPath,
    polyBBox,
  };
}
