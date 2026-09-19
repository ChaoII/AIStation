import { defineStore } from "pinia";
import type { Annotation } from "./types";

export const useAnnotationStore = defineStore("annotationWorkbench", {
  state: () => ({
    taskId: 0,
    annotations: [] as Annotation[],
    selectedAnnotationId: "" as string,
    images: [] as any[],
    currentImageIndex: 0,
    unsaved: false,
  }),
  getters: {
    selectedAnnotation(state): Annotation | null {
      return state.annotations.find((a) => a.id === state.selectedAnnotationId) ?? null;
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
