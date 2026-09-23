import { describe, it, expect } from "vitest";
import type { Annotation } from "../../../core/types";
import {
  boxCenter,
  boxCorners,
  groupByTrack,
  collectTrackIds,
  newTrackId,
  findBoxByTrack,
  trackPath,
  trackPathFromFrames,
  nearestTrackFrame,
  trackColor,
} from "../track";

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

describe("track 轨迹纯函数", () => {
  it("boxCenter 计算归一化中心点", () => {
    expect(boxCenter(box({ x1: 0, y1: 0, x2: 1, y2: 1 }))).toEqual({ x: 0.5, y: 0.5 });
    expect(boxCenter(box({ x1: 0.2, y1: 0.3, x2: 0.6, y2: 0.9 }))).toEqual({ x: 0.4, y: 0.6 });
  });

  it("boxCorners 返回四角点（左上/右上/右下/左下）", () => {
    const corners = boxCorners(box({ x1: 0.1, y1: 0.2, x2: 0.5, y2: 0.8 }));
    expect(corners).toEqual([
      { x: 0.1, y: 0.2 },
      { x: 0.5, y: 0.2 },
      { x: 0.5, y: 0.8 },
      { x: 0.1, y: 0.8 },
    ]);
  });

  it("groupByTrack 按 track_id 分组并跳过无轨迹框", () => {
    const grouped = groupByTrack([
      box({ id: "a", track_id: "t1" }),
      box({ id: "b", track_id: "t1" }),
      box({ id: "c", track_id: "t2" }),
      box({ id: "d" }),
    ]);
    expect(grouped["t1"].map((x) => x.id)).toEqual(["a", "b"]);
    expect(grouped["t2"].map((x) => x.id)).toEqual(["c"]);
    expect(grouped["d"]).toBeUndefined();
  });

  it("collectTrackIds 去重并保持首次出现顺序", () => {
    const ids = collectTrackIds([
      box({ track_id: "t1" }),
      box({ track_id: "t2" }),
      box({ track_id: "t1" }),
      box(),
    ]);
    expect(ids).toEqual(["t1", "t2"]);
  });

  it("newTrackId 生成非空唯一 id", () => {
    const a = newTrackId();
    const b = newTrackId();
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });

  it("findBoxByTrack 在某帧框集合中查找指定轨迹框", () => {
    const anns = [box({ id: "x", track_id: "t1" }), box({ id: "y", track_id: "t2" })];
    expect(findBoxByTrack(anns, "t2")?.id).toBe("y");
    expect(findBoxByTrack(anns, "t3")).toBeUndefined();
  });

  it("trackPath 按输入顺序取框中心连线", () => {
    const path = trackPath([
      box({ x1: 0.1, y1: 0.1, x2: 0.3, y2: 0.3 }),
      box({ x1: 0.6, y1: 0.6, x2: 0.8, y2: 0.8 }),
    ]);
    expect(path).toEqual([
      { x: 0.2, y: 0.2 },
      { x: 0.7, y: 0.7 },
    ]);
  });

  it("trackPathFromFrames 按帧序排序并返回中心点", () => {
    const path = trackPathFromFrames([
      { frameIndex: 10, box: box({ x1: 0.6, y1: 0.6, x2: 0.8, y2: 0.8 }) },
      { frameIndex: 2, box: box({ x1: 0.1, y1: 0.1, x2: 0.3, y2: 0.3 }) },
    ]);
    expect(path).toEqual([
      { frameIndex: 2, point: { x: 0.2, y: 0.2 } },
      { frameIndex: 10, point: { x: 0.7, y: 0.7 } },
    ]);
  });

  it("nearestTrackFrame 返回相对当前帧的前一/后一帧（无则 null）", () => {
    expect(nearestTrackFrame([2, 5, 9], 5, 1)).toBe(9);
    expect(nearestTrackFrame([2, 5, 9], 5, -1)).toBe(2);
    expect(nearestTrackFrame([2, 5, 9], 9, 1)).toBeNull();
    expect(nearestTrackFrame([2, 5, 9], 2, -1)).toBeNull();
    // 乱序输入也应正确处理
    expect(nearestTrackFrame([9, 2, 5], 2, 1)).toBe(5);
  });

  it("trackColor 同一 track_id 恒定同色", () => {
    expect(trackColor("abc")).toBe(trackColor("abc"));
    expect(trackColor("t1")).toMatch(/^#[0-9a-f]{6}$/);
  });
});
