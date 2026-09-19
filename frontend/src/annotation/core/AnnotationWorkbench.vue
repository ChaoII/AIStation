<template>
  <div class="ann-workbench">
    <el-alert
      v-if="lockedByOther"
      type="warning"
      :closable="false"
      show-icon
      title="该图片已被其他用户锁定，当前为只读模式"
      class="ann-lock-banner"
    />
    <div class="ann-header">
      <div class="ann-title">
        <el-tag :type="taskTagType" size="small">{{ taskTypeLabel }}</el-tag>
        <span class="task-name">{{ store.task?.name }}</span>
      </div>
      <div class="header-right">
        <span class="progress-text">{{ store.annotatedCount }}/{{ store.totalCount }}</span>
        <el-progress
          :percentage="store.progress"
          :stroke-width="6"
          :show-text="false"
          style="width: 100px"
        />
      </div>
    </div>
    <div class="ann-body">
      <aside class="ann-leftbar">
        <div class="tool-list">
          <div
            v-for="t in displayTools"
            :key="t.name"
            class="tool-btn"
            :class="{ active: currentTool === t.name }"
            :title="titleOf(t)"
            @click="setTool(t.name)"
          >
            <el-icon :size="20"><component :is="iconOf(t)" /></el-icon>
            <span class="tool-label">{{ t.label }}</span>
          </div>
          <div class="tool-sep" />
          <div class="tool-btn" title="撤销 (Ctrl+Z)" @click="undo">
            <el-icon :size="20"><RefreshLeft /></el-icon>
            <span class="tool-label">撤销</span>
          </div>
          <div class="tool-btn" title="重做 (Ctrl+Y)" @click="redo">
            <el-icon :size="20"><RefreshRight /></el-icon>
            <span class="tool-label">重做</span>
          </div>
          <div class="tool-btn danger" title="删除选中标注 (Delete)" @click="deleteSelected">
            <el-icon :size="20"><Delete /></el-icon>
            <span class="tool-label">删除</span>
          </div>
        </div>
      </aside>
      <main class="ann-canvas-area">
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
          <rect
            v-if="kpBoxDrafting && kp.boxStart.value && kp.boxEnd.value"
            :x="Math.min(kp.boxStart.value.x, kp.boxEnd.value.x) * cw"
            :y="Math.min(kp.boxStart.value.y, kp.boxEnd.value.y) * ch"
            :width="Math.abs(kp.boxEnd.value.x - kp.boxStart.value.x) * cw"
            :height="Math.abs(kp.boxEnd.value.y - kp.boxStart.value.y) * ch"
            fill="none"
            stroke="#e6a23c"
            stroke-width="1.5"
            stroke-dasharray="4 3"
          />
        </AnnotationCanvas>
      </main>
      <aside class="ann-rightbar">
        <div class="panel-section">
          <div class="section-title-row">图片列表</div>
          <div class="scroll-area img-list">
            <div
              v-for="(img, idx) in store.images"
              :key="img.id"
              class="image-item"
              :class="{ active: idx === store.currentImageIndex }"
              @click="goToImage(idx)"
            >
              <span class="dot" :class="img.status === 'annotated' ? 'dot-done' : 'dot-pending'" />
              <span class="img-name">{{ img.filename }}</span>
              <span class="img-meta">{{ img.updated_by?.name || "--" }}</span>
            </div>
          </div>
        </div>
        <div class="panel-section">
          <div class="section-title-row">类别</div>
          <div class="scroll-area">
            <div class="class-item" v-for="c in config.classes" :key="c.id">
              <span class="dot-color" :style="{ background: c.color }" />
              <span class="flex-1">{{ c.name }}</span>
            </div>
          </div>
        </div>
        <div class="panel-section">
          <div class="section-title-row">标注列表</div>
          <div class="scroll-area">
            <div v-for="a in store.annotations" :key="a.id" class="ann-item" @click="store.selectedAnnotationId = a.id">
              <span class="dot-color" :style="{ background: clsColor(a) }" />
              <span class="flex-1">{{ clsName(a) }}</span>
              <span class="tag-type">{{ a.type }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
    <div class="ann-footer">
      <el-button size="small" :disabled="!store.currentImage" @click="saveAnn">保存</el-button>
      <span class="nav-text">{{ store.currentImageIndex + 1 }}/{{ store.images.length }}</span>
      <el-button size="small" :disabled="!store.currentImage" @click="openHistory">历史</el-button>
      <el-button size="small" @click="prevImg">上一张</el-button>
      <el-button size="small" @click="nextImg">下一张</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { RefreshLeft, RefreshRight, Delete, Select, FullScreen, ZoomIn, Box, Refresh } from "@element-plus/icons-vue";
import AnnotationCanvas from "./AnnotationCanvas.vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";
import { useAnnotationStore } from "./useAnnotationStore";
import {
  useDetectionTool,
} from "../tasks/detection/useDetectionTool";
import { useRotatedTool, rotatedBoxFromEdgeAndPoint } from "../tasks/rotatedBox/useRotatedTool";
import { useSegmentTool } from "../tasks/segmentation/useSegmentTool";
import { useKeypointTool } from "../tasks/keypoint/useKeypointTool";
import { useOcrTool } from "../tasks/ocr/useOcrTool";
import type { Annotation, AnnotationTaskPlugin } from "./types";
import type { WorkbenchApi, WorkbenchConfig } from "./annotationTypes";

const props = defineProps<{
  plugin: AnnotationTaskPlugin;
  api: WorkbenchApi;
  config: WorkbenchConfig;
  taskId: number;
}>();

const store = useAnnotationStore();
const canvasRef = ref<InstanceType<typeof AnnotationCanvas> | null>(null);
const canvas = useAnnotationCanvas();
const currentTool = ref("select");
const imageLoaded = ref(false);
const lockedByOther = ref(false);
const lockedByUser = ref<any>(null);
const imgUrl = ref("");
const preview = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const det = useDetectionTool();
const rot = useRotatedTool();
const seg = useSegmentTool();
const kp = useKeypointTool();
const ocr = useOcrTool();
const rbPreview = ref<{ cx: number; cy: number; width: number; height: number; angle: number } | null>(null);
const kpBoxDrafting = ref(false);
const fontSize = 6;
const tagH = Math.max(8, fontSize + 6);

const baseTools = [
  { name: "select", label: "选择", icon: Select },
  { name: "pan", label: "平移", icon: FullScreen },
  { name: "zoom", label: "缩放", icon: ZoomIn },
];
const displayTools = computed(() => [...baseTools, ...props.plugin.tools]);
const taskTypeLabel = computed(() => props.plugin.label);
const taskTagType = computed(() => (props.plugin.color as any) || "primary");
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const dw = computed(() => canvas.dw.value);
const dh = computed(() => canvas.dh.value);
const toolCursor = computed(() =>
  currentTool.value === "box" || currentTool.value === "rotated_box" ? "crosshair" : "default"
);

const TOOL_ICONS: Record<string, any> = { box: Box, rotated_box: Refresh };

function iconOf(t: any) {
  return t.icon || TOOL_ICONS[t.name] || Box;
}
function titleOf(t: any) {
  return t.title || t.label;
}

let drawStart: { x: number; y: number } | null = null;
let rbLast: { x: number; y: number } | null = null;
let dragState:
  | { type: "move" | "resize" | "rotate" | "poly-vertex" | "kp-vertex"; ann: Annotation; handle: string; startX: number; startY: number; orig: Annotation }
  | null = null;
let loadImgToken = 0;
let lockRenewTimer: number | null = null;

// ==== 历史（undo/redo）====
const MAX_HISTORY = 50;
let historyStack: string[] = [];
let historyIndex = -1;
let lastSavedKey = "";
function annotKey() {
  return JSON.stringify(store.annotations);
}
function pushHistory() {
  const key = annotKey();
  if (historyIndex >= 0 && historyStack[historyIndex] === key) return;
  historyStack = historyStack.slice(0, historyIndex + 1);
  historyStack.push(key);
  if (historyStack.length > MAX_HISTORY) historyStack.shift();
  historyIndex = historyStack.length - 1;
}
function undo() {
  if (lockedByOther.value) return;
  if (historyIndex <= 0) return;
  historyIndex--;
  restoreHistory();
}
function redo() {
  if (lockedByOther.value) return;
  if (historyIndex >= historyStack.length - 1) return;
  historyIndex++;
  restoreHistory();
}
function restoreHistory() {
  const key = historyStack[historyIndex];
  try {
    store.annotations = key ? JSON.parse(key) : [];
  } catch {
    store.annotations = [];
  }
  if (annotKey() !== lastSavedKey && historyIndex < historyStack.length - 1) store.markUnsaved();
}
function deleteSelected() {
  if (lockedByOther.value) return;
  const before = store.annotations.length;
  store.annotations = store.annotations.filter((a) => a.id !== store.selectedAnnotationId);
  if (store.annotations.length !== before) {
    store.markUnsaved();
    pushHistory();
  }
}

function clsName(a: Annotation) {
  return props.config.classes.find((c) => c.id === a.class_id)?.name || "";
}
function clsColor(a: Annotation) {
  return props.config.classes.find((c) => c.id === a.class_id)?.color || "#3b82f6";
}

function toImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const el = document.querySelector(".annotation-canvas") as HTMLElement | null;
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return canvas.containerToImage(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
}

function setTool(t: string) {
  currentTool.value = t;
  resetDrawingState();
}
function resetDrawingState() {
  preview.value = null;
  drawStart = null;
  rbPreview.value = null;
  kpBoxDrafting.value = false;
  dragState = null;
  seg.points.value = [];
  kp.beginBox();
  ocr.reset();
}

function onImgLoad() {
  imageLoaded.value = true;
}

async function loadCurrentImage(imageId: number) {
  const myToken = ++loadImgToken;
  imgUrl.value = "";
  imageLoaded.value = false;
  store.selectedAnnotationId = "";
  store.annotations = [];
  store.unsaved = false;
  try {
    const r = await props.api.getPresignedUrl(imageId, store.taskId);
    if (myToken !== loadImgToken) return;
    imgUrl.value = r?.data?.data?.url || "";
    const ar = await props.api.loadAnnotations(store.taskId, imageId);
    if (myToken !== loadImgToken) return;
    store.annotations = ar?.data?.data || [];
  } catch {
    /* handled by interceptor */
  }
}

async function init() {
  store.taskId = props.taskId;
  store.loading = true;
  try {
    const dr = await props.api.getTaskDetail(props.taskId);
    const t = dr?.data?.data;
    if (!t) return;
    store.task = t;
    const imgs = await props.api.listImages({ task_id: props.taskId, page_no: 1, page_size: 1000 });
    store.images = imgs?.data?.data?.items || imgs?.data?.data || [];
    store.totalCount = store.images.length;
    store.annotatedCount = store.images.filter((i) => i.status === "annotated").length;
    if (store.images.length) {
      store.currentImageIndex = 0;
      await loadCurrentImage(store.images[0].id);
    }
  } catch {
    /* handled */
  } finally {
    store.loading = false;
  }
}

function goToImage(idx: number) {
  if (idx < 0 || idx >= store.images.length) return;
  store.currentImageIndex = idx;
  loadCurrentImage(store.images[idx].id);
}
function prevImg() {
  if (store.currentImageIndex > 0) goToImage(store.currentImageIndex - 1);
}
function nextImg() {
  if (store.currentImageIndex < store.images.length - 1) goToImage(store.currentImageIndex + 1);
}

async function saveAnn() {
  if (!store.currentImageId || !store.taskId) return;
  await props.api.saveAnnotations(store.taskId, store.currentImageId, store.annotations);
  store.unsaved = false;
  lastSavedKey = annotKey();
  historyStack = [lastSavedKey];
  historyIndex = 0;
  const img = store.images[store.currentImageIndex];
  if (img) {
    img.status = store.annotations.length ? "annotated" : "unannotated";
    store.annotatedCount = store.images.filter((i) => i.status === "annotated").length;
  }
}

function openHistory() {
  // 历史抽屉在后续 Task E 接入；先占位提示
}

// ==== 绘制/编辑（同阶段0-5a 逻辑） ====
function onDblClick() {
  if (currentTool.value === "polygon") {
    const created = seg.closePolygon();
    if (created && props.plugin.create(created)) {
      store.annotations.push(created);
      store.markUnsaved();
      pushHistory();
    }
  } else if (currentTool.value === "keypoint") {
    kp.beginBox();
  }
}
function onCanvasDown(e: MouseEvent) {
  if (e.button !== 0 || lockedByOther.value) return;
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
      pushHistory();
    }
  } else if (currentTool.value === "polygon") {
    seg.addPoint(p);
  } else if (currentTool.value === "keypoint") {
    if (kp.boxMode.value) {
      kp.setBoxStart(p);
      kpBoxDrafting.value = true;
    } else {
      kp.addPoint(p);
    }
  } else if (currentTool.value === "ocr") {
    const created = ocr.onPoint(p);
    if (created) {
      const text = window.prompt("输入 OCR 文本", "") || "";
      created.text = text;
      if (props.plugin.create(created)) {
        store.annotations.push(created);
        store.markUnsaved();
        pushHistory();
      }
    }
  }
}
function onAnnDown(e: MouseEvent, ann: Annotation) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = ann.id;
  dragState = { type: "move", ann, handle: "", startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
}
function onHandleDown(e: MouseEvent, ann: Annotation, handle: string) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = ann.id;
  if (handle.startsWith("kp-")) {
    dragState = { type: "kp-vertex", ann, handle: handle.replace("kp-", ""), startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    return;
  }
  if (handle.startsWith("ocr-")) {
    dragState = { type: "poly-vertex", ann, handle: handle.replace("ocr-", ""), startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    return;
  }
  if (handle.startsWith("poly-ins-")) {
    const idx = parseInt(handle.replace("poly-ins-", ""), 10);
    if (!isNaN(idx) && ann.points?.length) {
      const a = ann.points[idx], b = ann.points[(idx + 1) % ann.points.length];
      ann.points.splice(idx + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
      store.markUnsaved();
    }
    return;
  }
  if (handle.startsWith("poly-")) {
    dragState = { type: "poly-vertex", ann, handle: handle.replace("poly-", ""), startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    return;
  }
  dragState = { type: "resize", ann, handle, startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
}
function onRotateDown(e: MouseEvent, ann: Annotation) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = ann.id;
  dragState = { type: "rotate", ann, handle: "", startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
}
function onMove(e: MouseEvent) {
  if (lockedByOther.value) return;
  if (currentTool.value === "box" && drawStart) {
    const p = toImagePoint(e);
    if (!p) return;
    preview.value = { x: Math.min(drawStart.x, p.x), y: Math.min(drawStart.y, p.y), w: Math.abs(p.x - drawStart.x), h: Math.abs(p.y - drawStart.y) };
    return;
  }
  if (currentTool.value === "rotated_box") {
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
  if (currentTool.value === "keypoint" && kpBoxDrafting.value) {
    const p = toImagePoint(e);
    if (p) kp.updateBox(p);
    return;
  }
  if (dragState) {
    if (dragState.type === "kp-vertex") {
      const p = toImagePoint(e);
      if (p) { kp.moveKeypoint(dragState.ann, Number(dragState.handle), p); store.markUnsaved(); }
      return;
    }
    if (dragState.type === "poly-vertex") {
      const p = toImagePoint(e);
      if (p) { seg.moveVertex(dragState.ann, Number(dragState.handle), p); store.markUnsaved(); }
      return;
    }
    if (dragState.type === "rotate") {
      const c = document.querySelector(".annotation-canvas") as HTMLElement | null;
      if (c) {
        const r = c.getBoundingClientRect();
        const centerX = r.left + r.width / 2 - dw.value / 2 + dragState.ann.cx * dw.value;
        const centerY = r.top + r.height / 2 - dh.value / 2 + dragState.ann.cy * dh.value;
        rot.onRotate(dragState.ann, centerX, centerY, dragState.startX, dragState.startY, e.clientX, e.clientY);
      }
      store.markUnsaved();
      return;
    }
    const dx = (e.clientX - dragState.startX) / dw.value;
    const dy = (e.clientY - dragState.startY) / dh.value;
    if (dragState.type === "resize") {
      if (dragState.ann.type === "RotatedBox") {
        const p = toImagePoint(e);
        if (p) rot.onDragResize(dragState.ann, dragState.handle, p, cw.value, ch.value, ch.value / cw.value);
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
      pushHistory();
    }
    return;
  }
  if (currentTool.value === "rotated_box") {
    rbPreview.value = null;
    return;
  }
  if (currentTool.value === "keypoint" && kpBoxDrafting.value) {
    kpBoxDrafting.value = false;
    const created = kp.build();
    if (created && props.plugin.create(created)) {
      store.annotations.push(created);
      store.markUnsaved();
      pushHistory();
    }
    return;
  }
  if (dragState) pushHistory();
  dragState = null;
}

// ==== 历史（undo/redo）====
onMounted(() => {
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  window.addEventListener("beforeunload", onBeforeUnload);
  init();
});
onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMove);
  window.removeEventListener("mouseup", onUp);
  window.removeEventListener("beforeunload", onBeforeUnload);
  if (lockRenewTimer) clearInterval(lockRenewTimer);
});
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (store.unsaved) {
    e.preventDefault();
    e.returnValue = "";
  }
}
</script>

<style scoped>
.ann-workbench {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #fff;
}
.ann-lock-banner {
  margin: 8px;
}
.ann-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.ann-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ann-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.ann-leftbar {
  width: 56px;
  border-right: 1px solid var(--el-border-color-light);
  padding: 8px 0;
}
.tool-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 48px;
  padding: 6px 0;
  cursor: pointer;
  color: #606266;
}
.tool-btn.active {
  color: var(--el-color-primary);
}
.tool-btn.danger:hover {
  color: var(--el-color-danger);
}
.tool-label {
  font-size: 11px;
}
.tool-sep {
  height: 1px;
  width: 32px;
  background: var(--el-border-color-light);
  margin: 6px 0;
}
.ann-canvas-area {
  flex: 1;
  min-width: 0;
  position: relative;
}
.ann-rightbar {
  width: 240px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}
.panel-section {
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 8px;
}
.section-title-row {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
}
.scroll-area {
  max-height: 240px;
  overflow: auto;
}
.img-list {
  max-height: 320px;
}
.image-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  cursor: pointer;
  font-size: 12px;
}
.image-item.active {
  background: var(--el-color-primary-light-9);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-done {
  background: var(--el-color-success);
}
.dot-pending {
  background: var(--el-color-info);
}
.img-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-meta {
  color: #c0c4cc;
  font-size: 11px;
}
.class-item,
.ann-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  font-size: 12px;
  cursor: pointer;
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.flex-1 {
  flex: 1;
}
.tag-type {
  color: #c0c4cc;
  font-size: 11px;
}
.ann-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-light);
}
.nav-text {
  color: #909399;
  font-size: 13px;
}
</style>
