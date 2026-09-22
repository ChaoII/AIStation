import { describe, it, expect } from "vitest";
import { timeToFrameIndex, frameIndexToTime } from "../workbenchFrame";

describe("workbenchFrame 帧号换算", () => {
  it("timeToFrameIndex = round(time*fps)", () => {
    expect(timeToFrameIndex(1.234, 25)).toBe(31);
  });
  it("frameIndexToTime = idx/fps", () => {
    expect(frameIndexToTime(31, 25)).toBeCloseTo(1.24, 1);
  });
  it("round-trip", () => {
    expect(timeToFrameIndex(frameIndexToTime(7, 30), 30)).toBe(7);
  });
});
