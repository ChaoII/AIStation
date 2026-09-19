<template>
  <div class="ann-workbench">
    <div class="ann-toolbar">
      <button
        v-for="t in allTools"
        :key="t.name"
        class="tool-btn"
        :class="{ active: currentTool === t.name }"
        :title="t.title"
        @click="currentTool = t.name"
      >
        {{ t.label }}
      </button>
    </div>
    <div class="ann-body">
      <AnnotationCanvas
        ref="canvasRef"
        :img-url="imgUrl"
        :image-loaded="imageLoaded"
        :cursor="toolCursor"
        @img-load="onImgLoad"
        @mousedown="onCanvasDown"
      >
        <component
          :is="plugin.renderer"
          :annotations="store.annotations"
          :cw="cw"
          :ch="ch"
          :selected-id="store.selectedAnnotationId"
          :color="clsColor"
          :cls-name="clsName"
          :font-size="fontSize"
          :tag-h="tagH"
          @ann-down="onAnnDown"
          @handle-down="onHandleDown"
        />
        <rect
          v-if="preview"
          :x="preview.x * cw"
          :y="preview.y * ch"
          :width="(preview.w) * cw"
          :height="(preview.h) * ch"
          fill="none"
          stroke="#3b82f6"
          stroke-width="1.5"
          stroke-dasharray="4 3"
        />
      </AnnotationCanvas>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import AnnotationCanvas from "./AnnotationCanvas.vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";
import { useAnnotationStore } from "./useAnnotationStore";
import { useDetectionTool } from "../tasks/detection/useDetectionTool";
import type { Annotation, AnnotationTaskPlugin } from "../types";

const props = defineProps<{
  plugin: AnnotationTaskPlugin;
  imgUrl: string;
  classes: { id: number; name: string; color: string }[];
  saveApi: (taskId: number, imageId: number, data: any[]) => Promise<any>;
  taskId: number;
  imageId: number;
}>();

const store = useAnnotationStore();
const canvasRef = ref<InstanceType<typeof AnnotationCanvas> | null>(null);
const canvas = useAnnotationCanvas();
const currentTool = ref("select");
const imageLoaded = ref(false);
const preview = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const det = useDetectionTool();

const allTools = computed(() => [
  { name: "select", label: "选择", title: "选择" },
  ...props.plugin.tools,
]);
const toolCursor = computed(() => (currentTool.value === "box" ? "crosshair" : "default"));
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const dw = computed(() => canvas.dw.value);
const dh = computed(() => canvas.dh.value);
const fontSize = 6;
const tagH = Math.max(8, fontSize + 6);

let drawStart: { x: number; y: number } | null = null;
let dragState: { type: "move" | "resize"; ann: Annotation; handle: string; startX: number; startY: number; orig: Annotation } | null = null;

function clsName(a: Annotation) {
  return props.classes.find((c) => c.id === a.class_id)?.name || "";
}
function clsColor(a: Annotation) {
  return props.classes.find((c) => c.id === a.class_id)?.color || "#3b82f6";
}

function toImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const el = document.querySelector(".annotation-canvas") as HTMLElement | null;
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return canvas.containerToImage(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
}

function onImgLoad() {
  imageLoaded.value = true;
}

function onCanvasDown(e: MouseEvent) {
  if (e.button !== 0) return;
  const p = toImagePoint(e);
  if (!p) return;
  store.selectedAnnotationId = "";
  if (currentTool.value === "box") {
    det.onStart(p);
    drawStart = p;
    preview.value = { x: p.x, y: p.y, w: 0, h: 0 };
  }
}

function onAnnDown(e: MouseEvent, ann: Annotation) {
  store.selectedAnnotationId = ann.id;
  dragState = {
    type: "move",
    ann,
    handle: "",
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}

function onHandleDown(e: MouseEvent, ann: Annotation, handle: string) {
  store.selectedAnnotationId = ann.id;
  dragState = {
    type: "resize",
    ann,
    handle,
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}

function onMove(e: MouseEvent) {
  if (drawStart && currentTool.value === "box") {
    const p = toImagePoint(e);
    if (!p) return;
    preview.value = {
      x: Math.min(drawStart.x, p.x),
      y: Math.min(drawStart.y, p.y),
      w: Math.abs(p.x - drawStart.x),
      h: Math.abs(p.y - drawStart.y),
    };
    return;
  }
  if (dragState) {
    const dx = (e.clientX - dragState.startX) / dw.value;
    const dy = (e.clientY - dragState.startY) / dh.value;
    if (dragState.type === "resize") det.onDrag(dragState.ann, dragState.handle, dx, dy);
    else det.onDragMove(dragState.ann, dx, dy);
    store.markUnsaved();
  }
}

function onUp() {
  if (drawStart && currentTool.value === "box") {
    const p = preview.value;
    const created = det.onMoveEnd(p ? { x: p.x + p.w, y: p.y + p.h } : ({ x: 0, y: 0 } as any));
    preview.value = null;
    drawStart = null;
    if (created && props.plugin.create(created)) {
      store.annotations.push(created);
      store.markUnsaved();
    }
    return;
  }
  dragState = null;
}

onMounted(() => {
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
});
onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMove);
  window.removeEventListener("mouseup", onUp);
});
</script>

<style scoped>
.ann-workbench {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}
.ann-toolbar {
  display: flex;
  gap: 8px;
  padding: 8px;
}
.tool-btn {
  cursor: pointer;
}
.tool-btn.active {
  color: var(--el-color-primary);
}
.ann-body {
  flex: 1;
  position: relative;
  min-height: 0;
}
</style>
