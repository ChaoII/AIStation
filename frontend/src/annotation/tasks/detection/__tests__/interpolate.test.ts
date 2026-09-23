import { describe, it, expect } from "vitest";
import type { Annotation } from "../../../core/types";
import { interpolateBoxes } from "../interpolate";

function box(over: Partial<Annotation> = {}): Annotation {
  return {
    id: crypto.randomUUID(),
    type: "AxisAlignedBox",
    class_id: 0,
    x1: 0.1,
    y1: 0.2,
    x2: 0.5,
    y2: 0.8,
    ...over,
  };
}

describe("interpolateBoxes 线性插值", () => {
  it("t=0.5 中间帧坐标为两端中点，并继承 track_id/class_id/type", () => {
    const a = {
      frameIndex: 0,
      box: box({ id: "a", track_id: "t1", class_id: 5, x1: 0, y1: 0, x2: 1, y2: 1 }),
    };
    const b = {
      frameIndex: 10,
      box: box({ id: "b", track_id: "t1", class_id: 5, x1: 0.2, y1: 0.4, x2: 0.6, y2: 0.8 }),
    };
    const out = interpolateBoxes(a, b, [5]);
    expect(out).toHaveLength(1);
    expect(out[0].frame_index).toBe(5);
    expect(out[0].annotations).toHaveLength(1);
    const b5 = out[0].annotations[0];
    expect(b5.x1).toBeCloseTo(0.1);
    expect(b5.y1).toBeCloseTo(0.2);
    expect(b5.x2).toBeCloseTo(0.8);
    expect(b5.y2).toBeCloseTo(0.9);
    expect(b5.track_id).toBe("t1");
    expect(b5.class_id).toBe(5);
    expect(b5.type).toBe("AxisAlignedBox");
    expect(b5.id).toBeTruthy();
  });

  it("多个中间帧按 t 线性插值，t 随帧距变化", () => {
    const a = { frameIndex: 10, box: box({ track_id: "t1", x1: 0, y1: 0, x2: 1, y2: 1 }) };
    const b = { frameIndex: 20, box: box({ track_id: "t1", x1: 0.4, y1: 0.4, x2: 0.6, y2: 0.6 }) };
    const out = interpolateBoxes(a, b, [12, 15, 18]);
    expect(out.map((f) => f.frame_index)).toEqual([12, 15, 18]);
    const f12 = out[0].annotations[0];
    const f15 = out[1].annotations[0];
    const f18 = out[2].annotations[0];
    // t=0.2
    expect(f12.x1).toBeCloseTo(0.08);
    expect(f12.y1).toBeCloseTo(0.08);
    expect(f12.x2).toBeCloseTo(0.92);
    expect(f12.y2).toBeCloseTo(0.92);
    // t=0.5
    expect(f15.x1).toBeCloseTo(0.2);
    expect(f15.x2).toBeCloseTo(0.8);
    // t=0.8
    expect(f18.x1).toBeCloseTo(0.32);
    expect(f18.y2).toBeCloseTo(0.68);
  });

  it("关键帧本身不生成（frames 含 frameA/frameB 时跳过）", () => {
    const a = { frameIndex: 0, box: box({ track_id: "t1" }) };
    const b = { frameIndex: 2, box: box({ track_id: "t1" }) };
    const out = interpolateBoxes(a, b, [0, 1, 2]);
    expect(out).toHaveLength(1);
    expect(out[0].frame_index).toBe(1);
  });

  it("每个中间帧生成独立 id，关键帧框不动", () => {
    const a = { frameIndex: 0, box: box({ id: "A", track_id: "t1", class_id: 3 }) };
    const b = { frameIndex: 3, box: box({ id: "B", track_id: "t1", class_id: 3 }) };
    const out = interpolateBoxes(a, b, [1, 2]);
    const ids = out.map((f) => f.annotations[0].id);
    expect(ids[0]).not.toBe(ids[1]);
    expect(out[0].annotations[0].id).not.toBe("A");
    expect(out[1].annotations[0].id).not.toBe("B");
  });

  it("中间帧无框时生成空 annotations 列表", () => {
    const a = { frameIndex: 0, box: box({ track_id: "t1" }) };
    const b = { frameIndex: 5, box: box({ track_id: "t1" }) };
    const out = interpolateBoxes(a, b, []);
    expect(out).toEqual([]);
  });
});
