import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export function useSegmentTool() {
  const points = ref<Point[]>([]);

  function addPoint(p: Point) {
    points.value.push(p);
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
      pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x * cw},${p.y * ch}`).join(" ") + " Z"
    );
  }

  // 外接 bbox
  function polyBBox(ann: Annotation, cw: number, ch: number) {
    const pts = ann.points || [];
    const xs = pts.map((p) => p.x * cw);
    const ys = pts.map((p) => p.y * ch);
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    };
  }

  return { points, addPoint, closePolygon, moveVertex, insertVertex, deleteVertex, polygonPath, polyBBox };
}
