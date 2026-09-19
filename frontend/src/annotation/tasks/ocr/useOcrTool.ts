import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export function useOcrTool() {
  const first = ref<Point | null>(null);

  function onPoint(p: Point): Annotation | null {
    if (!first.value) {
      first.value = p;
      return null;
    }
    const s = first.value;
    const x1 = Math.min(s.x, p.x);
    const y1 = Math.min(s.y, p.y);
    const x2 = Math.max(s.x, p.x);
    const y2 = Math.max(s.y, p.y);
    first.value = null;
    if (Math.abs(x2 - x1) < 0.005 || Math.abs(y2 - y1) < 0.005) return null;
    const ann: Annotation = {
      id: crypto.randomUUID(),
      type: "Ocr",
      class_id: 0,
      points: [
        { x: x1, y: y1 },
        { x: x2, y: y1 },
        { x: x2, y: y2 },
        { x: x1, y: y2 },
      ],
      text: "",
      source: "rect",
    };
    return ann;
  }

  function reset() {
    first.value = null;
  }

  function moveVertex(ann: Annotation, idx: number, p: Point) {
    if (!ann.points?.[idx]) return;
    ann.points[idx] = p;
  }

  return { first, onPoint, reset, moveVertex };
}
