export type TaskShapeType =
  | "AxisAlignedBox"
  | "RotatedBox"
  | "Polygon"
  | "Keypoint"
  | "Ocr"
  | "Classification";

export interface Point {
  x: number;
  y: number;
}

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

export interface AnnotationTaskPlugin {
  name: string;
  label: string;
  color: string;
  renderer: any;
  tools: ToolDefinition[];
  create(shape: Annotation): boolean;
  onDrag?(ctx: any, handle: string): void;
}
