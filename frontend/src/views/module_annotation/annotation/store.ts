import { defineStore } from "pinia";

export type ToolName =
  | "select"
  | "box"
  | "rotated_box"
  | "polygon"
  | "keypoint"
  | "ocr"
  | "classification"
  | "pan"
  | "zoom";

export interface Point {
  x: number;
  y: number;
}

export interface Annotation {
  id: string;
  type: string;
  class_id: number;
  [key: string]: any;
}

export interface ImageInfo {
  id: number;
  dataset_id: number;
  filename: string;
  object_key: string;
  width: number;
  height: number;
  status: string;
  locked_by: number | null;
  annotation_count: number;
  thumbnail_key?: string | null;
  thumbnail_url?: string | null;
  updated_by?: { id: number; name: string };
  updated_time?: string;
}

interface AnnotationState {
  taskId: number;
  images: ImageInfo[];
  currentImageIndex: number;
  annotations: Annotation[];
  currentTool: ToolName;
  selectedAnnotationId: string | null;
  zoom: number;
  panX: number;
  panY: number;
  loading: boolean;
  saving: boolean;
}

export const useAnnotationStore = defineStore("annotation", {
  state: (): AnnotationState => ({
    taskId: 0,
    images: [],
    currentImageIndex: 0,
    annotations: [],
    currentTool: "select",
    selectedAnnotationId: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    loading: false,
    saving: false,
  }),

  getters: {
    currentImage(state): ImageInfo | null {
      return state.images[state.currentImageIndex] || null;
    },
    hasNext(state): boolean {
      return state.currentImageIndex < state.images.length - 1;
    },
    hasPrev(state): boolean {
      return state.currentImageIndex > 0;
    },
  },

  actions: {
    setTool(tool: ToolName) {
      this.currentTool = tool;
    },
    setZoom(z: number) {
      this.zoom = Math.max(0.1, Math.min(10, z));
    },
    setPan(x: number, y: number) {
      this.panX = x;
      this.panY = y;
    },
  },
});
