import { describe, it, expect, vi, beforeEach } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: requestMock }));

import {
  uploadAudio,
  getAudioList,
  getAudioDetail,
  getAudioPlayUrl,
  lockAudio,
  unlockAudio,
  saveAudioAnnotations,
  loadAudioAnnotations,
} from "../audio";
import type { AudioAnnotationsPayload } from "../audio";

const API_PATH = "/annotation";
const ok = (data: unknown) => ({ data: { code: 0, data, msg: "" } });

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockResolvedValue(ok(null));
});

describe("音频事件标注 API", () => {
  it("uploadAudio 构造 multipart 并 POST /annotation/audio/upload，datasetId 走 query", async () => {
    const file = new File(["a"], "a.mp3", { type: "audio/mpeg" });
    await uploadAudio(file, 7);

    expect(requestMock).toHaveBeenCalledTimes(1);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/upload`);
    expect(config.method).toBe("post");
    expect(config.params).toEqual({ dataset_id: 7 });
    expect(config.data).toBeInstanceOf(FormData);
    expect(config.data.get("file")).toBe(file);
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
    expect(config.timeout).toBe(0);
  });

  it("getAudioList GET /annotation/audio/list，携带 dataset_id", async () => {
    await getAudioList(3);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/list`);
    expect(config.method).toBe("get");
    expect(config.params).toEqual({ dataset_id: 3 });
  });

  it("getAudioDetail GET /annotation/audio/detail/{id}", async () => {
    await getAudioDetail(9);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/detail/9`);
    expect(config.method).toBe("get");
  });

  it("getAudioPlayUrl 返回 response.data 中的 presigned play_url", async () => {
    requestMock.mockResolvedValue(ok({ play_url: "http://cdn/x.mp3" }));
    const url = await getAudioPlayUrl(4);
    expect(url).toBe("http://cdn/x.mp3");
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/play-url/4`);
    expect(config.method).toBe("get");
  });

  it("lockAudio POST /annotation/audio/lock/{id}", async () => {
    await lockAudio(2);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/lock/2`);
    expect(config.method).toBe("post");
  });

  it("unlockAudio POST /annotation/audio/unlock/{id}", async () => {
    await unlockAudio(2);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/audio/unlock/2`);
    expect(config.method).toBe("post");
  });

  it("saveAudioAnnotations POST /annotation/anno/audio/save，body 为 {task_id,audio_id,annotations}", async () => {
    const payload: AudioAnnotationsPayload = {
      task_id: 1,
      audio_id: 2,
      annotations: [{ id: "s1", type: "AudioSegment", start: 0, end: 1.5, label_id: 3 }],
    };
    await saveAudioAnnotations(payload);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/audio/save`);
    expect(config.method).toBe("post");
    expect(config.data).toEqual(payload);
  });

  it("loadAudioAnnotations GET /annotation/anno/audio/load，参数为 task_id 与 a_id", async () => {
    requestMock.mockResolvedValue(ok({ annotation_data: [], version: 0 }));
    await loadAudioAnnotations({ task_id: 1, audio_id: 2 });
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/audio/load`);
    expect(config.method).toBe("get");
    expect(config.params).toEqual({ task_id: 1, a_id: 2 });
  });
});
