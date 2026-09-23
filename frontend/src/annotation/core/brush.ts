import { ref } from "vue";
import type { Annotation, Point } from "./types";

/** Douglas-Peucker 折线简化（保留首尾点），返回新数组。 */
export function simplifyPolygon(points: Point[], tolerance: number): Point[] {
  if (points.length <= 2) return points.slice();
  const sqTol = tolerance * tolerance;
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;
  const stack: Array<[number, number]> = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop()!;
    let maxDist = 0;
    let maxIdx = -1;
    for (let i = a + 1; i < b; i++) {
      const d = distToSegmentSq(points[i], points[a], points[b]);
      if (d > maxDist) {
        maxDist = d;
        maxIdx = i;
      }
    }
    if (maxIdx > 0 && maxDist > sqTol) {
      keep[maxIdx] = true;
      stack.push([a, maxIdx], [maxIdx, b]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

function distToSegmentSq(p: Point, a: Point, b: Point): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  if (lenSq === 0) return (p.x - a.x) ** 2 + (p.y - a.y) ** 2;
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lenSq;
  t = Math.max(0, Math.min(1, t));
  const cx = a.x + t * abx;
  const cy = a.y + t * aby;
  return (p.x - cx) ** 2 + (p.y - cy) ** 2;
}

/** 二值掩码(1=前景) → 最大连通域外边界 → 简化(像素坐标) → 归一化折线。 */
export function maskToPolygon(
  mask: Uint8Array,
  cw: number,
  ch: number,
  tol = 1.0
): Point[] {
  const grid = new Uint8Array(mask.length);
  for (let i = 0; i < mask.length; i++) grid[i] = mask[i] ? 1 : 0;

  // 1) 最大连通域（BFS），忽略前景为0的情况
  const comp = largestComponent(grid, cw, ch);
  if (comp.size < 3) return [];

  // 2) Moore 邻域边界追踪，得到像素坐标外边界（闭环）
  const { points: boundary, closed } = traceBoundary(comp, cw, ch);
  if (!closed || boundary.length < 3) {
    // 自交/杂乱涂鸦等复杂形状可能导致边界追踪无法闭环；此时退化为该连通域的外接矩形，
    // 保证快速返回一个可用多边形，避免主线程被 O(cw*ch*4) 的追踪卡死。
    return bboxPolygon(comp, cw, ch);
  }

  // 3) 在像素坐标下简化（tol 以像素为单位），再归一化 [0,1]
  const closedLoop = [...boundary, boundary[0]];
  const simp = simplifyPolygon(closedLoop, tol);
  return simp
    .slice(0, Math.max(simp.length - 1, 0))
    .map((p) => ({ x: p.x / cw, y: p.y / ch }));
}

/** 连通域的外接矩形（4 角），用于边界追踪无法闭环时的兜底多边形（归一化坐标）。 */
function bboxPolygon(comp: Set<number>, cw: number, ch: number): Point[] {
  if (comp.size === 0) return [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const idx of comp) {
    const x = idx % cw;
    const y = (idx - x) / cw;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const corners = [
    { x: minX, y: minY },
    { x: maxX, y: minY },
    { x: maxX, y: maxY },
    { x: minX, y: maxY },
  ];
  return corners.map((p) => ({ x: p.x / cw, y: p.y / ch }));
}

function largestComponent(
  grid: Uint8Array,
  cw: number,
  ch: number
): Set<number> {
  const visited = new Uint8Array(grid.length);
  let best = new Set<number>();
  const dirs = [
    [1, 0], [-1, 0], [0, 1], [0, -1],
  ];
  for (let i = 0; i < grid.length; i++) {
    if (!grid[i] || visited[i]) continue;
    const queue = [i];
    visited[i] = 1;
    const comp = new Set<number>();
    let head = 0;
    while (head < queue.length) {
      const cur = queue[head++];
      comp.add(cur);
      const cx = cur % cw;
      const cy = (cur - cx) / cw;
      for (const [dx, dy] of dirs) {
        const nx = cx + dx;
        const ny = cy + dy;
        if (nx < 0 || nx >= cw || ny < 0 || ny >= ch) continue;
        const ni = ny * cw + nx;
        if (grid[ni] && !visited[ni]) {
          visited[ni] = 1;
          queue.push(ni);
        }
      }
    }
    if (comp.size > best.size) best = comp;
  }
  return best;
}

/**
 * Moore 邻域边界追踪：从连通域最左上前景像素出发，沿外边界走回起点。
 * 返回是否成功闭环；对自交/杂乱形状可能无法闭环，此时 `closed` 为 false，
 * 由调用方退化为外接矩形，避免 O(cw*ch*4) 的循环阻塞主线程。
 */
function traceBoundary(
  comp: Set<number>,
  cw: number,
  ch: number
): { points: { x: number; y: number }[]; closed: boolean } {
  if (comp.size === 0) return { points: [], closed: false };
  const has = (x: number, y: number) =>
    x >= 0 && x < cw && y >= 0 && y < ch && comp.has(y * cw + x);

  // 找起点：最左列中最上面的前景像素
  let start = -1;
  for (let x = 0; x < cw && start < 0; x++)
    for (let y = 0; y < ch; y++)
      if (has(x, y)) {
        start = y * cw + x;
        break;
      }
  if (start < 0) return { points: [], closed: false };
  const sx = start % cw;
  const sy = (start - sx) / cw;

  // 8 方向，顺时针（屏幕坐标 y 向下）：N NE E SE S SW W NW
  const dirs = [
    [0, -1], [1, -1], [1, 0], [1, 1],
    [0, 1], [-1, 1], [-1, 0], [-1, -1],
  ];
  // 起点西侧必为背景（b0 是最左列前景），作为初始背景邻域方向
  let b = { x: sx, y: sy };
  let cDir = 6; // West
  const points: { x: number; y: number }[] = [b];
  // 用 (像素, 背景邻域方向) 状态去重检测循环：一旦重复说明当前追踪已陷入环路，
  // 不会再回到起点，立即中止（返回 closed=false）；否则会循环到 maxSteps 上限。
  const seen = new Set<string>();
  // 步数硬上限 = 边界像素数上界（周长 ≤ 4*面积 + 常数），防止任何病态退化。
  const maxSteps = 4 * comp.size + 100;
  let guard = 0;
  while (guard++ < maxSteps) {
    const stateKey = b.x + "," + b.y + "," + cDir;
    if (seen.has(stateKey)) break;
    seen.add(stateKey);
    // 自背景邻域 cDir 起，顺时针扫描 8 邻域，找第一个前景像素
    let found = -1;
    for (let k = 1; k <= 8; k++) {
      const idx = (cDir + k) % 8;
      const [dx, dy] = dirs[idx];
      if (has(b.x + dx, b.y + dy)) {
        found = idx;
        break;
      }
    }
    if (found < 0) break;
    const nb = { x: b.x + dirs[found][0], y: b.y + dirs[found][1] };
    if (nb.x === sx && nb.y === sy) return { points, closed: true }; // 回到起点，闭环完成
    b = nb;
    cDir = (found - 1 + 8) % 8; // 新背景邻域 = 找到的前景像素的前一个（顺时针）方向
    points.push(b);
  }
  return { points, closed: false };
}

/** 画笔状态机：维护当前笔画轨迹与橡皮擦标记；end() 用位图掩码转 Polygon。 */
export function useBrushTool() {
  const strokes = ref<Point[][]>([]);
  const brushSize = ref(8);
  const erasing = ref(false);
  let canvas: HTMLCanvasElement | null = null;

  function ensureCanvas(cw: number, ch: number): HTMLCanvasElement {
    if (!canvas) canvas = document.createElement("canvas");
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw;
      canvas.height = ch;
    }
    return canvas;
  }

  function paintStroke(points: Point[], cw: number, ch: number, erase: boolean) {
    const ctx = ensureCanvas(cw, ch).getContext("2d")!;
    ctx.globalCompositeOperation = erase ? "destination-out" : "source-over";
    ctx.strokeStyle = "#000";
    ctx.lineWidth = brushSize.value;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = p.x * cw;
      const y = p.y * ch;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function clearCanvas() {
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  /** 开始一笔：清空上一标注掩码，置首点。 */
  function start(p: Point) {
    clearCanvas();
    strokes.value = [[{ ...p }]];
  }

  /** 追加轨迹点。 */
  function move(p: Point) {
    const cur = strokes.value;
    if (cur.length === 0) return;
    (cur[cur.length - 1] ||= []).push({ ...p });
  }

  /** 结束一笔：把轨迹刷到画布 → 二值掩码 → 转 Polygon。 */
  function end(cw: number, ch: number): Annotation | null {
    if (strokes.value.length === 0) return null;
    const all: Point[] = [];
    strokes.value.forEach((s) => all.push(...s));
    paintStroke(all, cw, ch, erasing.value);
    const ctx = ensureCanvas(cw, ch).getContext("2d")!;
    const imageData = ctx.getImageData(0, 0, cw, ch);
    const mask = new Uint8Array(imageData.data.length / 4);
    for (let i = 0; i < mask.length; i++) mask[i] = imageData.data[i * 4 + 3] > 0 ? 1 : 0;
    const pts = maskToPolygon(mask, cw, ch);
    strokes.value = [];
    if (pts.length < 3) return null;
    return {
      id: crypto.randomUUID(),
      type: "Polygon" as const,
      class_id: 0,
      points: pts,
    };
  }

  function reset() {
    strokes.value = [];
    clearCanvas();
  }

  return { strokes, brushSize, erasing, start, move, end, reset };
}
