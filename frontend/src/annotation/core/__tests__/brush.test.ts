import { describe, it, expect } from "vitest";
import { simplifyPolygon } from "../brush";

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
