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
        <span v-if="props.collab" class="collab-online">在线 {{ props.collab.onlineUsers.value.length }}</span>
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
        <div
          v-if="crossVisible"
          class="crosshair-x"
          :style="{ left: crosshair.x + 'px', top: crosshair.y + 'px' }"
        />
        <div
          v-if="crossVisible"
          class="crosshair-y"
          :style="{ left: crosshair.x + 'px', top: crosshair.y + 'px' }"
        />
        <AnnotationCanvas
          ref="canvasRef"
          :img-url="imgUrl"
          :image-loaded="imageLoaded"
          :cursor="toolCursor"
          :canvas="canvas"
          @img-load="onImgLoad"
          @mousedown="onCanvasDown"
          @dblclick="onDblClick"
          @wheel="onWheel"
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
            @contextmenu.prevent="onRootContextmenu"
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
          <div class="section-title-row">
            <span>类别</span>
            <el-button link type="primary" size="small" @click="showClassModal = true">+ 添加</el-button>
          </div>
          <div class="scroll-area">
            <div class="class-item" v-for="c in taskClasses" :key="c.id">
              <span class="dot-color" :style="{ background: c.color }" />
              <span class="flex-1">{{ c.name }}</span>
              <el-popconfirm title="确定删除该类别？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeClass(c.id)">
                <template #reference>
                  <el-button text size="small">×</el-button>
                </template>
              </el-popconfirm>
            </div>
            <div v-if="taskClasses.length === 0" class="empty-hint">请添加类别</div>
          </div>
        </div>
        <div
          v-if="plugin.name === 'classification'"
          class="panel-section"
        >
          <div class="section-title-row">
            分类（{{ config.classificationMode === "multi" ? "多标签" : "单标签" }}）
          </div>
          <div class="scroll-area">
            <div
              v-for="c in taskClasses"
              :key="c.id"
              class="class-item"
              :class="{ active: isClsSelected(c.id) }"
              @click="toggleClassification(c.id)"
            >
              <span class="dot-color" :style="{ background: c.color }" />
              <span class="flex-1">{{ c.name }}</span>
              <el-checkbox :model-value="isClsSelected(c.id)" @click.stop />
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

    <div
      v-if="annMenu.visible"
      class="ctx-backdrop"
      @click="closeMenu"
      @contextmenu.prevent="closeMenu"
    />
    <div
      v-if="annMenu.visible"
      class="ctx-menu"
      :style="{ left: annMenu.x + 'px', top: annMenu.y + 'px' }"
    >
      <div class="ctx-item" @click.stop="menuEdit">编辑标注</div>
      <div class="ctx-item ctx-danger" @click.stop="menuDelete">删除标注</div>
    </div>

    <el-dialog v-model="editAnnVisible" title="编辑标注" width="420px" append-to-body>
      <el-form label-width="72px">
        <el-form-item label="类别">
          <el-select v-model="editForm.class_id" size="small" style="width: 100%" @change="editClassChange">
            <el-option v-for="c in taskClasses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editForm.ann?.type === 'Ocr'" label="OCR文本">
          <el-input v-model="editForm.text" size="small" placeholder="编辑OCR文本" @change="editTextChange" />
        </el-form-item>
        <el-form-item v-if="editForm.ann?.type === 'Keypoint'" label="关键点">
          <div style="width:100%">
            <div v-for="(kp, i) in editForm.keypoints" :key="i" style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
              <el-input v-model="kp.name" size="small" placeholder="名称" style="flex:1" @change="editKpChange" />
              <el-select v-model="kp.visibility" size="small" style="width:110px" @change="editKpChange">
                <el-option v-for="v in KP_VISIBILITY" :key="v" :label="v" :value="v" />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editAnnVisible = false">关闭</el-button>
        <el-button type="danger" @click="editDelete">删除该标注</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showClassModal" title="添加类别" width="380px" append-to-body>
      <el-form :model="clsForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="clsForm.name" placeholder="类别名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="clsForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showClassModal = false">取消</el-button>
        <el-button type="primary" @click="addClass">添加</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="ocrInputVisible" title="输入 OCR 文本" width="380px" append-to-body>
      <el-input v-model="ocrInput" placeholder="OCR 文本" @keydown.enter="confirmOcr" />
      <template #footer>
        <el-button @click="ocrInputVisible = false; pendingOcr = null">取消</el-button>
        <el-button type="primary" @click="confirmOcr">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
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
import type { WorkbenchApi, WorkbenchConfig, CollabAdapter } from "./annotationTypes";

const props = defineProps<{
  plugins: AnnotationTaskPlugin[];
  api: WorkbenchApi;
  config: WorkbenchConfig;
  taskId: number;
  collab?: CollabAdapter;
}>();

const store = useAnnotationStore();
const emit = defineEmits<{ (e: "open-history"): void }>();
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
const selectedClassId = ref<number | null>(null);
watch(
  () => [...taskClasses.value],
  (arr) => {
    if (!arr.length) selectedClassId.value = null;
    else if (!arr.some((c) => c.id === selectedClassId.value)) selectedClassId.value = arr[0].id;
  },
  { immediate: true }
);
const ocr = useOcrTool();
const rbPreview = ref<{ cx: number; cy: number; width: number; height: number; angle: number } | null>(null);
const kpBoxDrafting = ref(false);
const showCrosshair = ref(false);
const crosshair = reactive({ x: 0, y: 0 });
const pendingKpVisibility = ref("Visible");
const fontSize = 6;
const tagH = Math.max(8, fontSize + 6);

const baseTools = [
  { name: "select", label: "选择", icon: Select },
  { name: "pan", label: "平移", icon: FullScreen },
  { name: "zoom", label: "缩放", icon: ZoomIn },
];
const plugin = computed(
  () => props.plugins.find((p) => p.name === (store.task?.task_type || "")) ?? props.plugins[0]
);
const displayTools = computed(() => [...baseTools, ...plugin.value.tools]);
const taskTypeLabel = computed(() => plugin.value.label);
const taskTagType = computed(() => (plugin.value.color as any) || "primary");
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const dw = computed(() => canvas.dw.value);
const dh = computed(() => canvas.dh.value);
const toolCursor = computed(() =>
  currentTool.value === "box" || currentTool.value === "rotated_box" ? "crosshair" : "default"
);
const crossVisible = computed(() =>
  ["box", "rotated_box", "polygon", "keypoint", "ocr"].includes(currentTool.value)
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
let panState: { startX: number; startY: number; px: number; py: number } | null = null;
let dragState:
  | { type: "move" | "resize" | "rotate" | "poly-vertex" | "kp-vertex"; ann: Annotation; handle: string; startX: number; startY: number; orig: Annotation }
  | null = null;
let loadImgToken = 0;
let lockRenewTimer: number | null = null;
let lockedImageId: number | null = null;

function clearLockRenewal() {
  if (lockRenewTimer) {
    clearInterval(lockRenewTimer);
    lockRenewTimer = null;
  }
}
function unlockCurrent() {
  clearLockRenewal();
  if (lockedImageId) {
    props.api.unlockImage(lockedImageId, store.taskId).catch(() => {});
    lockedImageId = null;
  }
}

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
  const target = store.annotations.find((a) => a.id === store.selectedAnnotationId);
  if (!target) return;
  ElMessageBox.confirm(`将删除 1 个${target.type}标注，且不可恢复。`, "删除标注", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== store.selectedAnnotationId);
      if (store.annotations.length !== before) {
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}

// 复制 / 粘贴标注
let annClipboard: any = null;
function copySelected() {
  const ann = store.annotations.find((a) => a.id === store.selectedAnnotationId);
  if (!ann) {
    ElMessage.info("请先选中一个标注");
    return;
  }
  annClipboard = JSON.parse(JSON.stringify(ann));
  ElMessage.success("已复制标注");
}
function pasteCopied() {
  if (lockedByOther.value) return;
  if (!annClipboard) {
    ElMessage.info("剪贴板为空，先 Ctrl+C 复制标注");
    return;
  }
  const copy = JSON.parse(JSON.stringify(annClipboard));
  copy.id = crypto.randomUUID();
  if (copy.x1 !== undefined) {
    copy.x1 += 0.01;
    copy.x2 += 0.01;
    copy.y1 += 0.01;
    copy.y2 += 0.01;
  } else if (copy.cx !== undefined) {
    copy.cx += 0.01;
    copy.cy += 0.01;
  } else if (copy.points) {
    copy.points = copy.points.map((p: any) => ({ x: p.x + 0.01, y: p.y + 0.01 }));
  }
  store.annotations.push(copy);
  store.selectedAnnotationId = copy.id;
  store.markUnsaved();
  pushHistory();
}

const taskClasses = ref<any[]>([...(props.config.classes || [])]);
watch(
  () => props.config.classes,
  (val) => {
    taskClasses.value = [...(val || [])];
  },
  { deep: true }
);
const showClassModal = ref(false);
const clsForm = reactive({ name: "", color: "#409eff" });
const ocrInputVisible = ref(false);
const ocrInput = ref("");
let pendingOcr: Annotation | null = null;

async function addClass() {
  if (!clsForm.name.trim()) return;
  const id =
    taskClasses.value.length > 0
      ? Math.max(...taskClasses.value.map((c) => c.id)) + 1
      : 0;
  taskClasses.value.push({ id, name: clsForm.name.trim(), color: clsForm.color });
  clsForm.name = "";
  showClassModal.value = false;
  await saveClasses();
}
async function removeClass(id: number) {
  taskClasses.value = taskClasses.value.filter((c) => c.id !== id);
  store.annotations.forEach((a: any) => {
    if (a.class_id === id) a.class_id = -1;
    if (Array.isArray(a.class_ids)) a.class_ids = a.class_ids.filter((cid: number) => cid !== id);
  });
  await saveClasses();
}
async function saveClasses() {
  if (!store.taskId) return;
  try {
    await props.api.updateTask(store.taskId, { classes: taskClasses.value });
  } catch {
    /* ignore */
  }
}

function clsName(a: Annotation) {
  const c = taskClasses.value.find((c) => c.id === a.class_id);
  if (c) return c.name;
  // 多标签聚合并集显示
  if (Array.isArray(a.class_ids) && a.class_ids.length) {
    return a.class_ids
      .map((id) => taskClasses.value.find((c) => c.id === id)?.name)
      .filter(Boolean)
      .join(" / ");
  }
  return "";
}
function clsColor(a: Annotation) {
  return taskClasses.value.find((c) => c.id === a.class_id)?.color || "#3b82f6";
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

function onWheel(e: WheelEvent) {
  if (!cw.value || !ch.value) return;
  const el = document.querySelector(".annotation-canvas") as HTMLElement | null;
  if (!el) return;
  const r = el.getBoundingClientRect();
  const cx = e.clientX - r.left;
  const cy = e.clientY - r.top;
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const newZoom = Math.min(3, Math.max(0.1, canvas.zoom.value * factor));
  const scale = newZoom / canvas.zoom.value;
  // 保持光标下的图像点不动
  const off = canvas.imageOffset(r.width, r.height);
  const ix = (cx - off.left) / dw.value;
  const iy = (cy - off.top) / dh.value;
  canvas.zoom.value = newZoom;
  canvas.dw.value = cw.value * newZoom;
  canvas.dh.value = ch.value * newZoom;
  canvas.setPan(
    r.width / 2 - ix * dw.value - dw.value / 2,
    r.height / 2 - iy * dh.value - dh.value / 2
  );
}

function onRootContextmenu(e: MouseEvent) {
  const el = (e.target as Element).closest?.("[data-ann-id]");
  if (!el) return;
  const id = el.getAttribute("data-ann-id");
  if (!id) return;
  const ann = store.annotations.find((a) => a.id === id);
  if (!ann) return;
  openContextMenu(e, ann);
}

async function loadCurrentImage(imageId: number) {
  const myToken = ++loadImgToken;
  // 切图：先释放上一张锁
  if (lockedImageId && lockedImageId !== imageId) unlockCurrent();
  imgUrl.value = "";
  imageLoaded.value = false;
  store.selectedAnnotationId = "";
  store.annotations = [];
  store.unsaved = false;
  lockedByOther.value = false;
  lockedByUser.value = null;
  try {
    const r = await props.api.getPresignedUrl(imageId, store.taskId);
    if (myToken !== loadImgToken) return;
    imgUrl.value = r?.data?.data?.url || "";
    const ar = await props.api.loadAnnotations(store.taskId, imageId);
    if (myToken !== loadImgToken) return;
    store.annotations = ar?.data?.data || [];
    lockedImageId = imageId;
    props.collab?.focus(imageId);
    // 锁定当前图 + 定期续期（后端 5 分钟过期）
    props.api
      .lockImage(imageId, store.taskId)
      .then((lr: any) => {
        if (myToken !== loadImgToken) return;
        const d = lr?.data?.data;
        if (d?.locked) {
          lockedByOther.value = true;
          lockedByUser.value = d.locked_by ?? null;
        } else {
          lockedByOther.value = false;
          lockedByUser.value = null;
        }
        clearLockRenewal();
        lockRenewTimer = window.setInterval(() => {
          props.api.lockImage(imageId, store.taskId).catch(() => {});
        }, 180000);
      })
      .catch(() => {});
  } catch {
    /* handled by interceptor */
  }
}

const IMAGE_PAGE_SIZE = 200;
const imageTotal = ref(0);
const imagePrefetching = ref(false);
let imageLoadedPages = 0;

async function loadImagePage(p: number, silent = false): Promise<any[]> {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return [];
  const r = await props.api.getImages(datasetId, store.taskId, p, IMAGE_PAGE_SIZE, { silent });
  const d = r?.data?.data;
  imageTotal.value = d?.total ?? imageTotal.value;
  return d?.items || [];
}

async function prefetchRemainingImages() {
  if (imagePrefetching.value) return;
  imagePrefetching.value = true;
  try {
    const totalPages = Math.ceil(imageTotal.value / IMAGE_PAGE_SIZE);
    for (let p = imageLoadedPages + 1; p <= totalPages; p++) {
      try {
        const items = await loadImagePage(p, true);
        if (items.length) store.images.push(...items);
        imageLoadedPages = p;
      } catch {
        return;
      }
      await new Promise((res) => setTimeout(res, 800));
    }
  } finally {
    imagePrefetching.value = false;
  }
}

async function ensureMoreImages(idx: number) {
  const datasetId = store.task?.dataset_id;
  if (!datasetId || imagePrefetching.value) return;
  const totalPages = Math.ceil(imageTotal.value / IMAGE_PAGE_SIZE);
  if (imageLoadedPages >= totalPages) return;
  if (idx < store.images.length - 10) return;
  try {
    const items = await loadImagePage(imageLoadedPages + 1);
    if (items.length) store.images.push(...items);
    imageLoadedPages += 1;
  } catch {
    /* ignore */
  }
}

async function fetchTaskProgress() {
  try {
    await props.api.getTaskProgress(store.taskId);
  } catch {
    /* ignore */
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
    props.collab?.connect(store.taskId);
    imageTotal.value = 0;
    imageLoadedPages = 0;
    const imgs = await loadImagePage(1);
    store.images = imgs;
    imageLoadedPages = 1;
    store.totalCount = imageTotal.value;
    store.annotatedCount = store.images.filter((i) => i.status === "annotated").length;
    if (store.images.length) {
      store.currentImageIndex = 0;
      await loadCurrentImage(store.images[0].id);
    }
    fetchTaskProgress();
    prefetchRemainingImages();
  } catch {
    /* handled */
  } finally {
    store.loading = false;
  }
}

function goToImage(idx: number) {
  if (idx < 0 || idx >= store.images.length) return;
  store.currentImageIndex = idx;
  ensureMoreImages(idx);
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
  if (lockedByOther.value) {
    return;
  }
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
  // 历史抽屉由外层路由包装层承载（保持组件库解耦），此处仅触发事件
  emit("open-history");
}

// ==== 绘制/编辑（同阶段0-5a 逻辑） ====
function onDblClick(e: MouseEvent) {
  // 双击已有标注 → 打开编辑弹窗
  const hit = (e.target as Element)?.closest?.("[data-ann-id]");
  if (hit) {
    const id = hit.getAttribute("data-ann-id");
    const ann = store.annotations.find((a) => a.id === id);
    if (ann) {
      openEditDialog(ann);
      return;
    }
  }
  if (currentTool.value === "polygon") {
    const created = seg.closePolygon();
    if (created && plugin.value.create(created)) {
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
  if (currentTool.value === "pan") {
    panState = { startX: e.clientX, startY: e.clientY, px: canvas.panX.value, py: canvas.panY.value };
    return;
  }
  if (currentTool.value === "box") {
    det.onStart(p);
    drawStart = p;
    preview.value = { x: p.x, y: p.y, w: 0, h: 0 };
  } else if (currentTool.value === "rotated_box") {
    rbLast = p;
    const created = rot.onStep(p);
    if (created && plugin.value.create(created)) {
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
      const kpNames = taskClasses.value.find((c) => c.id === selectedClassId.value)?.keypoint_names || [];
      kp.setNames(kpNames);
      kp.addPoint(p, pendingKpVisibility.value);
    }
  } else if (currentTool.value === "ocr") {
    const created = ocr.onPoint(p);
    if (created) {
      pendingOcr = created;
      ocrInput.value = "";
      ocrInputVisible.value = true;
    }
  }
}
function confirmOcr() {
  if (pendingOcr) {
    pendingOcr.text = ocrInput.value;
    if (plugin.value.create(pendingOcr)) {
      store.annotations.push(pendingOcr);
      store.markUnsaved();
      pushHistory();
    }
  }
  pendingOcr = null;
  ocrInputVisible.value = false;
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
    const idx = handle.replace("kp-", "");
    if (e.altKey) {
      kp.removeKeypoint(ann, Number(idx));
      store.markUnsaved();
      pushHistory();
      return;
    }
    dragState = { type: "kp-vertex", ann, handle: idx, startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    return;
  }
  if (handle.startsWith("ocr-")) {
    const idx = Number(handle.replace("ocr-", ""));
    if (e.altKey) {
      if (ann.points?.length > 4) {
        ann.points.splice(idx, 1);
        store.markUnsaved();
        pushHistory();
      }
      return;
    }
    dragState = { type: "poly-vertex", ann, handle: String(idx), startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
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
    const idx = Number(handle.replace("poly-", ""));
    if (e.altKey) {
      if (ann.points?.length > 3) {
        ann.points.splice(idx, 1);
        store.markUnsaved();
        pushHistory();
      }
      return;
    }
    dragState = { type: "poly-vertex", ann, handle: String(idx), startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
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
  const cc = document.querySelector(".annotation-canvas") as HTMLElement | null;
  if (cc) {
    const r = cc.getBoundingClientRect();
    crosshair.x = e.clientX - r.left;
    crosshair.y = e.clientY - r.top;
  }
  if (panState) {
    canvas.setPan(panState.px + (e.clientX - panState.startX), panState.py + (e.clientY - panState.startY));
    return;
  }
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
  if (panState) {
    panState = null;
    return;
  }
  if (currentTool.value === "box" && drawStart) {
    const p = preview.value;
    const created = det.onMoveEnd(p ? { x: p.x + p.w, y: p.y + p.h } : ({ x: 0, y: 0 } as any));
    preview.value = null;
    drawStart = null;
    if (created && plugin.value.create(created)) {
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
    if (created && plugin.value.create(created)) {
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
const editAnnVisible = ref(false);
const editForm = reactive({ ann: null as any, class_id: 0, text: "", keypoints: [] as any[] });
const KP_VISIBILITY = ["Visible", "Occluded", "Hidden"];
const annMenu = reactive({ visible: false, ann: null as any, x: 0, y: 0 });

function openContextMenu(e: MouseEvent, ann: Annotation) {
  annMenu.ann = ann;
  annMenu.x = e.clientX;
  annMenu.y = e.clientY;
  annMenu.visible = true;
}
function closeMenu() {
  annMenu.visible = false;
}
function openEditDialog(ann: any) {
  if (!ann) return;
  editForm.ann = ann;
  editForm.class_id = ann.class_id;
  editForm.text = ann.text || "";
  editForm.keypoints = ann.type === "Keypoint" ? JSON.parse(JSON.stringify(ann.keypoints || [])) : [];
  editAnnVisible.value = true;
}
function menuEdit() {
  const ann = annMenu.ann;
  closeMenu();
  openEditDialog(ann);
}
function menuDelete() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  deleteSelected();
}
function editClassChange() {
  if (editForm.ann) editForm.ann.class_id = editForm.class_id;
}
function editTextChange() {
  if (editForm.ann) editForm.ann.text = editForm.text;
}
function editKpChange() {
  if (editForm.ann?.type === "Keypoint") {
    editForm.ann.keypoints = JSON.parse(JSON.stringify(editForm.keypoints));
  }
}
function editDelete() {
  if (editForm.ann) store.selectedAnnotationId = editForm.ann.id;
  editAnnVisible.value = false;
  deleteSelected();
}
function onKey(e: KeyboardEvent) {
  if (e.ctrlKey && e.key.toLowerCase() === "s") { e.preventDefault(); saveAnn(); }
  else if (e.ctrlKey && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); }
  else if (e.ctrlKey && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
  else if (e.ctrlKey && e.key.toLowerCase() === "c") { e.preventDefault(); copySelected(); }
  else if (e.ctrlKey && e.key.toLowerCase() === "v") { e.preventDefault(); pasteCopied(); }
  else if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); }
  else if (["1", "s"].includes(e.key)) setTool("select");
  else if (["2", "b"].includes(e.key)) setTool("box");
  else if (["3", "r"].includes(e.key)) setTool("rotated_box");
  else if (["4", "p"].includes(e.key)) setTool("polygon");
  else if (["5", "k"].includes(e.key)) setTool("keypoint");
  else if (["6", "o"].includes(e.key)) setTool("ocr");
  else if (["7", "c"].includes(e.key)) setTool("classification");
  else if (["0"].includes(e.key)) { if (currentTool.value === "keypoint") pendingKpVisibility.value = "Hidden"; }
  else if (["1"].includes(e.key)) { if (currentTool.value === "keypoint") pendingKpVisibility.value = "Occluded"; }
  else if (["2"].includes(e.key)) { if (currentTool.value === "keypoint") pendingKpVisibility.value = "Visible"; }
}
function toggleClassification(clsId: number) {
  if (lockedByOther.value) return;
  if (props.config.classificationMode === "single") {
    const existing = store.annotations.find((a) => a.type === "Classification");
    if (existing && existing.class_id === clsId) {
      store.annotations = store.annotations.filter((a) => a.id !== existing.id);
    } else {
      store.annotations = store.annotations.filter((a) => a.type !== "Classification");
      store.annotations.push({ id: crypto.randomUUID(), type: "Classification", class_id: clsId });
    }
  } else {
    const existing = store.annotations.find((a) => a.type === "Classification");
    if (existing) {
      const ids = (existing.class_ids || []) as number[];
      if (ids.includes(clsId)) {
        existing.class_ids = ids.filter((id) => id !== clsId);
        if (existing.class_ids.length === 0) {
          store.annotations = store.annotations.filter((a) => a.id !== existing.id);
        }
      } else {
        existing.class_ids = [...ids, clsId];
      }
    } else {
      store.annotations.push({ id: crypto.randomUUID(), type: "Classification", class_id: clsId, class_ids: [clsId] });
    }
  }
  store.markUnsaved();
  pushHistory();
}
function isClsSelected(clsId: number) {
  const a = store.annotations.find((x) => x.type === "Classification");
  if (!a) return false;
  if (Array.isArray(a.class_ids)) return a.class_ids.includes(clsId);
  return a.class_id === clsId;
}

onMounted(() => {
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  window.addEventListener("beforeunload", onBeforeUnload);
  document.addEventListener("keydown", onKey);
  init();
});
onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMove);
  window.removeEventListener("mouseup", onUp);
  window.removeEventListener("beforeunload", onBeforeUnload);
  document.removeEventListener("keydown", onKey);
  unlockCurrent();
  props.collab?.close();
});
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (store.unsaved) {
    e.preventDefault();
    e.returnValue = "";
  }
}

defineExpose({
  refreshCurrent() {
    if (store.currentImageId) loadCurrentImage(store.currentImageId);
  },
  getCurrentImageId() {
    return store.currentImageId;
  },
});
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
.collab-online {
  color: var(--el-color-success);
  font-size: 12px;
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
.class-item.active {
  background: var(--el-color-primary-light-9);
}
.ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
}
.ctx-menu {
  position: fixed;
  z-index: 1001;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  padding: 4px 0;
  min-width: 120px;
}
.ctx-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover {
  background: var(--el-fill-color-light);
}
.ctx-danger {
  color: var(--el-color-danger);
}
.crosshair-x,
.crosshair-y {
  position: absolute;
  z-index: 5;
  pointer-events: none;
}
.crosshair-x {
  height: 1px;
  width: 100%;
  border-top: 1px dashed #909399;
}
.crosshair-y {
  width: 1px;
  height: 100%;
  border-left: 1px dashed #909399;
}
.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 4px;
}
</style>
