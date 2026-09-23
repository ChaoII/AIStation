import request from "@/utils/request";

const API_PATH = "/annotation";

/**
 * 时间序列元数据（与后端 `TimeSeriesService.series_out` 出参一致）。
 */
export interface TimeSeriesMeta {
  id: number;
  dataset_id: number;
  name: string;
  object_key: string;
  time_column: string;
  value_columns: string[];
  row_count: number;
  time_unit: string;
  start_time: number;
  end_time: number;
  size_bytes: number;
  status: "unannotated" | "in_progress" | "annotated";
  locked_by: number | null;
  locked_at: string | null;
  annotation_count: number;
}

/**
 * 时间序列事件片段（时间戳 [start, end)，结构同后端 TimeSeriesSegment 校验）。
 */
export interface TimeSeriesSegment {
  id: string;
  type: "TimeSeriesSegment";
  start: number;
  end: number;
  label_id: number;
}

/** 时间序列事件标注 = 片段。 */
export type TimeSeriesAnnotation = TimeSeriesSegment;

/** 时间序列事件标注保存载荷。 */
export interface TimeSeriesAnnotationsPayload {
  task_id: number;
  time_series_id: number;
  annotations: TimeSeriesAnnotation[];
}

/**
 * 上传时间序列 CSV（multipart，datasetId 走 query）。
 * 文件可能较大，不设超时，由调用方处理加载态。
 */
export function uploadTimeSeries(file: File, datasetId: number) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ApiResponse<TimeSeriesMeta>>({
    url: `${API_PATH}/timeseries/upload`,
    method: "post",
    params: { dataset_id: datasetId },
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 0,
  });
}

/** 查询数据集下的时间序列列表。 */
export function getTimeSeriesList(datasetId: number) {
  return request<ApiResponse<{ items: TimeSeriesMeta[] }>>({
    url: `${API_PATH}/timeseries/list`,
    method: "get",
    params: { dataset_id: datasetId },
  });
}

/** 查询单个时间序列详情。 */
export function getTimeSeriesDetail(id: number) {
  return request<ApiResponse<TimeSeriesMeta>>({
    url: `${API_PATH}/timeseries/detail/${id}`,
    method: "get",
  });
}

/** 获取时间序列原始 CSV 文本（response.data 为字符串原文）。 */
export function getTimeSeriesContent(id: number) {
  return request<string>({
    url: `${API_PATH}/timeseries/content/${id}`,
    method: "get",
    responseType: "text",
  });
}

/** 锁定时间序列（按序列整体加锁）。 */
export function lockTimeSeries(id: number) {
  return request<ApiResponse<{ locked: boolean; locked_by: number | null }>>({
    url: `${API_PATH}/timeseries/lock/${id}`,
    method: "post",
  });
}

/** 解锁时间序列。 */
export function unlockTimeSeries(id: number) {
  return request<ApiResponse>({
    url: `${API_PATH}/timeseries/unlock/${id}`,
    method: "post",
  });
}

/** 保存时间序列事件标注。 */
export function saveTimeSeriesAnnotations(payload: TimeSeriesAnnotationsPayload) {
  return request<ApiResponse<{ version: number; annotation_count: number }>>({
    url: `${API_PATH}/anno/timeseries/save`,
    method: "post",
    data: payload,
  });
}

/** 读取时间序列事件标注。 */
export function loadTimeSeriesAnnotations(params: { task_id: number; t_id: number }) {
  return request<ApiResponse<{ annotation_data: TimeSeriesAnnotation[]; version: number }>>({
    url: `${API_PATH}/anno/timeseries/load`,
    method: "get",
    params: { task_id: params.task_id, t_id: params.t_id },
  });
}
