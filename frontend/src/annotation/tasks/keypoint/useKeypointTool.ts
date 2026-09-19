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

  function addPoint(p: Point, visibility = "Visible") {
    pending.value.push({
      x: p.x,
      y: p.y,
      name: currentNames[pending.value.length] || `kp${pending.value.length + 1}`,
      visibility,
    });
  }

  function removeKeypoint(ann: Annotation, idx: number) {
    if (!ann.keypoints?.length) return;
    if (ann.keypoints.length <= 1) return;
    ann.keypoints.splice(idx, 1);
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
    kp.x = Math.max(0, Math.min(1, p.x));
    kp.y = Math.max(0, Math.min(1, p.y));
  }

  // 整体移动：移动包围盒中心 + 所有关键点（相对同步平移）
  function moveBBox(ann: Annotation, dx: number, dy: number) {
    const b = ann.bounding_box;
    if (!b) return;
    b.cx = Math.max(0, Math.min(1, b.cx + dx));
    b.cy = Math.max(0, Math.min(1, b.cy + dy));
    (ann.keypoints || []).forEach((k: any) => {
      k.x = Math.max(0, Math.min(1, k.x + dx));
      k.y = Math.max(0, Math.min(1, k.y + dy));
    });
  }

  // 包围盒缩放：按 handle 调整 bbox，并按比例缩放/约束绝顶关键点
  function resizeBBox(ann: Annotation, handle: string, dx: number, dy: number) {
    const b = ann.bounding_box;
    if (!b) return;
    const o = JSON.parse(JSON.stringify(b));
    let x1 = o.cx - o.width / 2,
      y1 = o.cy - o.height / 2,
      x2 = o.cx + o.width / 2,
      y2 = o.cy + o.height / 2;
    if (handle.includes("l")) x1 = Math.min(x2 - 0.01, x1 + dx);
    if (handle.includes("r")) x2 = Math.max(x1 + 0.01, x2 + dx);
    if (handle.includes("t")) y1 = Math.min(y2 - 0.01, y1 + dy);
    if (handle.includes("b")) y2 = Math.max(y1 + 0.01, y2 + dy);
    const nw = Math.max(0.01, x2 - x1);
    const nh = Math.max(0.01, y2 - y1);
    const oW = o.width || 1;
    const oH = o.height || 1;
    // 以包围盒左上为基准，把关键点按比例映射到新 bbox
    (ann.keypoints || []).forEach((k: any) => {
      const rx = ((k.x - (o.cx - oW / 2)) / oW + 1) / 2; // 0..1 within old box
      const ry = ((k.y - (o.cy - oH / 2)) / oH + 1) / 2;
      k.x = Math.max(0, Math.min(1, x1 + rx * nw));
      k.y = Math.max(0, Math.min(1, y1 + ry * nh));
    });
    b.cx = (x1 + x2) / 2;
    b.cy = (y1 + y2) / 2;
    b.width = nw;
    b.height = nh;
  }

  return { pending, boxMode, boxStart, boxEnd, setNames, addPoint, beginBox, setBoxStart, updateBox, build, moveKeypoint, moveBBox, resizeBBox, removeKeypoint };
}
