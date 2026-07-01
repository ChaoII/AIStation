<template>
  <div class="ann-page">
    <div class="ann-header">
      <div class="ann-title">
        <el-button text @click="handleBack" :icon="ArrowLeft" />
        <el-tag :type="taskTypeTag" size="small">{{ taskTypeLabel }}</el-tag>
        <span class="task-name">{{ task?.name }}</span>
      </div>
      <div class="header-right">
        <span class="progress-text">{{ annotatedCount }}/{{ totalCount }}</span>
        <el-progress :percentage="progressPct" :stroke-width="6" :show-text="false" style="width:100px" />
      </div>
    </div>
    <div class="ann-body">
      <!-- 左侧工具栏 -->
      <aside class="ann-leftbar">
        <div class="tool-list">
          <div v-for="t in displayTools" :key="t.name" class="tool-btn" :class="{ active: currentTool === t.name }" @click="setTool(t.name)" :title="t.tip">
            <el-icon :size="18"><component :is="t.icon" /></el-icon>
            <span class="tool-label">{{ t.label }}</span>
          </div>
        </div>
      </aside>
      <!-- 画布 -->
      <main class="ann-canvas-area" ref="canvasWrapRef">
        <div class="canvas-container" ref="canvasRef" @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp" @mouseenter="onMouseEnter" @mouseleave="onMouseLeave" @wheel.prevent="onWheel" @dblclick="onDblClick" @contextmenu.prevent>
          <!-- 十字线 -->
          <div ref="cxXRef" class="crosshair crosshair-x" v-show="showCrosshair" />
          <div ref="cxYRef" class="crosshair crosshair-y" v-show="showCrosshair" />
          <img v-if="imgUrl" ref="imgRef" :src="imgUrl" :style="imgStyle" @load="onImgLoad" @error="imgUrl = ''" />
          <svg v-if="imgUrl" class="ann-svg" :style="svgStyle" :viewBox="`0 0 ${cw} ${ch}`">
            <!-- 已有标注 -->
            <g v-for="ann in store.annotations" :key="ann.id" @mousedown.left.stop="onAnnMouseDown($event, ann)">
              <template v-if="ann.type === 'AxisAlignedBox'">
                <rect :x="ann.x1 * cw" :y="ann.y1 * ch" :width="(ann.x2 - ann.x1) * cw" :height="(ann.y2 - ann.y1) * ch"
                  :stroke="clsColor(ann.class_id)" :stroke-width="store.selectedAnnotationId === ann.id ? 2 : 1.5"
                  :fill="store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'none'"
                  vector-effect="non-scaling-stroke" />
                <g v-if="store.selectedAnnotationId === ann.id">
                  <rect v-for="h in boxHandles(ann)" :key="h.key" :x="h.x - 4" :y="h.y - 4" width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5" :data-handle="h.key" class="handle" vector-effect="non-scaling-stroke" />
                </g>
                <g class="ann-label">
                  <rect :x="ann.x1 * cw" :y="ann.y1 * ch - 16" :width="labelW(getCls(ann.class_id)?.name)" height="16" :fill="clsColor(ann.class_id)" rx="2" />
                  <text :x="ann.x1 * cw + 4" :y="ann.y1 * ch - 4" fill="#fff" font-size="10" font-weight="500">{{ getCls(ann.class_id)?.name }}</text>
                </g>
              </template>
            </g>
            <!-- 绘制中的矩形虚线预览 -->
            <rect v-if="drawing && drawEnd" :x="Math.min(drawStart.x, drawEnd.x)" :y="Math.min(drawStart.y, drawEnd.y)"
              :width="Math.abs(drawEnd.x - drawStart.x)" :height="Math.abs(drawEnd.y - drawStart.y)"
              stroke="#3b82f6" fill="rgba(59,130,246,0.08)" stroke-width="1.5" stroke-dasharray="6,4"
              vector-effect="non-scaling-stroke" />
          </svg>
          <div v-if="!imgUrl && store.currentImage" class="no-image">加载失败</div>
          <div v-else-if="!store.currentImage" class="no-image">No image loaded</div>
        </div>
      </main>
      <!-- 右侧面板 -->
      <aside class="ann-rightbar">
        <div class="panel">
          <div class="panel-section">
            <div class="section-title-row"><span class="section-title">图片列表</span><span class="count-chip">{{ store.images.length }}</span></div>
            <div class="scroll-area">
              <div v-for="(img, idx) in store.images" :key="img.id" class="image-item" :class="{ active: idx === store.currentImageIndex }" @click="goToImage(idx)">
                <span class="dot" :class="img.status === 'annotated' ? 'dot-done' : 'dot-pending'" />
                <div class="img-info"><span class="img-name">{{ img.filename }}</span><span class="img-meta">{{ img.updated_by?.name || '--' }} {{ fmtTime(img.updated_time) }}</span></div>
              </div>
            </div>
          </div>
          <div class="divider" />
          <div class="panel-section">
            <div class="section-title-row">
              <span class="section-title">类别</span>
              <el-button text size="small" @click="showClassModal = true">+ 添加</el-button>
            </div>
            <div class="scroll-area">
              <div v-for="cls in taskClasses" :key="cls.id" class="class-item" :class="{ active: selectedClassId === cls.id }" @click="selectedClassId = cls.id">
                <span class="dot-color" :style="{ background: cls.color }" />
                <span class="flex-1 text-sm">{{ cls.name }}</span>
                <span class="text-xs text-gray-400">{{ clsCount(cls.id) }}</span>
                <el-button text size="small" @click.stop="removeClass(cls.id)">×</el-button>
              </div>
              <div v-if="taskClasses.length === 0" class="empty-hint">请添加标签类别</div>
            </div>
          </div>
          <div class="divider" />
          <div class="panel-section">
            <div class="section-title-row"><span class="section-title">标注列表</span><el-badge :value="store.annotations.length" :max="999" /></div>
            <div class="scroll-area">
              <div v-for="ann in store.annotations" :key="ann.id" class="ann-item" :class="{ active: store.selectedAnnotationId === ann.id }" @click="store.selectedAnnotationId = ann.id">
                <span class="dot-color" :style="{ background: clsColor(ann.class_id) }" />
                <span class="flex-1 text-sm">{{ getCls(ann.class_id)?.name || '?' }}</span>
                <span class="text-xs text-gray-400">矩形</span>
                <el-button text size="small" @click.stop="removeAnn(ann.id)" type="danger">×</el-button>
              </div>
              <div v-if="store.annotations.length === 0" class="empty-hint">暂无标注</div>
            </div>
          </div>
        </div>
      </aside>
    </div>
    <!-- 底栏（固定，无需滚动） -->
    <footer class="ann-footer">
      <span class="hint">{{ toolHint }}</span>
      <span class="text-xs text-gray-400 font-mono">X:{{ cursorX }} Y:{{ cursorY }}</span>
      <span class="text-xs text-gray-400">{{ Math.round(store.zoom * 100) }}%</span>
      <div class="sep" />
      <el-button size="small" :disabled="!store.currentImage" circle @click="prevImg"><el-icon><ArrowLeft /></el-icon></el-button>
      <span class="nav-text">{{ store.currentImageIndex + 1 }}/{{ store.images.length }}</span>
      <el-button size="small" :disabled="!store.hasNext" circle @click="nextImg"><el-icon><ArrowRight /></el-icon></el-button>
      <div class="sep" />
      <el-button size="small" type="primary" :loading="store.saving" @click="saveAnn" :disabled="!store.currentImage">保存</el-button>
    </footer>
    <!-- 添加类别弹窗 -->
    <el-dialog v-model="showClassModal" title="添加类别" width="320px">
      <el-form :model="clsForm" label-width="60px">
        <el-form-item label="名称"><el-input v-model="clsForm.name" placeholder="类别名称" /></el-form-item>
        <el-form-item label="颜色"><el-color-picker v-model="clsForm.color" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showClassModal = false">取消</el-button>
        <el-button type="primary" @click="addClass">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage, ElBadge } from "element-plus"
import { ArrowLeft, ArrowRight, Delete } from "@element-plus/icons-vue"
import { AnnotationAPI } from "@/api/module_annotation"
import { useAnnotationStore, type ToolName } from "./store"

const route = useRoute(); const router = useRouter()
const store = useAnnotationStore()

// Refs
const canvasRef = ref<HTMLElement | null>(null)
const canvasWrapRef = ref<HTMLElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const cxXRef = ref<HTMLElement | null>(null)
const cxYRef = ref<HTMLElement | null>(null)

// State
const imgUrl = ref("")
const cw = ref(1); const ch = ref(1)
const cursorX = ref(0); const cursorY = ref(0)
const showCrosshair = ref(false)
const selectedClassId = ref(0)
const currentTool = ref<ToolName>("box")
const taskType = ref("detection"); const task = ref<any>(null)
const taskClasses = ref<any[]>([])
const showClassModal = ref(false)
const clsForm = ref({ name: "", color: "#409eff" })

// Drawing state
const drawing = ref(false)
const drawStart = ref({ x: 0, y: 0 })
const drawEnd = ref<{ x: number; y: number } | null>(null)
const dragState = ref<{ active: boolean; type: string; ann: any; orig: any; startX: number; startY: number; handle: string }>({
  active: false, type: "", ann: null, orig: null, startX: 0, startY: 0, handle: ""
})

// ===== Tools =====
const baseTools: { name: ToolName; label: string; tip: string; icon: any }[] = [
  { name: "select", label: "选择", tip: "点击选择标注，拖拽移动", icon: "Select" },
  { name: "pan", label: "平移", tip: "拖拽平移画布", icon: "Rank" },
  { name: "zoom", label: "缩放", tip: "滚轮缩放", icon: "ZoomIn" },
]
const taskToolMap: Record<string, { name: ToolName; label: string; tip: string; icon: any }[]> = {
  detection: [{ name: "box", label: "矩形", tip: "拖拽创建矩形框", icon: "FullScreen" }],
  rotated_detection: [{ name: "rotated_box", label: "旋转框", tip: "旋转框", icon: "RefreshRight" }],
  segmentation: [{ name: "polygon", label: "多边形", tip: "点击创建多边形", icon: "EditPen" }],
  keypoint: [{ name: "keypoint", label: "关键点", tip: "放置关键点", icon: "Coin" }],
  ocr: [{ name: "ocr", label: "OCR", tip: "文本标注", icon: "Document" }],
  classification: [{ name: "classification", label: "分类", tip: "图像分类", icon: "Collection" }],
}
const displayTools = computed(() => [...baseTools, ...(taskToolMap[taskType.value] || [])])
const taskTypeLabel = computed(() => ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" }[taskType.value] || taskType.value))
const taskTypeTag = computed(() => ({ detection: undefined, rotated_detection: "warning", segmentation: "danger", keypoint: "warning", ocr: "info", classification: "info" } as Record<string, any>)[taskType.value])
const toolHint = computed(() => ({ select: "点击选择标注，拖拽移动", pan: "拖拽平移", zoom: "滚轮缩放", box: "拖拽创建矩形框", rotated_box: "三步旋转框", polygon: "点击创建多边形", keypoint: "放置关键点", ocr: "文本标注", classification: "选择类别" }[currentTool.value] || ""))

const annotatedCount = computed(() => store.images.filter(i => i.status === "annotated").length)
const totalCount = computed(() => store.images.length)
const progressPct = computed(() => totalCount.value === 0 ? 0 : Math.round(annotatedCount.value / totalCount.value * 100))

// ===== 图片显示 =====
const imgStyle = computed(() => {
  const dw = cw.value * store.zoom; const dh = ch.value * store.zoom
  return { width: dw + "px", height: dh + "px", transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)` }
})
const svgStyle = computed(() => {
  const dw = cw.value * store.zoom; const dh = ch.value * store.zoom
  return { width: dw + "px", height: dh + "px", transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)` }
})

function onImgLoad() {
  const el = imgRef.value; const c = canvasRef.value; if (!el || !c) return
  cw.value = el.naturalWidth; ch.value = el.naturalHeight
  const r = c.getBoundingClientRect()
  const z = Math.min(r.width / cw.value, r.height / ch.value)
  store.setZoom(Math.min(z * 0.95, 1))
  store.setPan(0, 0)
}

function mouseToImgPx(e: MouseEvent) {
  const c = canvasRef.value; if (!c || !cw.value || !ch.value) return null
  const r = c.getBoundingClientRect(); const dw = cw.value * store.zoom; const dh = ch.value * store.zoom
  const ix = r.width / 2 - dw / 2 + store.panX; const iy = r.height / 2 - dh / 2 + store.panY
  return { x: Math.max(0, Math.min(dw, e.clientX - r.left - ix)), y: Math.max(0, Math.min(dh, e.clientY - r.top - iy)) }
}

// ===== Crosshair =====
function updCrosshair(e: MouseEvent) {
  const c = canvasRef.value; if (!c) return
  const r = c.getBoundingClientRect(); const x = e.clientX - r.left; const y = e.clientY - r.top
  if (cxXRef.value) { cxXRef.value.style.top = y + "px" }
  if (cxYRef.value) { cxYRef.value.style.left = x + "px" }
}

// ===== 类别 =====
function getCls(id: number) { return taskClasses.value.find(c => c.id === id) }
function clsColor(id: number) { return getCls(id)?.color || "#3b82f6" }
function clsCount(id: number) { return store.annotations.filter(a => a.class_id === id).length }
function labelW(name: string) { return Math.max(30, ((name?.length || 0) * 8 + 16)) }
function addClass() {
  if (!clsForm.value.name.trim()) return
  const id = taskClasses.value.length > 0 ? Math.max(...taskClasses.value.map(c => c.id)) + 1 : 0
  taskClasses.value.push({ id, name: clsForm.value.name, color: clsForm.value.color })
  clsForm.value = { name: "", color: "#409eff" }
  showClassModal.value = false
  saveClassesToTask()
}
function removeClass(id: number) {
  taskClasses.value = taskClasses.value.filter(c => c.id !== id)
  store.annotations = store.annotations.filter(a => a.class_id !== id)
  if (selectedClassId.value === id) selectedClassId.value = taskClasses.value[0]?.id ?? 0
  saveClassesToTask()
}
async function saveClassesToTask() {
  if (!task.value?.id) return
  try {
    await AnnotationAPI.updateTask(task.value.id, { classes: taskClasses.value })
  } catch {}
}

// ===== 画布事件 =====
function onMouseEnter(e: MouseEvent) {
  if (currentTool.value === "box") { showCrosshair.value = true; updCrosshair(e) }
}
function onMouseLeave() {
  showCrosshair.value = false
}
function onMouseDown(e: MouseEvent) {
  if (!store.currentImage) return
  // 选择工具 → 点击标注或空白
  if (currentTool.value === "select") {
    store.selectedAnnotationId = null; return
  }
  // 平移
  if (currentTool.value === "pan") {
    dragState.value = { active: true, type: "pan", ann: null, orig: null, startX: e.clientX, startY: e.clientY, handle: "" }; return
  }
  // 矩形工具
  if (currentTool.value === "box") {
    if (taskClasses.value.length === 0) { ElMessage.warning("请先添加类别"); return }
    if (!selectedClassId.value && taskClasses.value.length > 0) selectedClassId.value = taskClasses.value[0].id
    const p = mouseToImgPx(e); if (!p) return
    drawing.value = true
    drawStart.value = { x: p.x / store.zoom, y: p.y / store.zoom }
    drawEnd.value = null
    showCrosshair.value = true; updCrosshair(e)
    return
  }
}

function onMouseMove(e: MouseEvent) {
  if (!store.currentImage) return
  const p = mouseToImgPx(e)
  if (p) { cursorX.value = Math.round(p.x / store.zoom); cursorY.value = Math.round(p.y / store.zoom) }
  if (showCrosshair.value) updCrosshair(e)
  // 拖拽平移
  if (dragState.value.active && dragState.value.type === "pan") {
    const dx = e.clientX - dragState.value.startX; const dy = e.clientY - dragState.value.startY
    store.setPan(store.panX + dx, store.panY + dy)
    dragState.value.startX = e.clientX; dragState.value.startY = e.clientY; return
  }
  // 拖拽移动标注
  if (dragState.value.active && dragState.value.type === "move" && dragState.value.ann) {
    const c = canvasRef.value; if (!c) return; const r = c.getBoundingClientRect()
    const dx = (e.clientX - dragState.value.startX) / (cw.value * store.zoom)
    const dy = (e.clientY - dragState.value.startY) / (ch.value * store.zoom)
    const o = dragState.value.orig
    if (dragState.value.ann.type === "AxisAlignedBox") {
      dragState.value.ann.x1 = Math.max(0, Math.min(1, o.x1 + dx))
      dragState.value.ann.y1 = Math.max(0, Math.min(1, o.y1 + dy))
      dragState.value.ann.x2 = Math.max(0, Math.min(1, o.x2 + dx))
      dragState.value.ann.y2 = Math.max(0, Math.min(1, o.y2 + dy))
    }
    return
  }
  // 拖拽调整大小（手柄）
  if (dragState.value.active && dragState.value.type.startsWith("resize-") && dragState.value.ann) {
    const c = canvasRef.value; if (!c) return
    const dx = (e.clientX - dragState.value.startX) / (cw.value * store.zoom)
    const dy = (e.clientY - dragState.value.startY) / (ch.value * store.zoom)
    const o = dragState.value.orig; const ann = dragState.value.ann; const h = dragState.value.handle
    if (ann.type === "AxisAlignedBox") {
      if (h.includes("l")) ann.x1 = Math.max(0, Math.min(o.x2 - 0.01, o.x1 + dx))
      if (h.includes("r")) ann.x2 = Math.min(1, Math.max(o.x1 + 0.01, o.x2 + dx))
      if (h.includes("t")) ann.y1 = Math.max(0, Math.min(o.y2 - 0.01, o.y1 + dy))
      if (h.includes("b")) ann.y2 = Math.min(1, Math.max(o.y1 + 0.01, o.y2 + dy))
    }
    return
  }
  // 绘制矩形中
  if (drawing.value && currentTool.value === "box") {
    const p = mouseToImgPx(e); if (!p) return
    drawEnd.value = { x: p.x / store.zoom, y: p.y / store.zoom }
    updCrosshair(e); return
  }
}

function onMouseUp(_e: MouseEvent) {
  // 完成矩形绘制
  if (drawing.value && drawEnd.value) {
    drawing.value = false; showCrosshair.value = false
    const x1 = drawStart.value.x; const y1 = drawStart.value.y
    const x2 = drawEnd.value.x; const y2 = drawEnd.value.y
    const w = Math.abs(x2 - x1); const h = Math.abs(y2 - y1)
    if (w > 5 && h > 5) {
      store.annotations.push({
        id: crypto.randomUUID(), type: "AxisAlignedBox",
        class_id: selectedClassId.value || 0,
        x1: Math.min(x1, x2) / cw.value, y1: Math.min(y1, y2) / ch.value,
        x2: Math.max(x1, x2) / cw.value, y2: Math.max(y1, y2) / ch.value,
      })
    }
    drawEnd.value = null; return
  }
  if (dragState.value.active) dragState.value.active = false
}

function onWheel(e: WheelEvent) {
  const d = e.deltaY > 0 ? -0.08 : 0.08
  store.setZoom(Math.max(0.1, Math.min(10, store.zoom + d)))
}

function onDblClick(_e: MouseEvent) {}

// ===== 标注选中/拖拽 =====
function onAnnMouseDown(e: MouseEvent, ann: any) {
  if (currentTool.value === "select" || currentTool.value === "pan" || currentTool.value === "box") {
    const t = (e.target as HTMLElement)
    const handle = t.getAttribute("data-handle")
    if (handle && handle.startsWith("resize-")) {
      store.selectedAnnotationId = ann.id
      dragState.value = { active: true, type: "resize", ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle }
      return
    }
    store.selectedAnnotationId = store.selectedAnnotationId === ann.id ? null : ann.id
    if (store.selectedAnnotationId === ann.id) {
      dragState.value = { active: true, type: "move", ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle: "" }
    }
  }
}

function boxHandles(ann: any) {
  const x1 = ann.x1 * cw.value; const y1 = ann.y1 * ch.value; const x2 = ann.x2 * cw.value; const y2 = ann.y2 * ch.value
  return [
    { key: "resize-tl", x: x1, y: y1 }, { key: "resize-tr", x: x2, y: y1 },
    { key: "resize-bl", x: x1, y: y2 }, { key: "resize-br", x: x2, y: y2 },
    { key: "resize-l", x: x1, y: (y1 + y2) / 2 }, { key: "resize-r", x: x2, y: (y1 + y2) / 2 },
    { key: "resize-t", x: (x1 + x2) / 2, y: y1 }, { key: "resize-b", x: (x1 + x2) / 2, y: y2 },
  ]
}

// ===== 标注操作 =====
function removeAnn(id: string) { store.annotations = store.annotations.filter(a => a.id !== id); if (store.selectedAnnotationId === id) store.selectedAnnotationId = null }

// ===== 图片导航 =====
async function loadImg(imageId: number) {
  imgUrl.value = ""; store.selectedAnnotationId = null
  const idx = store.images.findIndex(i => i.id === imageId)
  if (idx >= 0) store.currentImageIndex = idx
  try {
    const r = await AnnotationAPI.getPresignedUrl(imageId)
    imgUrl.value = r.data?.data?.url || ""
    const ar = await AnnotationAPI.getAnnotations(store.taskId, imageId)
    store.annotations = ar.data?.data || []
  } catch { imgUrl.value = "" }
}
function goToImage(idx: number) { if (idx >= 0 && idx < store.images.length) loadImg(store.images[idx].id) }
function prevImg() { if (store.currentImageIndex > 0) goToImage(store.currentImageIndex - 1) }
function nextImg() { if (store.currentImageIndex < store.images.length - 1) goToImage(store.currentImageIndex + 1) }

async function saveAnn() {
  const img = store.currentImage; if (!img) return
  store.saving = true
  try {
    await AnnotationAPI.saveAnnotations(img.id, {
      task_id: store.taskId, image_id: img.id, annotation_data: store.annotations,
    })
    img.status = store.annotations.length > 0 ? "annotated" : "unannotated"
    ElMessage.success("保存成功")
  } finally { store.saving = false }
}

function setTool(t: ToolName) { currentTool.value = t; store.setTool(t) }
function handleBack() { router.push("/annotation/task") }
function fmtTime(t?: string) { if (!t) return ""; const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}` }

// ===== 键盘 =====
const keyToolMap: Record<string, ToolName> = { "1": "select", "s": "select", "2": "box", "b": "box", "3": "rotated_box", "r": "rotated_box", "4": "polygon", "p": "polygon", "5": "keypoint", "k": "keypoint", "6": "ocr", "o": "ocr", "7": "classification", "c": "classification" }
function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
  const k = e.key.toLowerCase()
  if (e.ctrlKey && k === "s") { e.preventDefault(); saveAnn(); return }
  if ((k === "delete" || k === "backspace") && store.selectedAnnotationId) { removeAnn(store.selectedAnnotationId); return }
  if (k === "arrowleft" || k === "a") { prevImg(); return }
  if (k === "arrowright" || k === "d") { nextImg(); return }
  if (k === "escape") { drawing.value = false; showCrosshair.value = false; store.selectedAnnotationId = null; return }
  const t = keyToolMap[k]; if (t && displayTools.value.some(d => d.name === t)) setTool(t)
}

// ===== 生命周期 =====
onMounted(async () => {
  const tid = Number(route.params.id || route.query.id || 0); if (!tid) return
  store.loading = true
  try {
    const dr = await AnnotationAPI.getTaskDetail(tid)
    const t = dr.data?.data; if (!t) return
    task.value = t; taskType.value = t.task_type || "detection"
    taskClasses.value = t.classes || []
    currentTool.value = (taskToolMap[t.task_type]?.[0]?.name as ToolName) || "box"
    store.setTool(currentTool.value); store.taskId = tid
    if (taskClasses.value.length > 0) selectedClassId.value = taskClasses.value[0].id
    const ir = await AnnotationAPI.getImages(t.dataset_id); const imgs = ir.data?.data || []
    store.images = imgs
    if (imgs.length > 0) await loadImg(imgs[0].id)
  } catch (e: any) { ElMessage.error("加载失败: " + (e?.msg || e?.message || ""))
  } finally { store.loading = false }
  document.addEventListener("keydown", onKey)
})
onBeforeUnmount(() => document.removeEventListener("keydown", onKey))
</script>

<style scoped>
.ann-page { display:flex; flex-direction:column; width:100%; height:100%; background:#f5f7fa; overflow:hidden; }
.ann-header { display:flex; align-items:center; padding:6px 12px; background:#fff; border-bottom:1px solid #e4e7ed; gap:10px; flex-shrink:0; height:44px; }
.ann-title { display:flex; align-items:center; gap:6px; flex:1; }
.task-name { font-size:13px; font-weight:600; color:#303133; }
.header-right { display:flex; align-items:center; gap:8px; }
.progress-text { font-size:11px; color:#909399; white-space:nowrap; font-variant-numeric:tabular-nums; }
.ann-body { display:flex; flex:1; overflow:hidden; }
.ann-leftbar { width:52px; background:#fff; border-right:1px solid #e4e7ed; display:flex; flex-direction:column; align-items:center; padding:8px 2px; gap:2px; flex-shrink:0; }
.tool-list { display:flex; flex-direction:column; align-items:center; gap:1px; }
.tool-btn { display:flex; flex-direction:column; align-items:center; justify-content:center; width:44px; height:44px; border-radius:6px; cursor:pointer; color:#606266; transition:all 0.12s; border:1px solid transparent; }
.tool-btn:hover { background:#f0f2f5; }
.tool-btn.active { background:#ecf5ff; border-color:#409eff; color:#409eff; }
.tool-label { font-size:9px; margin-top:1px; line-height:1; }
.ann-canvas-area { flex:1; overflow:hidden; position:relative; background:#f0f2f5; }
.canvas-container { width:100%; height:100%; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; cursor:crosshair; }
.crosshair { position:absolute; pointer-events:none; z-index:20; }
.crosshair-x { left:0; height:1px; background:rgba(59,130,246,0.5); width:100%; }
.crosshair-y { top:0; width:1px; background:rgba(59,130,246,0.5); height:100%; }
.ann-svg { position:absolute; top:50%; left:50%; pointer-events:none; }
.ann-svg rect, .ann-svg g { pointer-events:all; cursor:pointer; }
.ann-svg .handle { cursor:pointer; pointer-events:all; }
.ann-svg .ann-label { pointer-events:none; }
.no-image { color:#909399; font-size:13px; }
.ann-rightbar { width:240px; background:#fff; border-left:1px solid #e4e7ed; flex-shrink:0; display:flex; flex-direction:column; overflow:hidden; }
.panel { padding:6px 10px; display:flex; flex-direction:column; gap:0; flex:1; min-height:0; }
.panel-section { display:flex; flex-direction:column; gap:2px; flex:1; min-height:0; overflow:hidden; }
.section-title-row { display:flex; align-items:center; gap:4px; padding:2px 0; flex-shrink:0; }
.section-title { font-size:11px; font-weight:600; color:#909399; text-transform:uppercase; flex:1; letter-spacing:0.03em; }
.count-chip { font-size:10px; color:#909399; background:#f0f2f5; border:1px solid #e4e7ed; padding:0 5px; border-radius:999px; font-variant-numeric:tabular-nums; }
.divider { height:1px; background:#e4e7ed; margin:2px 0; flex-shrink:0; }
.scroll-area { flex:1; overflow-y:auto; min-height:0; display:flex; flex-direction:column; gap:1px; }
.image-item { display:flex; align-items:center; gap:5px; padding:4px 6px; border-radius:4px; cursor:pointer; border-left:3px solid transparent; }
.image-item:hover { background:#f0f2f5; }
.image-item.active { background:#ecf5ff; border-left-color:#409eff; }
.dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.dot-done { background:#67c23a; }
.dot-pending { background:#f56c6c; }
.img-info { display:flex; flex-direction:column; overflow:hidden; flex:1; }
.img-name { font-size:11px; color:#303133; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.img-meta { font-size:9px; color:#909399; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.class-item, .ann-item { display:flex; align-items:center; gap:5px; padding:3px 6px; border-radius:4px; cursor:pointer; }
.class-item:hover, .ann-item:hover { background:#f0f2f5; }
.class-item.active, .ann-item.active { background:#ecf5ff; }
.dot-color { width:10px; height:10px; border-radius:2px; flex-shrink:0; }
.empty-hint { font-size:11px; color:#c0c4cc; text-align:center; padding:8px 0; }
.text-xs { font-size:11px; }
.text-gray-400 { color:#909399; }
.font-mono { font-family:monospace; }
.flex-1 { flex:1; }
.ann-footer { height:36px; background:#fff; border-top:1px solid #e4e7ed; display:flex; align-items:center; padding:0 10px; gap:6px; flex-shrink:0; }
.hint { flex:1; font-size:11px; color:#909399; }
.sep { width:1px; height:14px; background:#e4e7ed; flex-shrink:0; }
.nav-text { font-size:11px; color:#606266; font-family:monospace; min-width:50px; text-align:center; font-variant-numeric:tabular-nums; }
</style>