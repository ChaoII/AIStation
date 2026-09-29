import type { Component } from "vue";

/** 任务媒体类型：图片任务按图像加载，视频任务按帧级加载与导航，文本任务按文档全文渲染，音频任务按波形渲染，时间序列任务按折线图渲染。 */
export type TaskMedia = "image" | "video" | "text" | "audio" | "time_series";

export type TaskShapeType =
  | "AxisAlignedBox"
  | "RotatedBox"
  | "Polygon"
  | "Polyline"
  | "Keypoint"
  | "Ocr"
  | "Classification"
  | "Cuboid";

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
/**
 * 3D 框的**米制 7-dof**，单位与坐标系见字段注释。
 *
 * 为什么单独挂一个对象而不是往 CuboidShape 上摊平：`w` / `h` 已被底面占用
 * （且是各向异性的——分别除图像宽与图像高，**不能当米用**），3D 的 l/w/h 必须
 * 用独立字段名。挂成可选对象还顺带解决了向后兼容：老标注没有 box3d，按缺省值
 * 渲染即可，不需要数据迁移。
 */
export interface Box3DMeters {
  /**
   * 底面中心在**相机系**的 x（米，右为正）。
   * 相机系：x 右 / y 下 / z 前，与 KITTI `label_2` 一致。
   */
  x: number;
  /** 底面中心在相机系的 y（米，下为正） */
  y: number;
  /** 底面中心在相机系的 z（米，**沿光轴的前向距离**，即深度） */
  z: number;
  /** 长（米，沿航向方向） */
  l: number;
  /** 宽（米，垂直于航向） */
  w: number;
  /** 高（米，竖直向上） */
  h: number;
  /**
   * 航向角，KITTI 的 `rotation_y`（**弧度**）。
   *
   * 车长轴在相机 (x, z) 平面内的方向为 `(cos ry, 0, -sin ry)`：`ry = 0` 时车头朝
   * 画面**右方**，`ry = π/2` 时朝**正前方**。与 KITTI devkit `compute_box_3d`
   * 的定义一致，也是 TorchKiln `tools/convert/kitti_to_det3d.py` 的输入约定。
   *
   * ⚠️ 不要理解成「绕相机 Y 轴从正前方起算的转角」——那会与 KITTI 差 90°。
   */
  ry: number;
}

export interface CuboidShape {
  id: string;
  type: "Cuboid";
  class_id: number;
  /** 底部矩形中心 x（归一化 [0,1]） */
  cx: number;
  /** 底部矩形中心 y（归一化 [0,1]） */
  cy: number;
  /** 底部矩形宽（归一化，按图像宽） */
  w: number;
  /** 底部矩形高（归一化，按图像高） */
  h: number;
  /** 底部矩形朝向角（弧度，绕中心，参照 rotatedBox） */
  yaw: number;
  /**
   * 图像深度（归一化 [0,1]）。
   *
   * ⚠️ 历史遗留：它此前**只是 `top_cy` 的一份拷贝**，没有任何独立语义
   * （创建时 `depth = top_cy`、拖拽时再同步一次）。真正可用的 3D 深度请用
   * `box3d.z`（米制相机系深度）。本字段继续只当「画布上的高度投影」用，
   * 保持旧数据渲染不变。
   */
  depth: number;
  /** 高度投影线在画布上的垂直偏移（归一化，顶面=底部矩形沿 y 平移 -top_cy 的投影） */
  top_cy: number;
  /** 底面第一条边（长）方向角（弧度）；缺省用 yaw（兼容旧数据） */
  angle1?: number;
  /** 底面第二条边（宽/高）方向角（弧度）；缺省为 yaw + π/2（正交矩形兼容旧数据） */
  angle2?: number;
  /**
   * 米制 3D 框（相机系 7-dof）。**可选**：老标注没有它，按缺省值渲染。
   *
   * 语义分工：2D 底面四边形（cx/cy/w/h/angle1/angle2）是**画布上的投影**，
   * 用来拖拽；`box3d` 是**训练真值**（米制、有真实尺寸与深度）。两者相关但
   * 不强制一致——图像上拖出来的投影不唯一确定深度，深度只能由人填。
   */
  box3d?: Box3DMeters;
}

export type ShapeAnnotation =
  | AxisAlignedBoxShape
  | RotatedBoxShape
  | PolygonShape
  | PolylineShape
  | OcrShape
  | KeypointShape
  | ClassificationShape
  | CuboidShape;

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
  /** 标签锚点（相对图像左上角的归一化坐标，返回 null 则用默认）；cw/ch 为图像像素宽高，供非方形图片做像素空间换算 */
  tagAnchor?(ann: Annotation, cw?: number, ch?: number): { x: number; y: number } | null;
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
  /** 画布像素宽度（brush 等按位图掩码生成的工具使用） */
  cw?: number;
  /** 画布像素高度（brush 等按位图掩码生成的工具使用） */
  ch?: number;
  /** 当前缩放（显示尺寸/原始尺寸比），用于屏幕像素级判定（如多边形首点闭合半径） */
  zoom?: number;
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
  /** 当前选中标注 id（面板据此精确锁定要编辑的标注） */
  selectedAnnotationId?: string;
  /**
   * 图像像素宽高，供面板做「归一化 ↔ 像素 ↔ 米制」换算。
   * 画布组件本来就拿得到（`cw`/`ch`），面板此前拿不到——只能显示、不能换算。
   */
  imageWidth?: number;
  imageHeight?: number;
  /** 更新一个已有标注（替换同 id 标注并标记未保存 + 入撤销历史） */
  update?: (ann: Annotation) => void;
}

export interface AnnotationTaskPlugin {
  name: string;
  label: string;
  color: string;
  /** 任务媒体类型（缺省视为图片任务） */
  media?: TaskMedia;
  renderer: TaskCanvasRenderer;
  tools: ToolDefinition[];
  create(shape: Annotation): boolean;
  /** 标注级交互（阶段 B 下沉，默认无则走壳的默认实现） */
  interaction?: AnnotationInteraction;
  /** 绘制工具运行时（阶段 C 下沉） */
  tool?: PluginTool;
  /** 多工具分发：按 name 取对应绘制工具；缺省时回退单 `tool`（向后兼容）。 */
  toolMap?: Record<string, PluginTool>;
  /** 插件级自定义面板组件（如「填充背景」等操作），由壳渲染并注入 ctx，不 import 业务 */
  panel?: Component;
  /** @deprecated 旧拖拽扩展，逐步替换为 interaction */
  onDrag?(ctx: any, handle: string): void;
}
