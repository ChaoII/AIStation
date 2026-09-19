import { defineStore } from "pinia";
import type { Annotation } from "./types";

export const useAnnotationStore = defineStore("annotationWorkbench", {
  state: () => ({
    taskId: 0,
    task: null as any,
    annotations: [] as Annotation[],
    selectedAnnotationId: "" as string,
    images: [] as any[],
    currentImageIndex: 0,
    loading: false,
    annotatedCount: 0,
    totalCount: 0,
    unsaved: false,
  }),
  getters: {
    selectedAnnotation(state): Annotation | null {
      return state.annotations.find((a) => a.id === state.selectedAnnotationId) ?? null;
    },
    currentImage(state): any {
      return state.images[state.currentImageIndex] ?? null;
    },
    currentImageId(state): number | null {
      return state.images[state.currentImageIndex]?.id ?? null;
    },
    progress(state): number {
      if (!state.totalCount) return 0;
      return Math.round((state.annotatedCount / state.totalCount) * 100);
    },
  },
  actions: {
    reset() {
      this.annotations = [];
      this.selectedAnnotationId = "";
      this.unsaved = false;
    },
    markUnsaved() {
      this.unsaved = true;
    },
  },
});
