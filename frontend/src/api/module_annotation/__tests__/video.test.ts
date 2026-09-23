import { describe, it, expect, vi, beforeEach } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: requestMock }));

import { interpolateVideoFrames } from "../video";

const API_PATH = "/annotation";
const ok = (data: unknown) => ({ data: { code: 0, data, msg: "" } });

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockResolvedValue(ok(null));
});

describe("视频关键帧批量插值 API", () => {
  it("interpolateVideoFrames POST /annotation/anno/video/interpolate，body 为 {task_id,video_id,track_id,frame_a,frame_b,frames}", async () => {
    const payload = {
      task_id: 1,
      video_id: 2,
      track_id: "t1",
      frame_a: 0,
      frame_b: 10,
      frames: [
        { frame_index: 5, annotations: [{ id: "x", type: "AxisAlignedBox", class_id: 3, x1: 0.1, y1: 0.2, x2: 0.5, y2: 0.8, track_id: "t1" }] },
      ],
    };
    await interpolateVideoFrames(payload);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/video/interpolate`);
    expect(config.method).toBe("post");
    expect(config.data).toEqual(payload);
  });

  it("interpolateVideoFrames 返回后端 saved/count 结果", async () => {
    requestMock.mockResolvedValue(ok({ saved: [{ frame_index: 5, version: 1 }], count: 1 }));
    const res = await interpolateVideoFrames({
      task_id: 1,
      video_id: 2,
      track_id: "t1",
      frame_a: 0,
      frame_b: 10,
      frames: [],
    });
    expect(res.data.data).toEqual({ saved: [{ frame_index: 5, version: 1 }], count: 1 });
  });
});
