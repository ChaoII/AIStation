import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

export interface KpPoint {
  x: number;
  y: number;
  name: string;
  visibility: string;
}

export function useKeypointTool(kpNames: string[] = []) {
  const pending = ref<KpPoint[]>([]);
  const boxMode = ref(false);
  const boxStart = ref<Point | null>(null);
  const boxEnd = ref<Point | null>(null);
  let currentNames = kpNames;

  function setNames(names: string[]) {
    currentNames = names;
  }

  function addPoint(p: Point) {
    pending.value.push({
      x: p.x,
      y: p.y,
      name: currentNames[pending.value.length] || `kp${pending.value.length + 1}`,
      visibility: "Visible",
    });
  }

  function beginBox() {
    if (pending.value.length === 0) return;
    boxMode.value = true;
  }

  function setBoxStart(p: Point) {
    boxStart.value = p;
    boxEnd.value = p;
  }

  function updateBox(p: Point) {
    boxEnd.value = p;
  }

  // 生成关键点标注（box 用归一化对角）
  function build(): Annotation | null {
    if (!boxStart.value || !boxEnd.value) return null;
    const s = boxStart.value;
    const e = boxEnd.value;
    if (Math.abs(e.x - s.x) < 0.005 || Math.abs(e.y - s.y) < 0.005) return null;
    const x1 = Math.min(s.x, e.x);
    const y1 = Math.min(s.y, e.y);
    const x2 = Math.max(s.x, e.x);
    const y2 = Math.max(s.y, e.y);
    const ann: Annotation = {
      id: crypto.randomUUID(),
      type: "Keypoint",
      class_id: 0,
      keypoints: [...pending.value],
      bounding_box: {
        cx: (x1 + x2) / 2,
        cy: (y1 + y2) / 2,
        width: x2 - x1,
        height: y2 - y1,
        angle: 0,
      },
    };
    pending.value = [];
    boxMode.value = false;
    boxStart.value = null;
    boxEnd.value = null;
    return ann;
  }

  function moveKeypoint(ann: Annotation, idx: number, p: Point) {
    if (!ann.keypoints?.[idx]) return;
    const kp = ann.keypoints[idx];
    kp.x = p.x;
    kp.y = p.y;
  }

  return { pending, boxMode, boxStart, boxEnd, setNames, addPoint, beginBox, setBoxStart, updateBox, build, moveKeypoint };
}
