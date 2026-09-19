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
        @dblclick="onDblClick"
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
          @rotate-down="onRotateDown"
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
        <rect
          v-if="rbPreview"
          :x="rbPreview.cx * cw - (rbPreview.width * cw) / 2"
          :y="rbPreview.cy * ch - (rbPreview.height * ch) / 2"
          :width="rbPreview.width * cw"
          :height="rbPreview.height * ch"
          fill="none"
          stroke="#f56c6c"
          stroke-width="1.5"
          stroke-dasharray="4 3"
          :transform="`rotate(${(rbPreview.angle * 180) / Math.PI} ${rbPreview.cx * cw} ${rbPreview.cy * ch})`"
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
import { useRotatedTool, rotatedBoxFromEdgeAndPoint } from "../tasks/rotatedBox/useRotatedTool";
import { useSegmentTool } from "../tasks/segmentation/useSegmentTool";
import type { Annotation, AnnotationTaskPlugin } from "./types";

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
const rot = useRotatedTool();
const seg = useSegmentTool();
const rbPreview = ref<{ cx: number; cy: number; width: number; height: number; angle: number } | null>(null);

const allTools = computed(() => [
  { name: "select", label: "选择", title: "选择" },
  ...props.plugin.tools,
]);
const toolCursor = computed(() =>
  currentTool.value === "box" || currentTool.value === "rotated_box" ? "crosshair" : "default"
);
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const dw = computed(() => canvas.dw.value);
const dh = computed(() => canvas.dh.value);
const fontSize = 6;
const tagH = Math.max(8, fontSize + 6);

let drawStart: { x: number; y: number } | null = null;
let rbLast: { x: number; y: number } | null = null;
let dragState:
  | { type: "move" | "resize" | "rotate" | "poly-vertex"; ann: Annotation; handle: string; startX: number; startY: number; orig: Annotation }
  | null = null;

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

function onDblClick() {
  if (currentTool.value === "polygon") {
    const created = seg.closePolygon();
    if (created && props.plugin.create(created)) {
      store.annotations.push(created);
      store.markUnsaved();
    }
  }
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
  } else if (currentTool.value === "rotated_box") {
    rbLast = p;
    const created = rot.onStep(p);
    if (created && props.plugin.create(created)) {
      store.annotations.push(created);
      store.markUnsaved();
    }
  } else if (currentTool.value === "polygon") {
    seg.addPoint(p);
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
  if (handle.startsWith("poly-ins-")) {
    const idx = parseInt(handle.replace("poly-ins-", ""), 10);
    if (!isNaN(idx) && ann.points?.length) {
      const a = ann.points[idx];
      const b = ann.points[(idx + 1) % ann.points.length];
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      ann.points.splice(idx + 1, 0, mid);
      store.markUnsaved();
    }
    return;
  }
  if (handle.startsWith("poly-")) {
    const idx = handle.replace("poly-", "");
    dragState = {
      type: "poly-vertex",
      ann,
      handle: idx,
      startX: e.clientX,
      startY: e.clientY,
      orig: JSON.parse(JSON.stringify(ann)),
    };
    return;
  }
  dragState = {
    type: "resize",
    ann,
    handle,
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}

function onRotateDown(e: MouseEvent, ann: Annotation) {
  store.selectedAnnotationId = ann.id;
  dragState = {
    type: "rotate",
    ann,
    handle: "",
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}

function onMove(e: MouseEvent) {
  if (currentTool.value === "box" && drawStart) {
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
  if (currentTool.value === "rotated_box" && rot.step.value > 0) {
    const p = toImagePoint(e);
    if (p) {
      rbLast = p;
      if (rot.pt1.value && rot.pt2.value) {
        const g = rotatedBoxFromEdgeAndPoint(rot.pt1.value, rot.pt2.value, p);
        if (g) rbPreview.value = { ...g };
      }
    }
    return;
  }
  if (dragState) {
    if (dragState.type === "poly-vertex") {
      const p = toImagePoint(e);
      if (p) {
        seg.moveVertex(dragState.ann, Number(dragState.handle), p);
        store.markUnsaved();
      }
      return;
    }
    if (dragState.type === "rotate") {
      const c = document.querySelector(".annotation-canvas") as HTMLElement | null;
      if (c) {
        const r = c.getBoundingClientRect();
        const centerX = r.left + r.width / 2 - dw.value / 2 + dragState.ann.cx * dw.value;
        const centerY = r.top + r.height / 2 - dh.value / 2 + dragState.ann.cy * dh.value;
        rot.onRotate(
          dragState.ann,
          centerX,
          centerY,
          dragState.startX,
          dragState.startY,
          e.clientX,
          e.clientY
        );
      }
      store.markUnsaved();
      return;
    }
    const dx = (e.clientX - dragState.startX) / dw.value;
    const dy = (e.clientY - dragState.startY) / dh.value;
    if (dragState.type === "resize") {
      if (dragState.ann.type === "RotatedBox") {
        const p = toImagePoint(e);
        if (p) {
          rot.onDragResize(
            dragState.ann,
            dragState.handle,
            p,
            cw.value,
            ch.value,
            ch.value / cw.value
          );
        }
      } else {
        det.onDrag(dragState.ann, dragState.handle, dx, dy);
      }
    } else {
      det.onDragMove(dragState.ann, dx, dy);
    }
    store.markUnsaved();
  }
}

function onUp() {
  if (currentTool.value === "box" && drawStart) {
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
  if (currentTool.value === "rotated_box") {
    rbPreview.value = null;
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
