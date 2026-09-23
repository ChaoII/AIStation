import request from "@/utils/request";

const API_PATH = "/annotation";

/**
 * 视频事件片段（秒级 [start, end)，结构同后端 `VideoSegmentSchema`）。
 */
export interface VideoSegment {
  id: string;
  type: "VideoSegment";
  start: number;
  end: number;
  label_id: number;
}

/**
 * 视频时间轴事件标注 = 片段。
 */
export type VideoEventAnnotation = VideoSegment;

/**
 * 视频元数据（与后端 `AnnotationVideoModel._video_out` 出参一致，供时间轴/面板读取时长等）。
 */
export interface VideoMeta {
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
  locked_at: string | null;
  annotation_count: number;
  play_url: string;
  /** 同源内容地址（前端构造，非后端返回）。 */
  content_url?: string;
}

/** 视频事件标注保存载荷。 */
export interface VideoEventPayload {
  task_id: number;
  video_id: number;
  segments: VideoEventAnnotation[];
}

/** 保存视频时间轴事件标注。 */
export function saveVideoEventAnnotations(payload: VideoEventPayload) {
  return request<ApiResponse<{ version: number; annotation_count: number }>>({
    url: `${API_PATH}/anno/video-event/save`,
    method: "post",
    data: payload,
  });
}

/** 读取视频时间轴事件标注。 */
export function loadVideoEventAnnotations(params: { task_id: number; video_id: number }) {
  return request<ApiResponse<{ annotation_data: VideoEventAnnotation[]; version: number }>>({
    url: `${API_PATH}/anno/video-event/load`,
    method: "get",
    params: { task_id: params.task_id, video_id: params.video_id },
  });
}
