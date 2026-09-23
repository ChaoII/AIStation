import { describe, it, expect, vi, beforeEach } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: requestMock }));

import { saveVideoEventAnnotations, loadVideoEventAnnotations } from "../videoEvent";
import type { VideoEventPayload } from "../videoEvent";

const API_PATH = "/annotation";
const ok = (data: unknown) => ({ data: { code: 0, data, msg: "" } });

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockResolvedValue(ok(null));
});

describe("视频事件标注 API", () => {
  it("saveVideoEventAnnotations POST /annotation/anno/video-event/save，body 为 {task_id,video_id,segments}", async () => {
    const payload: VideoEventPayload = {
      task_id: 1,
      video_id: 2,
      segments: [{ id: "s1", type: "VideoSegment", start: 0, end: 1.5, label_id: 3 }],
    };
    await saveVideoEventAnnotations(payload);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/video-event/save`);
    expect(config.method).toBe("post");
    expect(config.data).toEqual(payload);
  });

  it("loadVideoEventAnnotations GET /annotation/anno/video-event/load，参数为 task_id 与 video_id", async () => {
    requestMock.mockResolvedValue(ok({ annotation_data: [], version: 0 }));
    await loadVideoEventAnnotations({ task_id: 1, video_id: 2 });
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/video-event/load`);
    expect(config.method).toBe("get");
    expect(config.params).toEqual({ task_id: 1, video_id: 2 });
  });
});
