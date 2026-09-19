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
      <AnnotationToolbar
        :tools="displayTools"
        :current-tool="currentTool"
        @select="setTool"
        @undo="undo"
        @redo="redo"
        @delete="deleteSelected"
      />
      <main class="ann-canvas-area">
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
            :stroke="strokeW"
            :sel-stroke="selStrokeW"
            :pointer-none="crossVisible"
            @ann-down="onAnnDown"
            @handle-down="onHandleDown"
            @rotate-down="onRotateDown"
            @contextmenu.prevent="onRootContextmenu"
          />
          <line
            v-if="crossVisible"
            :x1="crosshair.x * cw"
            :y1="0"
            :x2="crosshair.x * cw"
            :y2="ch"
            stroke="#909399"
            stroke-width="1"
            stroke-dasharray="3 3"
            class="cross-svg"
          />
          <line
            v-if="crossVisible"
            :x1="0"
            :y1="crosshair.y * ch"
            :x2="cw"
            :y2="crosshair.y * ch"
            stroke="#909399"
            stroke-width="1"
            stroke-dasharray="3 3"
            class="cross-svg"
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
        <polyline
          v-if="currentTool === 'polygon' && seg.points.value.length"
          :points="polyPts"
          fill="none"
          stroke="#3b82f6"
          stroke-width="1.5"
          stroke-dasharray="4 3"
        />
        <circle
          v-for="(pt, i) in (currentTool === 'polygon' ? seg.points.value : [])"
          :key="'pp' + i"
          :cx="pt.x * cw"
          :cy="pt.y * ch"
          r="3"
          fill="#fff"
          stroke="#3b82f6"
          stroke-width="1"
        />
        <circle
          v-for="(pt, i) in (currentTool === 'keypoint' ? kp.pending.value : [])"
          :key="'kp' + i"
          :cx="pt.x * cw"
          :cy="pt.y * ch"
          r="4"
          fill="none"
          stroke="#e6a23c"
          stroke-width="1.5"
        />
        <polyline
          v-if="currentTool === 'ocr' && ocr.mode.value === 'quad' && ocr.quadPoints.value.length"
          :points="ocrQuadPts"
          fill="none"
          stroke="#e6a23c"
          stroke-width="1.5"
          stroke-dasharray="4 3"
        />
        <circle
          v-for="(pt, i) in (currentTool === 'ocr' && ocr.mode.value === 'quad' ? ocr.quadPoints.value : [])"
          :key="'oq' + i"
          :cx="pt.x * cw"
          :cy="pt.y * ch"
          r="3"
          fill="#fff"
          stroke="#e6a23c"
          stroke-width="1"
        />
        <!-- 旋转框三步绘制引导 -->
        <template v-if="currentTool === 'rotated_box' && rot.step.value > 0">
          <line
            v-if="rot.pt1.value && rbLast"
            :x1="rot.pt1.value.x * cw"
            :y1="rot.pt1.value.y * ch"
            :x2="rbLast.x * cw"
            :y2="rbLast.y * ch"
            stroke="#f56c6c"
            stroke-width="1.5"
            stroke-dasharray="4 3"
          />
          <line
            v-if="rot.pt1.value && rot.pt2.value && rbLast"
            :x1="rot.pt2.value.x * cw"
            :y1="rot.pt2.value.y * ch"
            :x2="rbLast.x * cw"
            :y2="rbLast.y * ch"
            stroke="#f56c6c"
            stroke-width="1"
            stroke-dasharray="2 2"
          />
          <circle v-if="rot.pt1.value" :cx="rot.pt1.value.x * cw" :cy="rot.pt1.value.y * ch" r="4" fill="#fff" stroke="#f56c6c" stroke-width="1.5" />
          <circle v-if="rot.pt2.value" :cx="rot.pt2.value.x * cw" :cy="rot.pt2.value.y * ch" r="4" fill="#fff" stroke="#f56c6c" stroke-width="1.5" />
        </template>
        <!-- 多边形首点提示 -->
        <circle
          v-if="currentTool === 'polygon' && seg.points.value.length"
          :cx="seg.points.value[0].x * cw"
          :cy="seg.points.value[0].y * ch"
          r="4"
          fill="none"
          stroke="#3b82f6"
          stroke-width="1.5"
        />
        </AnnotationCanvas>
      </main>
      <AnnotationRightPanel
        :ann-settings="annSettings"
        :image-filter="imageFilter"
        :filtered-images="filteredImages"
        :images="store.images"
        :current-image-id="store.currentImage?.id ?? null"
        :task-classes="taskClasses"
        :selected-class-id="selectedClassId"
        :plugin-name="plugin.name"
        :classification-mode="config.classificationMode"
        :annotations="store.annotations"
        :selected-annotation-id="store.selectedAnnotationId"
        :cls-color="clsColor"
        :cls-name="clsName"
        :cls-count="clsCount"
        :is-cls-selected="isClsSelected"
        @update-image-filter="imageFilter = $event"
        @go-image="goToImage"
        @add-class="openAddClass"
        @edit-class="openEditClass"
        @select-class="selectedClassId = $event"
        @remove-class="removeClass"
        @change-class-color="changeClassColor"
        @toggle-classification="toggleClassification"
        @select-annotation="store.selectedAnnotationId = $event"
        @edit-annotation="openEditDialog"
        @contextmenu-annotation="openContextMenu"
        @delete-annotation="deleteById"
      />
    </div>
    <AnnotationHistoryBar
      :has-current-image="!!store.currentImage"
      :current-index="store.currentImageIndex"
      :total="store.images.length"
      :unsaved="store.unsaved"
      :cursor-x="cursorPos.x"
      :cursor-y="cursorPos.y"
      :zoom="canvas.zoom.value"
      :cw="canvas.cw.value"
      :hint="hintText"
      :can-prev="store.currentImageIndex > 0"
      :can-next="store.currentImageIndex < store.images.length - 1"
      :locked="lockedByOther"
      @save="saveAnn"
      @prev="prevImg"
      @next="nextImg"
      @history="openHistory"
      @help="showHelpModal = true"
    />

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
      <div class="ctx-item" @click.stop="menuCopy">复制标注</div>
      <div class="ctx-item" @click.stop="menuLayerTop">置顶</div>
      <div class="ctx-item" @click.stop="menuLayerBottom">置底</div>
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
    <el-dialog v-model="showClassModal" :title="editingClassId !== null ? '编辑类别' : '添加类别'" width="400px" append-to-body>
      <el-form :model="clsForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="clsForm.name" placeholder="类别名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <div style="width:100%">
            <div class="preset-palette">
              <span
                v-for="col in PRESET_COLORS"
                :key="col"
                class="preset-dot"
                :class="{ active: clsForm.color === col }"
                :style="{ background: col }"
                @click="clsForm.color = col"
              />
            </div>
            <el-color-picker v-model="clsForm.color" size="small" class="custom-color" />
          </div>
        </el-form-item>
        <el-form-item v-if="plugin.name === 'keypoint'" label="关键点">
          <div style="width:100%">
            <div
              v-for="(kp, i) in clsForm.kpNames"
              :key="i"
              style="display:flex;gap:6px;align-items:center;margin-bottom:4px"
            >
              <el-input v-model="clsForm.kpNames[i]" size="small" placeholder="关键点名称" />
              <el-color-picker v-model="clsForm.kpColors[i]" size="small" />
              <el-button text size="small" type="danger" @click="clsForm.kpNames.splice(i,1); clsForm.kpColors.splice(i,1)">×</el-button>
            </div>
            <el-button size="small" @click="clsForm.kpNames.push(''); clsForm.kpColors.push('#409eff')">+ 关键点</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showClassModal = false">取消</el-button>
        <el-button type="primary" @click="addClass">{{ editingClassId !== null ? '保存' : '添加' }}</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="ocrInputVisible" title="输入 OCR 文本" width="380px" append-to-body>
      <el-input v-model="ocrInput" placeholder="OCR 文本" @keydown.enter="confirmOcr" />
      <template #footer>
        <el-button @click="ocrInputVisible = false; pendingOcr = null">取消</el-button>
        <el-button type="primary" @click="confirmOcr">确定</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showHelpModal" title="快捷键" width="420px" append-to-body>
      <div class="shortcut-grid">
        <div v-for="s in shortcutList" :key="s.keys" class="shortcut-row">
          <span class="shortcut-keys">{{ s.keys }}</span>
          <span class="shortcut-desc">{{ s.desc }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import { Select, FullScreen, ZoomIn } from "@element-plus/icons-vue";
import AnnotationCanvas from "./AnnotationCanvas.vue";
import AnnotationHistoryBar from "./AnnotationHistoryBar.vue";
import AnnotationToolbar from "./AnnotationToolbar.vue";
import AnnotationRightPanel from "./AnnotationRightPanel.vue";
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
const cursorPos = reactive({ x: 0, y: 0 });
const imageFilter = ref<"all" | "annotated" | "unannotated">("all");
const filteredImages = computed(() => {
  if (imageFilter.value === "all") return store.images;
  return store.images.filter((i) => (imageFilter.value === "annotated") === (i.status === "annotated"));
});
const showHelpModal = ref(false);
const shortcutList = computed(() => {
  const base = [
    { keys: "1-7 / s b r p k o c", desc: "切换标注工具" },
    { keys: "Ctrl+S", desc: "保存当前图" },
    { keys: "Ctrl+Z / Ctrl+Y", desc: "撤销 / 重做" },
    { keys: "Ctrl+C / Ctrl+V", desc: "复制 / 粘贴标注" },
    { keys: "Delete / Backspace", desc: "删除选中标注" },
    { keys: "Esc", desc: "取消绘制" },
    { keys: "←→ / a d", desc: "上一张 / 下一张" },
  ];
  const extra: any[] = [];
  if (plugin.value.name === "keypoint") extra.push({ keys: "0/1/2", desc: "关键点可见性 Hidden/Occluded/Visible" });
  if (plugin.value.name === "ocr") extra.push({ keys: "t", desc: "矩形 / 四边形模式切换" });
  return [...base, ...extra];
});
const fontSize = ref(6);
const strokeW = ref(1.5);
const selStrokeW = ref(2);
const tagH = computed(() => Math.max(8, fontSize.value + 6));
const settingsKey = "annotation-workbench-settings";
function loadSettings(): any {
  try {
    return JSON.parse(localStorage.getItem(settingsKey) || "{}");
  } catch {
    return {};
  }
}
const annSettings = reactive({ labelFontSize: 6, strokeWidth: 1.5, selStrokeWidth: 2, ...loadSettings() });fontSize.value = annSettings.labelFontSize;
strokeW.value = annSettings.strokeWidth;
selStrokeW.value = annSettings.selStrokeWidth;
watch(annSettings, () => {
  fontSize.value = annSettings.labelFontSize;
  strokeW.value = annSettings.strokeWidth;
  selStrokeW.value = annSettings.selStrokeWidth;
  localStorage.setItem(settingsKey, JSON.stringify(annSettings));
}, { deep: true });
// 协作：锁定被拒提示 + 远程标注同步刷新（顶层 watch，随组件卸载自动清理）
watch(
  () => props.collab?.lockDeniedTick?.value ?? 0,
  () => {
    if (props.collab?.lockDeniedTick?.value) ElMessage.warning("保存被拒绝：图片已被其他用户锁定");
  }
);
watch(
  () => props.collab?.remoteAnnotationTick?.value ?? 0,
  () => {
    if (props.collab?.remoteAnnotationTick?.value && store.currentImageId) {
      loadCurrentImage(store.currentImageId).catch(() => {});
    }
  }
);

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
const hintText = computed(() => {
  const t = displayTools.value.find((x) => x.name === currentTool.value);
  return (t as any)?.title || (t as any)?.tip || "";
});
const polyPts = computed(() =>
  seg.points.value.map((p) => `${p.x * cw.value},${p.y * ch.value}`).join(" ")
);
const ocrQuadPts = computed(() =>
  ocr.quadPoints.value.map((p) => `${p.x * cw.value},${p.y * ch.value}`).join(" ")
);

let drawStart: { x: number; y: number } | null = null;
let rbLast: { x: number; y: number } | null = null;
let panState: { startX: number; startY: number; px: number; py: number } | null = null;
let dragState:
  | { type: "move" | "resize" | "rotate" | "poly-vertex" | "kp-vertex" | "kp-move" | "kp-resize"; ann: Annotation; handle: string; startX: number; startY: number; orig: Annotation }
  | null = null;
let loadImgToken = 0;
let lockRenewTimer: number | null = null;
let lockedImageId: number | null = null;
let unmounted = false;

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
function deleteAnnotation(id: string) {
  if (lockedByOther.value) return;
  const target = store.annotations.find((a) => a.id === id);
  if (!target) return;
  ElMessageBox.confirm(`将删除 1 个${target.type}标注，且不可恢复。`, "删除标注", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}
function deleteSelected() {
  deleteAnnotation(store.selectedAnnotationId);
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
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  if (copy.x1 !== undefined) {
    copy.x1 = clamp(copy.x1 + 0.01);
    copy.x2 = clamp(copy.x2 + 0.01);
    copy.y1 = clamp(copy.y1 + 0.01);
    copy.y2 = clamp(copy.y2 + 0.01);
  } else if (copy.cx !== undefined) {
    copy.cx = clamp(copy.cx + 0.01);
    copy.cy = clamp(copy.cy + 0.01);
  } else if (copy.points) {
    copy.points = copy.points.map((p: any) => ({ x: clamp(p.x + 0.01), y: clamp(p.y + 0.01) }));
  } else if (copy.keypoints) {
    copy.keypoints = copy.keypoints.map((k: any) => ({ ...k, x: clamp(k.x + 0.01), y: clamp(k.y + 0.01) }));
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
const editingClassId = ref<number | null>(null);
const PRESET_COLORS = [
  "#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#909399", "#9b59b6",
  "#00bcd4", "#ff9800", "#795548", "#607d8b", "#e91e63", "#8bc34a",
];
const clsForm = reactive({ name: "", color: "#409eff", kpNames: [] as string[], kpColors: [] as string[] });

function openAddClass() {
  editingClassId.value = null;
  clsForm.name = "";
  clsForm.color = PRESET_COLORS[0];
  clsForm.kpNames = [];
  clsForm.kpColors = [];
  showClassModal.value = true;
}
function openEditClass(c: any) {
  editingClassId.value = c.id;
  clsForm.name = c.name || "";
  clsForm.color = c.color || PRESET_COLORS[0];
  clsForm.kpNames = [...(c.keypoint_names || [])];
  clsForm.kpColors = [...(c.keypoint_colors || [])];
  showClassModal.value = true;
}
const ocrInputVisible = ref(false);
const ocrInput = ref("");
let pendingOcr: Annotation | null = null;

async function addClass() {
  if (lockedByOther.value) return;
  if (!clsForm.name.trim()) return;
  const kpNames = clsForm.kpNames.filter((n) => n.trim());
  if (editingClassId.value !== null) {
    const c = taskClasses.value.find((x) => x.id === editingClassId.value);
    if (c) {
      c.name = clsForm.name.trim();
      c.color = clsForm.color;
      c.keypoint_names = kpNames.length ? kpNames : undefined;
      c.keypoint_colors = kpNames.length ? clsForm.kpColors.slice(0, kpNames.length) : undefined;
    }
  } else {
    const id =
      taskClasses.value.length > 0
        ? Math.max(...taskClasses.value.map((c) => c.id)) + 1
        : 0;
    taskClasses.value.push({
      id,
      name: clsForm.name.trim(),
      color: clsForm.color,
      keypoint_names: kpNames.length ? kpNames : undefined,
      keypoint_colors: kpNames.length ? clsForm.kpColors.slice(0, kpNames.length) : undefined,
    });
  }
  clsForm.name = "";
  clsForm.kpNames = [];
  clsForm.kpColors = [];
  showClassModal.value = false;
  await saveClasses();
}
async function removeClass(id: number) {
  if (lockedByOther.value) return;
  taskClasses.value = taskClasses.value.filter((c) => c.id !== id);
  const before = store.annotations.length;
  store.annotations = store.annotations.filter((a: any) => {
    const uses = a.class_id === id || (Array.isArray(a.class_ids) && a.class_ids.includes(id));
    return !uses;
  });
  if (store.annotations.length !== before) {
    store.markUnsaved();
    pushHistory();
  }
  if (selectedClassId.value === id) selectedClassId.value = taskClasses.value[0]?.id ?? null;
  await saveClasses();
}
function clsCount(classId: number) {
  return store.annotations.filter((a) => a.class_id === classId).length;
}
async function changeClassColor(id: number, color: string) {
  const c = taskClasses.value.find((x) => x.id === id);
  if (!c) return;
  c.color = color;
  // 颜色为响应式，标注框颜色（clsColor）会自动联动更新
  await saveClasses();
}
async function saveClasses() {
  if (!store.taskId || lockedByOther.value) return;
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

let _canvasEl: HTMLElement | null = null;
function getCanvasEl(): HTMLElement | null {
  if (!_canvasEl || !document.contains(_canvasEl)) {
    _canvasEl = document.querySelector(".annotation-canvas") as HTMLElement | null;
  }
  return _canvasEl;
}

function toImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const el = getCanvasEl();
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
  rbLast = null;
  seg.points.value = [];
  rot.step.value = 0;
  rot.pt1.value = null;
  rot.pt2.value = null;
  kp.pending.value = [];
  kp.boxMode.value = false;
  kp.boxStart.value = null;
  kp.boxEnd.value = null;
  det.drawing.value = false;
  ocr.reset();
}

function onImgLoad() {
  imageLoaded.value = true;
}

function onWheel(e: WheelEvent) {
  if (!cw.value || !ch.value) return;
  const el = getCanvasEl();
  if (!el) return;
  const r = el.getBoundingClientRect();
  const cx = e.clientX - r.left;
  const cy = e.clientY - r.top;
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  zoomAt(factor, cx, cy);
}
function boxZoom(factor: number, clientX: number, clientY: number) {
  const el = getCanvasEl();
  if (!el) return;
  const r = el.getBoundingClientRect();
  zoomAt(factor, clientX - r.left, clientY - r.top);
}
function zoomAt(factor: number, cx: number, cy: number) {
  if (!cw.value || !ch.value) return;
  const el = getCanvasEl();
  if (!el) return;
  const r = el.getBoundingClientRect();
  const newZoom = Math.min(3, Math.max(0.1, canvas.zoom.value * factor));
  // 光标下的图像点（归一化）
  const off = canvas.imageOffset(r.width, r.height);
  const ix = (cx - off.left) / dw.value;
  const iy = (cy - off.top) / dh.value;
  canvas.zoom.value = newZoom;
  canvas.dw.value = cw.value * newZoom;
  canvas.dh.value = ch.value * newZoom;
  // 缩放后让该图像点仍落在光标位置（修正 pan）
  const newLeft = cx - ix * canvas.dw.value;
  const newTop = cy - iy * canvas.dh.value;
  canvas.setPan(
    newLeft - r.width / 2 + canvas.dw.value / 2,
    newTop - r.height / 2 + canvas.dh.value / 2
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
  resetDrawingState();
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
      if (unmounted) return;
      try {
        const items = await loadImagePage(p, true);
        if (unmounted) return;
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
  if (!datasetId || imagePrefetching.value || unmounted) return;
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
    const r = await props.api.getTaskProgress(store.taskId);
    const d = r?.data?.data;
    if (d) {
      store.totalCount = d.total_images ?? store.totalCount;
      store.annotatedCount = d.annotated_images ?? store.annotatedCount;
    }
  } catch {
    /* ignore */
  }
}

async function init() {
  store.reset();
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
  const doSwitch = () => {
    store.currentImageIndex = idx;
    ensureMoreImages(idx);
    loadCurrentImage(store.images[idx].id);
  };
  if (store.unsaved) {
    ElMessageBox({
      title: "未保存",
      message: "当前图有未保存的修改，是否先保存？",
      confirmButtonText: "保存并切换",
      cancelButtonText: "不保存",
      distinguishCancelAndClose: true,
      closeOnClickModal: false,
      type: "warning",
    })
      .then(async (action: any) => {
        if (action === "confirm") await saveAnn();
        if (action === "confirm" || action === "cancel") doSwitch();
        // action === 'close' => 留在当前图，不切换
      })
      .catch(() => {});
    return;
  }
  doSwitch();
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
  }
  fetchTaskProgress();
}

function openHistory() {
  // 历史抽屉由外层路由包装层承载（保持组件库解耦），此处仅触发事件
  emit("open-history");
}

// ==== 绘制/编辑（同阶段0-5a 逻辑） ====
function onDblClick(e: MouseEvent) {
  e.preventDefault();
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
      created.class_id = selectedClassId.value ?? created.class_id;
      store.annotations.push(created);
      store.markUnsaved();
      pushHistory();
    }
  } else if (currentTool.value === "keypoint") {
    kp.beginBox();
  } else if (currentTool.value === "ocr" && ocr.mode.value === "quad") {
    const created = ocr.closeQuad();
    if (created) {
      pendingOcr = created;
      ocrInput.value = "";
      ocrInputVisible.value = true;
    }
  }
}
function onCanvasDown(e: MouseEvent) {
  e.preventDefault();
  if (e.button !== 0 || lockedByOther.value) return;
  const p = toImagePoint(e);
  if (!p) return;
  store.selectedAnnotationId = "";
  if (currentTool.value === "pan") {
    panState = { startX: e.clientX, startY: e.clientY, px: canvas.panX.value, py: canvas.panY.value };
    return;
  }
  if (currentTool.value === "zoom") {
    boxZoom(e.altKey ? 0.8 : 1.25, e.clientX, e.clientY);
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
      created.class_id = selectedClassId.value ?? created.class_id;
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
    if (ocr.mode.value === "quad") {
      ocr.addQuadPoint(p);
    } else {
      const created = ocr.onPoint(p);
      if (created) {
        pendingOcr = created;
        ocrInput.value = "";
        ocrInputVisible.value = true;
      }
    }
  }
}
function confirmOcr() {
  if (pendingOcr) {
    pendingOcr.text = ocrInput.value;
    pendingOcr.class_id = selectedClassId.value ?? pendingOcr.class_id;
    if (plugin.value.create(pendingOcr)) {
      store.annotations.push(pendingOcr);
      store.markUnsaved();
      pushHistory();
    } else {
      ElMessage.warning("OCR 区域无效，未创建标注");
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
  if (handle.startsWith("kpb-")) {
    const h = handle.replace("kpb-", "");
    if (h === "move") {
      dragState = { type: "kp-move", ann, handle: "", startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    } else {
      dragState = { type: "kp-resize", ann, handle: h, startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
    }
    return;
  }
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
  e.preventDefault();
  if (lockedByOther.value) return;
  const crossPt = toImagePoint(e);
  if (crossPt) {
    crosshair.x = crossPt.x;
    crosshair.y = crossPt.y;
  }
  if (panState) {
    canvas.setPan(panState.px + (e.clientX - panState.startX), panState.py + (e.clientY - panState.startY));
    return;
  }
  const ip = toImagePoint(e);
  if (ip) {
    cursorPos.x = Math.round(ip.x * (canvas.cw.value || 0));
    cursorPos.y = Math.round(ip.y * (canvas.ch.value || 0));
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
    const o = dragState.orig;
    const ann = dragState.ann;
    const dx = (e.clientX - dragState.startX) / dw.value;
    const dy = (e.clientY - dragState.startY) / dh.value;
    const nc = (v: number) => Math.max(0, Math.min(1, v));
    const movePoints = (pts: any[]) => pts.map((p: any) => ({ ...p, x: nc(p.x + dx), y: nc(p.y + dy) }));

    if (dragState.type === "kp-move") {
      if (ann.bounding_box) {
        ann.bounding_box.cx = nc(o.bounding_box.cx + dx);
        ann.bounding_box.cy = nc(o.bounding_box.cy + dy);
      }
      ann.keypoints = (o.keypoints || []).map((k: any) => ({ ...k, x: nc(k.x + dx), y: nc(k.y + dy) }));
      store.markUnsaved();
      return;
    }
    if (dragState.type === "kp-resize") {
      kp.resizeBBox(ann, o, dragState.handle, dx, dy);
      store.markUnsaved();
      return;
    }
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
      const c = getCanvasEl();
      if (c) {
        const r = c.getBoundingClientRect();
        const off = canvas.imageOffset(r.width, r.height);
        const centerX = r.left + off.left + dragState.ann.cx * dw.value;
        const centerY = r.top + off.top + dragState.ann.cy * dh.value;
        rot.onRotate(dragState.ann, centerX, centerY, dragState.startX, dragState.startY, e.clientX, e.clientY);
      }
      store.markUnsaved();
      return;
    }
    if (dragState.type === "move") {
      if (ann.type === "AxisAlignedBox") {
        ann.x1 = nc(o.x1 + dx); ann.x2 = nc(o.x2 + dx);
        ann.y1 = nc(o.y1 + dy); ann.y2 = nc(o.y2 + dy);
      } else if (ann.type === "RotatedBox") {
        ann.cx = nc(o.cx + dx); ann.cy = nc(o.cy + dy);
      } else if (ann.type === "Polygon") {
        ann.points = movePoints(o.points);
      } else if (ann.type === "Ocr") {
        ann.points = movePoints(o.points);
      }
      store.markUnsaved();
      return;
    }
    if (dragState.type === "resize") {
      if (ann.type === "RotatedBox") {
        const p = toImagePoint(e);
        if (p) rot.onDragResize(ann, o, dragState.handle, p, cw.value, ch.value, ch.value / cw.value);
      } else if (ann.type === "AxisAlignedBox") {
        if (dragState.handle.includes("l")) ann.x1 = nc(Math.min(o.x2 - 0.01, o.x1 + dx));
        if (dragState.handle.includes("r")) ann.x2 = nc(Math.max(o.x1 + 0.01, o.x2 + dx));
        if (dragState.handle.includes("t")) ann.y1 = nc(Math.min(o.y2 - 0.01, o.y1 + dy));
        if (dragState.handle.includes("b")) ann.y2 = nc(Math.max(o.y1 + 0.01, o.y2 + dy));
      } else if (ann.type === "Ocr") {
        const ox = { x1: Math.min(...o.points.map((p: any) => p.x)), x2: Math.max(...o.points.map((p: any) => p.x)) };
        const oy = { y1: Math.min(...o.points.map((p: any) => p.y)), y2: Math.max(...o.points.map((p: any) => p.y)) };
        let x1 = ox.x1, y1 = oy.y1, x2 = ox.x2, y2 = oy.y2;
        if (dragState.handle.includes("l")) x1 = nc(Math.min(x2 - 0.01, x1 + dx));
        if (dragState.handle.includes("r")) x2 = nc(Math.max(x1 + 0.01, x2 + dx));
        if (dragState.handle.includes("t")) y1 = nc(Math.min(y2 - 0.01, y1 + dy));
        if (dragState.handle.includes("b")) y2 = nc(Math.max(y1 + 0.01, y2 + dy));
        ann.points = [{ x: x1, y: y1 }, { x: x2, y: y1 }, { x: x2, y: y2 }, { x: x1, y: y2 }];
      }
      store.markUnsaved();
      return;
    }
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
      created.class_id = selectedClassId.value ?? created.class_id;
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
      created.class_id = selectedClassId.value ?? created.class_id;
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
function menuCopy() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  copySelected();
}
function layerMove(ann: any, toTop: boolean) {
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  const rest = store.annotations.filter((a) => a.id !== ann.id);
  store.annotations = toTop ? [ann, ...rest] : [...rest, ann];
  store.markUnsaved();
  pushHistory();
}
function menuLayerTop() {
  const ann = annMenu.ann;
  closeMenu();
  layerMove(ann, true);
}
function menuLayerBottom() {
  const ann = annMenu.ann;
  closeMenu();
  layerMove(ann, false);
}
function deleteById(id: string) {
  deleteAnnotation(id);
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
  if (e.ctrlKey && e.key.toLowerCase() === "s") { e.preventDefault(); saveAnn(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === "c") { e.preventDefault(); copySelected(); return; }
  if (e.ctrlKey && e.key.toLowerCase() === "v") { e.preventDefault(); pasteCopied(); return; }
  if (e.key === "Escape") { resetDrawingState(); return; }
  // 方向键 / a d ：上一下一张（select 工具下）
  if (currentTool.value === "select") {
    if (e.key === "ArrowRight" || e.key.toLowerCase() === "d") { nextImg(); return; }
    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a") { prevImg(); return; }
  }
  if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
  // 关键点工具下：0/1/2 设可见性（优先于切工具，避免冲突）
  if (currentTool.value === "keypoint") {
    if (["0", "1", "2"].includes(e.key)) {
      const map: Record<string, string> = { "0": "Hidden", "1": "Occluded", "2": "Visible" };
      pendingKpVisibility.value = map[e.key];
      return;
    }
  }
  if (currentTool.value === "ocr" && e.key.toLowerCase() === "t") {
    ocr.toggleMode();
    return;
  }
  if (["1", "s"].includes(e.key)) setTool("select");
  else if (["2", "b"].includes(e.key)) setTool("box");
  else if (["3", "r"].includes(e.key)) setTool("rotated_box");
  else if (["4", "p"].includes(e.key)) setTool("polygon");
  else if (["5", "k"].includes(e.key)) setTool("keypoint");
  else if (["6", "o"].includes(e.key)) setTool("ocr");
  else if (["7", "c"].includes(e.key)) setTool("classification");
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
  unmounted = true;
  window.removeEventListener("mousemove", onMove);
  window.removeEventListener("mouseup", onUp);
  window.removeEventListener("beforeunload", onBeforeUnload);
  document.removeEventListener("keydown", onKey);
  if (store.unsaved && store.currentImageId && !lockedByOther.value) {
    props.api.saveAnnotations(store.taskId, store.currentImageId, store.annotations).catch(() => {});
  }
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
  user-select: none;
  -webkit-user-select: none;
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
.progress-text {
  color: var(--el-text-color-regular);
  font-size: 13px;
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
.ann-canvas-area {
  flex: 1;
  min-width: 0;
  position: relative;
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
.cross-svg {
  pointer-events: none;
}
.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 4px;
}
.shortcut-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.shortcut-row {
  display: flex;
  gap: 12px;
  align-items: center;
}
.shortcut-keys {
  min-width: 160px;
  color: var(--el-color-primary);
  font-weight: 500;
}
.shortcut-desc {
  color: #606266;
}
.preset-palette {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.preset-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
}
.preset-dot.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--el-color-primary);
}
.custom-color {
  vertical-align: middle;
}
</style>
