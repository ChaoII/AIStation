import request from "@/utils/request";

const API_PATH = "/annotation";

/**
 * 视频元数据（与后端 `AnnotationVideoModel._video_out` 出参一致）。
 */
export interface VideoAnnotationMeta {
  id: number;
  dataset_id: number;
  name: string;
  object_key: string;
  width: number;
  height: number;
  duration: number;
  fps: number;
  frame_count: number;
  status: "unannotated" | "in_progress" | "annotated";
  locked_by: number | null;
  annotation_count: number;
  play_url: string;
}

/**
 * 视频帧标注（AxisAlignedBox，归一化 [0,1]，结构同后端 `AxisAlignedBoxSchema`）。
 */
export interface VideoFrameAnnotation {
  id?: string | null;
  type?: string;
  class_id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * 上传视频（multipart，datasetId 走 query）。
 * 视频可能较大，不设超时，由调用方处理加载态。
 */
export function uploadVideo(datasetId: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ApiResponse<VideoAnnotationMeta>>({
    url: `${API_PATH}/video/upload`,
    method: "post",
    params: { dataset_id: datasetId },
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 0,
  });
}

/** 查询数据集下的视频列表。 */
export function getVideoList(datasetId: number) {
  return request<ApiResponse<{ items: VideoAnnotationMeta[] }>>({
    url: `${API_PATH}/video/list`,
    method: "get",
    params: { dataset_id: datasetId },
  });
}

/** 查询单个视频详情。 */
export function getVideoDetail(id: number) {
  return request<ApiResponse<VideoAnnotationMeta>>({
    url: `${API_PATH}/video/detail/${id}`,
    method: "get",
  });
}

/** 获取视频播放地址。 */
export function getVideoPlayUrl(id: number) {
  return request<ApiResponse<{ play_url: string }>>({
    url: `${API_PATH}/video/play-url/${id}`,
    method: "get",
  });
}

/** 锁定视频（按视频整体加锁）。 */
export function lockVideo(id: number) {
  return request<ApiResponse<{ locked: boolean; locked_by: number }>>({
    url: `${API_PATH}/video/lock/${id}`,
    method: "post",
  });
}

/** 解锁视频。 */
export function unlockVideo(id: number) {
  return request<ApiResponse>({
    url: `${API_PATH}/video/unlock/${id}`,
    method: "post",
  });
}

/** 保存某视频帧的标注。 */
export function saveVideoAnnotations(
  taskId: number,
  videoId: number,
  frameIndex: number,
  annotations: VideoFrameAnnotation[]
) {
  return request<ApiResponse<{ version: number; annotation_count: number }>>({
    url: `${API_PATH}/anno/video/save`,
    method: "post",
    data: { task_id: taskId, video_id: videoId, frame_index: frameIndex, annotations },
  });
}

/** 读取某视频帧的标注。 */
export function loadVideoAnnotations(taskId: number, videoId: number, frameIndex: number) {
  return request<ApiResponse<VideoFrameAnnotation[]>>({
    url: `${API_PATH}/anno/video/load`,
    method: "get",
    params: { task_id: taskId, v_id: videoId, frame_index: frameIndex },
  });
}
