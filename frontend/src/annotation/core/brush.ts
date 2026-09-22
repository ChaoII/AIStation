import type { Point } from "./types";

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
  const boundary = traceBoundary(comp, cw, ch);
  if (boundary.length < 3) return [];

  // 3) 在像素坐标下简化（tol 以像素为单位），再归一化 [0,1]
  const closed = [...boundary, boundary[0]];
  const simp = simplifyPolygon(closed, tol);
  return simp
    .slice(0, Math.max(simp.length - 1, 0))
    .map((p) => ({ x: p.x / cw, y: p.y / ch }));
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

/** Moore 邻域边界追踪：从连通域最左上前景像素出发，沿外边界走回起点。 */
function traceBoundary(
  comp: Set<number>,
  cw: number,
  ch: number
): { x: number; y: number }[] {
  if (comp.size === 0) return [];
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
  if (start < 0) return [];
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
  const out: { x: number; y: number }[] = [b];
  let guard = 0;
  const maxSteps = cw * ch * 4 + 100;
  while (guard++ < maxSteps) {
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
    if (nb.x === sx && nb.y === sy) break; // 回到起点，闭环完成
    b = nb;
    cDir = (found - 1 + 8) % 8; // 新背景邻域 = 找到的前景像素的前一个（顺时针）方向
    out.push(b);
  }
  return out;
}
