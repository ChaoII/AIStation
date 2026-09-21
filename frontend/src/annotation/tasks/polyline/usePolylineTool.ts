import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export function usePolylineTool() {
  const points = ref<Point[]>([]);

  function addPoint(p: Point) {
    points.value.push(p);
  }

  function finish(): Annotation | null {
    if (points.value.length < 2) {
      points.value = [];
      return null;
    }
    const ann: Annotation = {
      id: crypto.randomUUID(),
      type: "Polyline",
      class_id: 0,
      points: [...points.value],
    };
    points.value = [];
    return ann;
  }

  return { points, addPoint, finish };
}
