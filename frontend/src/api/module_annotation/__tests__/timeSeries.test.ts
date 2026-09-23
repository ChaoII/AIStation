import { describe, it, expect, vi, beforeEach } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));
vi.mock("@/utils/request", () => ({ default: requestMock }));

import {
  uploadTimeSeries,
  getTimeSeriesList,
  getTimeSeriesDetail,
  getTimeSeriesContent,
  lockTimeSeries,
  unlockTimeSeries,
  saveTimeSeriesAnnotations,
  loadTimeSeriesAnnotations,
} from "../timeSeries";
import type { TimeSeriesAnnotationsPayload } from "../timeSeries";

const API_PATH = "/annotation";
const ok = (data: unknown) => ({ data: { code: 0, data, msg: "" } });

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockResolvedValue(ok(null));
});

describe("时间序列事件标注 API", () => {
  it("uploadTimeSeries 构造 multipart 并 POST /annotation/timeseries/upload，datasetId 走 query", async () => {
    const file = new File(["ts"], "a.csv", { type: "text/csv" });
    await uploadTimeSeries(file, 7);

    expect(requestMock).toHaveBeenCalledTimes(1);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/upload`);
    expect(config.method).toBe("post");
    expect(config.params).toEqual({ dataset_id: 7 });
    expect(config.data).toBeInstanceOf(FormData);
    expect(config.data.get("file")).toBe(file);
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
    expect(config.timeout).toBe(0);
  });

  it("getTimeSeriesList GET /annotation/timeseries/list，携带 dataset_id", async () => {
    await getTimeSeriesList(3);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/list`);
    expect(config.method).toBe("get");
    expect(config.params).toEqual({ dataset_id: 3 });
  });

  it("getTimeSeriesDetail GET /annotation/timeseries/detail/{id}", async () => {
    await getTimeSeriesDetail(9);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/detail/9`);
    expect(config.method).toBe("get");
  });

  it("getTimeSeriesContent GET /annotation/timeseries/content/{id}，responseType 为 text 并返回原文", async () => {
    requestMock.mockResolvedValue({ data: "time,value\n0,1\n1,2\n" });
    const res = await getTimeSeriesContent(5);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/content/5`);
    expect(config.method).toBe("get");
    expect(config.responseType).toBe("text");
    expect(res.data).toBe("time,value\n0,1\n1,2\n");
  });

  it("lockTimeSeries POST /annotation/timeseries/lock/{id}", async () => {
    await lockTimeSeries(2);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/lock/2`);
    expect(config.method).toBe("post");
  });

  it("unlockTimeSeries POST /annotation/timeseries/unlock/{id}", async () => {
    await unlockTimeSeries(2);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/timeseries/unlock/2`);
    expect(config.method).toBe("post");
  });

  it("saveTimeSeriesAnnotations POST /annotation/anno/timeseries/save，body 为 {task_id,time_series_id,annotations}", async () => {
    const payload: TimeSeriesAnnotationsPayload = {
      task_id: 1,
      time_series_id: 2,
      annotations: [{ id: "s1", type: "TimeSeriesSegment", start: 0, end: 1.5, label_id: 3 }],
    };
    await saveTimeSeriesAnnotations(payload);
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/timeseries/save`);
    expect(config.method).toBe("post");
    expect(config.data).toEqual(payload);
  });

  it("loadTimeSeriesAnnotations GET /annotation/anno/timeseries/load，参数为 task_id 与 t_id", async () => {
    requestMock.mockResolvedValue(ok({ annotation_data: [], version: 0 }));
    await loadTimeSeriesAnnotations({ task_id: 1, t_id: 2 });
    const config = requestMock.mock.calls[0][0];
    expect(config.url).toBe(`${API_PATH}/anno/timeseries/load`);
    expect(config.method).toBe("get");
    expect(config.params).toEqual({ task_id: 1, t_id: 2 });
  });
});
