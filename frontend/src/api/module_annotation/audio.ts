import request from "@/utils/request";

const API_PATH = "/annotation";

/**
 * 音频元数据（与后端 `AudioService.audio_out` 出参一致）。
 */
export interface AudioMeta {
  id: number;
  dataset_id: number;
  name: string;
  object_key: string;
  duration: number;
  sample_rate: number;
  channels: number;
  bitrate: number;
  size_bytes: number;
  status: "unannotated" | "in_progress" | "annotated";
  locked_by: number | null;
  locked_at: string | null;
  annotation_count: number;
  play_url: string;
  created_time?: string;
  updated_time?: string;
}

/**
 * 音频事件片段（秒级 [start, end)，结构同后端 AudioSegment 校验）。
 */
export interface AudioSegment {
  id: string;
  type: "AudioSegment";
  start: number;
  end: number;
  label_id: number;
}

/** 音频事件标注 = 片段。 */
export type AudioAnnotation = AudioSegment;

/** 音频事件标注保存载荷。 */
export interface AudioAnnotationsPayload {
  task_id: number;
  audio_id: number;
  annotations: AudioAnnotation[];
}

/**
 * 上传音频（multipart，datasetId 走 query）。
 * 音频可能较大，不设超时，由调用方处理加载态。
 */
export function uploadAudio(file: File, datasetId: number) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ApiResponse<AudioMeta>>({
    url: `${API_PATH}/audio/upload`,
    method: "post",
    params: { dataset_id: datasetId },
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 0,
  });
}

/** 查询数据集下的音频列表。 */
export function getAudioList(datasetId: number) {
  return request<ApiResponse<{ items: AudioMeta[] }>>({
    url: `${API_PATH}/audio/list`,
    method: "get",
    params: { dataset_id: datasetId },
  });
}

/** 查询单个音频详情。 */
export function getAudioDetail(id: number) {
  return request<ApiResponse<AudioMeta>>({
    url: `${API_PATH}/audio/detail/${id}`,
    method: "get",
  });
}

/** 获取音频播放地址（presigned url，读 response.data 的 play_url）。 */
export async function getAudioPlayUrl(id: number): Promise<string> {
  const res = await request<ApiResponse<{ play_url: string }>>({
    url: `${API_PATH}/audio/play-url/${id}`,
    method: "get",
  });
  return res.data.data.play_url;
}

/** 锁定音频（按音频整体加锁）。 */
export function lockAudio(id: number) {
  return request<ApiResponse<{ locked: boolean; locked_by: number | null }>>({
    url: `${API_PATH}/audio/lock/${id}`,
    method: "post",
  });
}

/** 解锁音频。 */
export function unlockAudio(id: number) {
  return request<ApiResponse>({
    url: `${API_PATH}/audio/unlock/${id}`,
    method: "post",
  });
}

/** 保存音频事件标注。 */
export function saveAudioAnnotations(payload: AudioAnnotationsPayload) {
  return request<ApiResponse<{ version: number; annotation_count: number }>>({
    url: `${API_PATH}/anno/audio/save`,
    method: "post",
    data: payload,
  });
}

/** 读取音频事件标注。 */
export function loadAudioAnnotations(params: { task_id: number; audio_id: number }) {
  return request<ApiResponse<{ annotation_data: AudioAnnotation[]; version: number }>>({
    url: `${API_PATH}/anno/audio/load`,
    method: "get",
    params: { task_id: params.task_id, a_id: params.audio_id },
  });
}
