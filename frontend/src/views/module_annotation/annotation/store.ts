import { defineStore } from "pinia";
import { AnnotationAPI } from "@/api/module_annotation";

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
  updated_by?: { id: number; name: string };
  updated_time?: string;
}

interface AnnotationState {
  taskId: number;
  images: ImageInfo[];
  currentImageIndex: number;
  annotations: Annotation[];
  currentTool: ToolName;
  currentClassId: number;
  selectedAnnotationId: string | null;
  zoom: number;
  panX: number;
  panY: number;
  loading: boolean;
  saving: boolean;
  wsConnected: boolean;
}

export const useAnnotationStore = defineStore("annotation", {
  state: (): AnnotationState => ({
    taskId: 0,
    images: [],
    currentImageIndex: 0,
    annotations: [],
    currentTool: "select",
    currentClassId: 0,
    selectedAnnotationId: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    loading: false,
    saving: false,
    wsConnected: false,
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
    async init(taskId: number) {
      this.taskId = taskId;
      this.loading = true;
      try {
        const detailRes = await AnnotationAPI.getTaskDetail(taskId);
        const task = detailRes.data?.data;
        if (task?.dataset_id) {
          this.currentTool = "box";
          const imgRes = await AnnotationAPI.getImages(task.dataset_id);
          this.images = imgRes.data?.data || [];
          if (this.images.length > 0) {
            await this.loadAnnotations(this.images[0].id);
          }
        }
      } finally {
        this.loading = false;
      }
    },

    async loadAnnotations(imageId: number) {
      const res = await AnnotationAPI.getAnnotations(this.taskId, imageId);
      this.annotations = res.data?.data || [];
      const img = this.currentImage;
      if (img) {
        img.annotation_count = this.annotations.length;
      }
    },

    async saveAnnotations() {
      if (!this.currentImage) return;
      this.saving = true;
      try {
        await AnnotationAPI.saveAnnotations(this.currentImage.id, {
          task_id: this.taskId,
          image_id: this.currentImage.id,
          annotation_data: this.annotations,
        });
      } finally {
        this.saving = false;
      }
    },

    async goToImage(index: number) {
      if (index < 0 || index >= this.images.length) return;
      if (this.annotations.length > 0) {
        await this.saveAnnotations();
      }
      this.currentImageIndex = index;
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;
      this.selectedAnnotationId = null;
      const img = this.images[index];
      if (img) {
        await this.loadAnnotations(img.id);
      }
    },

    nextImage() {
      if (this.hasNext) this.goToImage(this.currentImageIndex + 1);
    },
    prevImage() {
      if (this.hasPrev) this.goToImage(this.currentImageIndex - 1);
    },

    addAnnotation(ann: Annotation) {
      this.annotations.push(ann);
    },

    updateAnnotation(id: string, data: Partial<Annotation>) {
      const idx = this.annotations.findIndex((a) => a.id === id);
      if (idx >= 0) {
        this.annotations[idx] = { ...this.annotations[idx], ...data };
      }
    },

    removeAnnotation(id: string) {
      this.annotations = this.annotations.filter((a) => a.id !== id);
      if (this.selectedAnnotationId === id) this.selectedAnnotationId = null;
    },

    setTool(tool: ToolName) {
      this.currentTool = tool;
    },
    setClassId(id: number) {
      this.currentClassId = id;
    },
    selectAnnotation(id: string | null) {
      this.selectedAnnotationId = id;
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
