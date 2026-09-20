export type TaskShapeType =
  "AxisAlignedBox" | "RotatedBox" | "Polygon" | "Keypoint" | "Ocr" | "Classification";

export interface Point {
  x: number;
  y: number;
}

/** 各形状的判别联合字段（非破坏性，供新增代码与泛型工具引用） */
export interface AxisAlignedBoxShape {
  id: string;
  type: "AxisAlignedBox";
  class_id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
export interface RotatedBoxShape {
  id: string;
  type: "RotatedBox";
  class_id: number;
  cx: number;
  cy: number;
  width: number;
  height: number;
  angle: number;
}
export interface PolygonShape {
  id: string;
  type: "Polygon";
  class_id: number;
  points: Point[];
}
export interface OcrShape {
  id: string;
  type: "Ocr";
  class_id: number;
  points: Point[];
  text: string;
  source?: "rect" | "quad";
}
export interface KeypointShape {
  id: string;
  type: "Keypoint";
  class_id: number;
  keypoints: { x: number; y: number; name: string; visibility: string }[];
  bounding_box?: { cx: number; cy: number; width: number; height: number; angle: number };
}
export interface ClassificationShape {
  id: string;
  type: "Classification";
  class_id: number;
  class_ids?: number[];
}

export type ShapeAnnotation =
  | AxisAlignedBoxShape
  | RotatedBoxShape
  | PolygonShape
  | OcrShape
  | KeypointShape
  | ClassificationShape;

/** 兼容接口：存量访问仍可用松散字段；新代码优先用 ShapeAnnotation 判别联合 */
export interface Annotation {
  id: string;
  type: TaskShapeType;
  class_id: number;
  [key: string]: any;
}

export interface ToolDefinition {
  name: string;
  label: string;
  title: string;
}

/** 各任务 Canvas 组件的公共 props 契约 */
export interface TaskCanvasProps {
  annotations: Annotation[];
  cw: number;
  ch: number;
  selectedId: string;
  color: (a: Annotation) => string;
  clsName: (a: Annotation) => string;
  fontSize: number;
  tagH: number;
  stroke?: number;
  selStroke?: number;
  pointerNone?: boolean;
}

/** 各任务 Canvas 组件的公共 emits 契约 */
export interface TaskCanvasEmits {
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
  (e: "rotate-down", ev: MouseEvent, ann: Annotation): void;
}

/** 任务渲染组件（SVG 层）：任意 Vue 组件，props/emits 由运行时交互契约约束 */
export type TaskCanvasRenderer = any;

export interface AnnotationTaskPlugin {
  name: string;
  label: string;
  color: string;
  renderer: TaskCanvasRenderer;
  tools: ToolDefinition[];
  create(shape: Annotation): boolean;
  onDrag?(ctx: any, handle: string): void;
}
