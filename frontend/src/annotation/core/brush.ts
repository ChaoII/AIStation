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
