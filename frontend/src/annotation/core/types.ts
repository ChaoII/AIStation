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

/** 标注级拖拽交互上下文（壳派发时传入，插件据此更新草稿标注） */
export interface DragContext {
  /** 当前草稿标注（draft，可能已由插件修改） */
  ann: Annotation;
  /** 拖拽起点快照 */
  orig: Annotation;
  /** 当前激活 handle（移动/缩放/顶点标识） */
  handle: string;
  /** 归一化位移 */
  dx: number;
  dy: number;
  /** 画布尺寸 */
  cw: number;
  ch: number;
  /** 鼠标在图像坐标的点（归一化） */
  point?: { x: number; y: number };
  /** 屏幕坐标：作用中心（旋转框中心等） */
  center?: { x: number; y: number };
  /** 屏幕坐标：拖拽起点 */
  start?: { x: number; y: number };
  /** 屏幕坐标：当前鼠标端点 */
  client?: { x: number; y: number };
  /** 触发一次重绘（draft 更新后通知壳刷新） */
  trigger: () => void;
}

/** 标注级交互能力（可选）。插件声明后，壳在 onMove/onHandleDown/tagStyle 中优先派发。 */
export interface AnnotationInteraction {
  /** 整体移动标注 */
  move?(ctx: DragContext): void;
  /** 缩放（8 向手柄 / 角点） */
  resize?(ctx: DragContext): void;
  /** 旋转（RotatedBox） */
  rotate?(ctx: DragContext): void;
  /** 顶点级移动（polygon/ocr/keypoint） */
  vertexMove?(ctx: DragContext): void;
  /** 顶点插入（polygon 中点） */
  vertexInsert?(ann: Annotation, handle: string): void;
  /** 顶点删除（alt+点击） */
  vertexDelete?(ann: Annotation, handle: string): void;
  /** 标签锚点（相对图像左上角的归一化坐标，返回 null 则用默认） */
  tagAnchor?(ann: Annotation): { x: number; y: number } | null;
}

export interface AnnotationTaskPlugin {
  name: string;
  label: string;
  color: string;
  renderer: TaskCanvasRenderer;
  tools: ToolDefinition[];
  create(shape: Annotation): boolean;
  /** 标注级交互（阶段 B 下沉，默认无则走壳的默认实现） */
  interaction?: AnnotationInteraction;
  /** @deprecated 旧拖拽扩展，逐步替换为 interaction */
  onDrag?(ctx: any, handle: string): void;
}
