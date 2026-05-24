/**
 * 算法配置文件模板
 * 不同算法类型有不同的配置结构
 */

export interface AlgoConfig {
  algorithm_type: string;
  version: string;
  model: {
    format: string;
    encrypt?: { enabled: boolean; key?: string; method?: string };
  };
  runtime: {
    engine: string;
    gpu: { enabled: boolean; device_id: number };
    threads: number;
    batch_size: number;
    input_width: number;
    input_height: number;
  };
  params: Record<string, any>;
  output: {
    draw_boxes: boolean;
    box_color: string;
    show_label: boolean;
    [key: string]: any;
  };
}

export const configTemplates: Record<string, AlgoConfig> = {
  INTRUSION: {
    algorithm_type: "INTRUSION",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: { confidence: 0.5, nms_threshold: 0.45 },
    output: { draw_boxes: true, box_color: "#00FF00", show_label: true },
  },
  LINE_CROSSING: {
    algorithm_type: "LINE_CROSSING",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: {
      confidence: 0.4,
      nms_threshold: 0.4,
      line: [
        [0.3, 0.5],
        [0.7, 0.5],
      ],
      direction: "both",
    },
    output: {
      draw_boxes: true,
      box_color: "#FFA500",
      show_label: true,
      draw_line: true,
      line_color: "#FF0000",
    },
  },
  FACE_DETECT: {
    algorithm_type: "FACE_DETECT",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 4,
      input_width: 640,
      input_height: 640,
    },
    params: {
      confidence: 0.6,
      nms_threshold: 0.4,
      min_face_size: 50,
      max_face_size: 500,
      similarity_threshold: 0.7,
    },
    output: { draw_boxes: true, box_color: "#00BFFF", show_label: true, blur_face: false },
  },
  CROWD_COUNT: {
    algorithm_type: "CROWD_COUNT",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: { confidence: 0.3, max_count: 100, alert_threshold: 50 },
    output: { draw_boxes: false, show_label: true, show_count: true, count_color: "#FF0000" },
  },
  FIRE_SMOKE: {
    algorithm_type: "FIRE_SMOKE",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: { confidence: 0.5, nms_threshold: 0.45 },
    output: { draw_boxes: true, box_color: "#FF0000", show_label: true },
  },
  VEHICLE_DETECT: {
    algorithm_type: "VEHICLE_DETECT",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: {
      confidence: 0.5,
      nms_threshold: 0.45,
      vehicle_types: ["car", "truck", "bus", "motorcycle"],
    },
    output: { draw_boxes: true, box_color: "#FFFF00", show_label: true, show_plate: false },
  },
  BEHAVIOR_ANALYSIS: {
    algorithm_type: "BEHAVIOR_ANALYSIS",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: { confidence: 0.5, behaviors: ["fall", "fight", "run"], alert_cooldown: 30 },
    output: { draw_boxes: true, box_color: "#FF00FF", show_label: true, draw_skeleton: false },
  },
  OBJECT_LEFT: {
    algorithm_type: "OBJECT_LEFT",
    version: "1.0.0",
    model: { format: "onnx" },
    runtime: {
      engine: "tensorrt",
      gpu: { enabled: true, device_id: 0 },
      threads: 4,
      batch_size: 1,
      input_width: 640,
      input_height: 640,
    },
    params: { confidence: 0.5, nms_threshold: 0.45, idle_seconds: 60, min_object_area: 500 },
    output: {
      draw_boxes: true,
      box_color: "#FF4500",
      show_label: true,
      highlight_idle: true,
      idle_color: "#FF0000",
    },
  },
};

export const algoTypeLabels: Record<string, string> = {
  INTRUSION: "入侵检测",
  LINE_CROSSING: "越界检测",
  FACE_DETECT: "人脸识别",
  CROWD_COUNT: "人数统计",
  FIRE_SMOKE: "烟火检测",
  VEHICLE_DETECT: "车辆识别",
  BEHAVIOR_ANALYSIS: "行为分析",
  OBJECT_LEFT: "物品遗留",
};
