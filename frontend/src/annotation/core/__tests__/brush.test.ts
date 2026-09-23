import { describe, it, expect } from "vitest";
import { simplifyPolygon, maskToPolygon } from "../brush";
describe("simplifyPolygon", () => {
  it("保留首尾点并简化中间共线点", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 3 },
    ];
    const out = simplifyPolygon(pts, 0.1);
    expect(out[0]).toEqual({ x: 0, y: 0 });
    expect(out[out.length - 1]).toEqual({ x: 3, y: 3 });
    // 共线中间点被简化掉
    expect(out.length).toBeLessThan(pts.length);
  });

  it("tolerance 大于特征距离时保留拐点", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
    ];
    const out = simplifyPolygon(pts, 0.1);
    expect(out.length).toBe(3);
  });
});

describe("maskToPolygon", () => {
  // 8x8 掩码，前景为居中 4x4 方块（col/row 2..5），其边界归一化中心约在 (0.5,0.5)
  const mask = new Uint8Array(64);
  for (let y = 2; y < 6; y++)
    for (let x = 2; x < 6; x++) mask[y * 8 + x] = 1;

  it("为空掩码返回空数组", () => {
    expect(maskToPolygon(new Uint8Array(64), 8, 8)).toEqual([]);
  });

  it("对居中4x4方块提取外轮廓并归一化", () => {
    const pts = maskToPolygon(mask, 8, 8);
    expect(pts.length).toBeGreaterThanOrEqual(3);
    for (const p of pts) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(1);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(1);
    }
    // 中心约在 (0.5,0.5)（居中块中心）
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    expect(Math.abs(cx - 0.5)).toBeLessThan(0.1);
    expect(Math.abs(cy - 0.5)).toBeLessThan(0.1);
  });

  it("两块前景取最大连通域（忽略小碎块）", () => {
    // 7x7：大块在左上(col0..4,row0..4)，小碎块在右下(6,6)
    const m = new Uint8Array(49);
    for (let y = 0; y < 5; y++)
      for (let x = 0; x < 5; x++) m[y * 7 + x] = 1;
    m[6 * 7 + 6] = 1;
    const pts = maskToPolygon(m, 7, 7);
    expect(pts.length).toBeGreaterThan(0);
    // 轮廓应落在左上大块附近（不含右下角）
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    expect(cx).toBeLessThan(0.8);
  });

  it("自交涂鸦（复杂连通域）不卡死且返回合法多边形", { timeout: 4000 }, () => {
    // 回归：真实手绘高频移动产生的自交掩码会让旧的边界追踪陷入 O(cw*ch*4) 死循环。
    // 修复后应快速返回（闭环或退化外接矩形），且坐标合法。
    const cw = 1000, ch = 800;
    const m = new Uint8Array(cw * ch);
    const size = 8, r = size / 2;
    for (let i = 0; i <= 120; i++) {
      const t = i / 120;
      const cx = (0.5 + Math.sin(t * Math.PI * 6) * 0.25) * cw;
      const cy = (0.5 + Math.cos(t * Math.PI * 8) * 0.15) * ch;
      const x0 = Math.max(0, Math.floor(cx - r)), x1 = Math.min(cw - 1, Math.ceil(cx + r));
      const y0 = Math.max(0, Math.floor(cy - r)), y1 = Math.min(ch - 1, Math.ceil(cy + r));
      for (let y = y0; y <= y1; y++)
        for (let x = x0; x <= x1; x++) {
          const dx = x - cx, dy = y - cy;
          if (dx * dx + dy * dy <= r * r) m[y * cw + x] = 1;
        }
    }
    const pts = maskToPolygon(m, cw, ch);
    expect(pts.length).toBeGreaterThanOrEqual(4);
    for (const p of pts) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(1);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(1);
    }
  });
});
