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
    box_color?: string;
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

export interface ParamMeta {
  label: string;
  type: "float" | "int" | "bool" | "select" | "multi-select" | "string" | "polyline";
  default: any;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  hint?: string;
  options?: { label: string; value: string }[];
}

export const paramMetaTemplates: Record<string, Record<string, ParamMeta>> = {
  INTRUSION: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "检测置信度阈值，低于此值的结果将被过滤",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.45,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "非极大值抑制阈值，值越小重复框越少",
    },
  },
  LINE_CROSSING: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.4,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "目标检测置信度",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.4,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "非极大值抑制阈值",
    },
    line: {
      label: "越界线坐标",
      type: "polyline",
      default: [
        [0.3, 0.5],
        [0.7, 0.5],
      ],
      unit: "归一化坐标",
      hint: "在画面中绘制一条虚拟线，两点确定一条直线",
    },
    direction: {
      label: "检测方向",
      type: "select",
      default: "both",
      options: [
        { label: "双向", value: "both" },
        { label: "A→B", value: "a_to_b" },
        { label: "B→A", value: "b_to_a" },
      ],
      hint: "越界方向过滤器",
    },
  },
  FACE_DETECT: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.6,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "人脸检测置信度",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.4,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "",
    },
    min_face_size: {
      label: "最小人脸",
      type: "int",
      default: 50,
      min: 20,
      max: 300,
      step: 10,
      unit: "像素",
      hint: "小于此尺寸的人脸将被忽略",
    },
    max_face_size: {
      label: "最大人脸",
      type: "int",
      default: 500,
      min: 100,
      max: 2000,
      step: 50,
      unit: "像素",
      hint: "大于此尺寸的人脸将被忽略",
    },
    similarity_threshold: {
      label: "比对阈值",
      type: "float",
      default: 0.7,
      min: 0.5,
      max: 1.0,
      step: 0.05,
      hint: "人脸比对相似度阈值，越高越严格",
    },
  },
  CROWD_COUNT: {
    confidence: {
      label: "检测置信度",
      type: "float",
      default: 0.3,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "人员检测置信度阈值",
    },
    max_count: {
      label: "人数上限",
      type: "int",
      default: 100,
      min: 10,
      max: 500,
      step: 10,
      unit: "人",
      hint: "区域内最多检测人数",
    },
    alert_threshold: {
      label: "告警阈值",
      type: "int",
      default: 50,
      min: 10,
      max: 500,
      step: 5,
      unit: "人",
      hint: "超过此人数触发聚集告警",
    },
  },
  FIRE_SMOKE: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "烟火检测置信度，建议设 0.4~0.6 之间",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.45,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "",
    },
  },
  VEHICLE_DETECT: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "车辆检测置信度",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.45,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "",
    },
    vehicle_types: {
      label: "检测车型",
      type: "multi-select",
      default: ["car", "truck", "bus", "motorcycle"],
      options: [
        { label: "轿车", value: "car" },
        { label: "卡车", value: "truck" },
        { label: "巴士", value: "bus" },
        { label: "摩托车", value: "motorcycle" },
        { label: "自行车", value: "bicycle" },
        { label: "三轮车", value: "tricycle" },
      ],
      hint: "选择需要检测的车辆类型",
    },
  },
  BEHAVIOR_ANALYSIS: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "行为检测置信度",
    },
    behaviors: {
      label: "检测行为",
      type: "multi-select",
      default: ["fall", "fight", "run"],
      options: [
        { label: "摔倒", value: "fall" },
        { label: "打架", value: "fight" },
        { label: "奔跑", value: "run" },
        { label: "徘徊", value: "wander" },
        { label: "挥手", value: "wave" },
      ],
      hint: "选择需要检测的行为类型",
    },
    alert_cooldown: {
      label: "告警冷却",
      type: "int",
      default: 30,
      min: 5,
      max: 300,
      step: 5,
      unit: "秒",
      hint: "同一行为触发告警后的冷却时间",
    },
  },
  OBJECT_LEFT: {
    confidence: {
      label: "置信度阈值",
      type: "float",
      default: 0.5,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "物品检测置信度",
    },
    nms_threshold: {
      label: "NMS 阈值",
      type: "float",
      default: 0.45,
      min: 0.1,
      max: 1.0,
      step: 0.05,
      hint: "",
    },
    idle_seconds: {
      label: "停留阈值",
      type: "int",
      default: 60,
      min: 10,
      max: 600,
      step: 10,
      unit: "秒",
      hint: "物品静止超过此时间判定为遗留物",
    },
    min_object_area: {
      label: "最小面积",
      type: "int",
      default: 500,
      min: 100,
      max: 10000,
      step: 100,
      unit: "像素²",
      hint: "小于此面积的物品将被忽略",
    },
  },
};
