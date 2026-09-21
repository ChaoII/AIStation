import type { Component } from "vue";

export type TaskShapeType =
  "AxisAlignedBox" | "RotatedBox" | "Polygon" | "Polyline" | "Keypoint" | "Ocr" | "Classification";

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
export interface PolylineShape {
  id: string;
  type: "Polyline";
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
  | PolylineShape
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

/** 绘制运行上下文（壳在画布事件时传入） */
export interface DrawContext {
  /** 归一化图像坐标 */
  point?: Point | null;
  /** 原始鼠标事件 */
  event: MouseEvent;
  /** 当前任务类别（含 keypoint_names） */
  classes?: any[];
  /** 当前选中类别 id */
  selectedClassId?: number | null;
  /** 新增关键点的可见性（keypoint） */
  visibility?: string;
}

/** 任务绘制工具运行时（阶段 C 下沉） */
export interface PluginTool {
  /** 工具名（= tools[0].name），壳据此判断绘制模式 */
  name: string;
  /** 绘制激活时挂载的临时预览组件（SVG 根，用 <g>） */
  preview?: TaskCanvasRenderer;
  /** 绘制状态（字段为 ref），供 preview 读取 */
  state?: Record<string, any>;
  /** 按下：返回合法标注则壳 push（如 rotated_box 第 3 步 / ocr 第 2 点） */
  down?(ctx: DrawContext): Annotation | null;
  /** 移动：更新预览 */
  move?(ctx: DrawContext): void;
  /** 抬起：返回合法标注则壳 push */
  up?(ctx: DrawContext): Annotation | null;
  /** 双击：闭合多边形 / 进入包围盒 / OCR 闭合，返回标注则壳 push */
  dblclick?(ctx: DrawContext): Annotation | null;
  /** 切换工具/换图/清空时重置绘制状态 */
  reset?(): void;
  /** 切换工具内部模式（如 OCR rect/quad 切换），实现内自带 reset */
  toggleMode?(): void;
  /** 工具专属键盘快捷键（返回 true 表示已处理，壳不再继续执行通用/切工具逻辑） */
  keydown?(e: KeyboardEvent): boolean;
}

/** 插件级自定义面板的运行时上下文（壳渲染 panel 组件时注入，不 import 业务） */
export interface PluginPanelContext {
  /** 任务类别列表 */
  classes: any[];
  /** 当前选中类别 id */
  selectedClassId: number | null;
  /** 提交一个新标注（壳会对齐 create 校验 + push + 历史） */
  commit: (ann: Annotation) => void;
  /** 当前全部标注（只读），供面板查询已有背景等 */
  annotations?: Annotation[];
  /** 按 id 移除标注（面板替换/清理已有背景用） */
  remove?: (ids: string[]) => void;
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
  /** 绘制工具运行时（阶段 C 下沉） */
  tool?: PluginTool;
  /** 插件级自定义面板组件（如「填充背景」等操作），由壳渲染并注入 ctx，不 import 业务 */
  panel?: Component;
  /** @deprecated 旧拖拽扩展，逐步替换为 interaction */
  onDrag?(ctx: any, handle: string): void;
}
