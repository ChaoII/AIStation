import type { AnnotationTaskPlugin } from "../../core/types";
import { detectionPlugin } from "../detection";

/**
 * 视频目标检测插件：复用 detection 的渲染器与框选工具与 AxisAlignedBox 校验，
 * 仅替换任务名为 `video_detection` 并将媒体类型标记为 `video`。
 */
export const videoDetectionPlugin: AnnotationTaskPlugin = {
  ...detectionPlugin,
  name: "video_detection",
  label: "视频目标检测",
  media: "video",
};
