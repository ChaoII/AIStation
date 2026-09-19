import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export function useDetectionTool() {
  const drawing = ref(false);
  const startImg = ref<Point | null>(null);

  function onStart(p: Point) {
    drawing.value = true;
    startImg.value = p;
  }

  function onMoveEnd(p: Point): Annotation | null {
    if (!drawing.value || !startImg.value) return null;
    drawing.value = false;
    const s = startImg.value;
    if (Math.abs(p.x - s.x) < 0.005 || Math.abs(p.y - s.y) < 0.005) return null;
    return {
      id: crypto.randomUUID(),
      type: "AxisAlignedBox",
      class_id: 0,
      x1: Math.min(s.x, p.x),
      y1: Math.min(s.y, p.y),
      x2: Math.max(s.x, p.x),
      y2: Math.max(s.y, p.y),
    };
  }

  function onDrag(ann: Annotation, handle: string, dx: number, dy: number) {
    const o = JSON.parse(JSON.stringify(ann));
    if (handle.includes("l")) ann.x1 = Math.max(0, Math.min(o.x2 - 0.01, o.x1 + dx));
    if (handle.includes("r")) ann.x2 = Math.min(1, Math.max(o.x1 + 0.01, o.x2 + dx));
    if (handle.includes("t")) ann.y1 = Math.max(0, Math.min(o.y2 - 0.01, o.y1 + dy));
    if (handle.includes("b")) ann.y2 = Math.min(1, Math.max(o.y1 + 0.01, o.y2 + dy));
  }

  function onDragMove(ann: Annotation, dx: number, dy: number) {
    ann.x1 = Math.max(0, Math.min(1, ann.x1 + dx));
    ann.x2 = Math.max(0, Math.min(1, ann.x2 + dx));
    ann.y1 = Math.max(0, Math.min(1, ann.y1 + dy));
    ann.y2 = Math.max(0, Math.min(1, ann.y2 + dy));
  }

  return { drawing, onStart, onMoveEnd, onDrag, onDragMove };
}
