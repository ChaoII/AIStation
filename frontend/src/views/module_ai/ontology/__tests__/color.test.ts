import { describe, it, expect } from "vitest";
import { stableColor } from "../../../../utils/color";

describe("stableColor", () => {
  it("相同 key 稳定返回同色", () => {
    expect(stableColor("sales")).toBe(stableColor("sales"));
    expect(stableColor("sales")).toBe(stableColor("sales"));
  });
  it("不同 key 大概率返回不同色", () => {
    const a = stableColor("sales");
    const b = stableColor("iot");
    const c = stableColor("hr");
    // 一个集合里 3 个不同 key 至少 2 个不同色（允许极小碰撞）
    const set = new Set([a, b, c]);
    expect(set.size).toBeGreaterThan(1);
  });
  it("空/未分组 key 返回稳定的中性色", () => {
    expect(stableColor("")).toBe(stableColor("未分组"));
    expect(stableColor("未分组")).toMatch(/^#/);
  });
});
