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
          <div ref="cxXRef" class="crosshair crosshair-x" v-show="showCrosshair" :style="cxStyle" />
          <div ref="cxYRef" class="crosshair crosshair-y" v-show="showCrosshair" :style="cxStyle" />
          <!-- 框预览（容器相对坐标） -->
          <div ref="boxPreviewRef" class="box-preview" v-show="drawing" />
          <img v-if="imgUrl" ref="imgRef" :src="imgUrl" :style="imgStyle" class="ann-img" draggable="false" @load="onImgLoad" @error="imgUrl = ''" />
          <svg v-if="imgUrl" class="ann-svg" :style="svgStyle" :viewBox="`0 0 ${cw} ${ch}`">
            <!-- 已有标注 -->
            <g v-for="ann in store.annotations" :key="ann.id" :data-ann-id="ann.id" @mousedown.left.prevent="onAnnMouseDown($event, ann)">
              <template v-if="ann.type === 'AxisAlignedBox'">
                <rect :x="ann.x1 * cw" :y="ann.y1 * ch" :width="(ann.x2 - ann.x1) * cw" :height="(ann.y2 - ann.y1) * ch"
                  :stroke="clsColor(ann.class_id)" :stroke-width="store.selectedAnnotationId === ann.id ? 2 : 1.5"
                  :fill="store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'none'"
                  vector-effect="non-scaling-stroke" />
                <g v-if="store.selectedAnnotationId === ann.id">
                  <rect v-for="h in boxHandles(ann)" :key="h.key" :x="h.x - 4" :y="h.y - 4" width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5" :data-handle="h.key" class="handle" vector-effect="non-scaling-stroke" />
                </g>
                <g class="ann-label">
                  <rect :x="ann.x1 * cw" :y="ann.y1 * ch - (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H)" :width="labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)" :height="labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H" :fill="clsColor(ann.class_id)" :stroke="clsColor(ann.class_id)" stroke-width="0.5" vector-effect="non-scaling-stroke" rx="1" />
                  <text :x="ann.x1 * cw + 2" :y="ann.y1 * ch - 6" fill="#ffffff" font-weight="500" text-anchor="start" font-family="Microsoft YaHei,sans-serif" font-size="6">{{ getCls(ann.class_id)?.name }}</text>
                </g>
              </template>
            </g>
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
      <span class="text-xs text-gray-400 font-mono">Z:{{ Math.round(store.zoom * 100) }}% | cw:{{ cw }}</span>
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
const boxPreviewRef = ref<HTMLElement | null>(null)

// State
const imgUrl = ref("")
const cw = ref(1); const ch = ref(1)
const cursorX = ref(0); const cursorY = ref(0)
const showCrosshair = ref(false)
const selectedClassId = ref(0)
const currentTool = ref<ToolName>("select")
const taskType = ref("detection"); const task = ref<any>(null)
const taskClasses = ref<any[]>([])
const showClassModal = ref(false)
const clsForm = ref({ name: "", color: "#409eff" })

// ---- Constants (matching EasyLabelTauri) ----
const LABEL_TAG_H = 8

// ---- Drag state (single object, matching EasyLabelTauri pattern) ----
interface DragState {
  active: boolean
  type: "move" | "pan" | "resize-tl" | "resize-tr" | "resize-bl" | "resize-br"
       | "resize-l" | "resize-r" | "resize-t" | "resize-b" | ""
  ann: any | null
  orig: any | null     // deep-copy of annotation when drag started
  startX: number
  startY: number
  handle: string
}
const drag = ref<DragState>({
  active: false, type: "", ann: null, orig: null, startX: 0, startY: 0, handle: "",
})

// ---- 测量文字实际宽高 ----
const labelTextRects = ref(new Map<string, { w: number; h: number; y: number }>())
async function measureLabelRects() {
  await nextTick()
  await new Promise(r => setTimeout(r, 100))
  const annSvg = document.querySelector(".ann-svg")
  if (!annSvg) return
  const texts = annSvg.querySelectorAll<SVGTextElement>(".ann-label text")
  const map = new Map<string, { w: number; h: number; y: number }>()
  texts.forEach(t => {
    const annEl = t.closest<SVGGElement>("[data-ann-id]")
    if (!annEl) return
    const id = annEl.getAttribute("data-ann-id")
    if (!id) return
    const bbox = t.getBBox()
    if (bbox.width > 0 && bbox.height > 0) {
      map.set(id, { w: bbox.width, h: bbox.height, y: bbox.y })
    }
  })
  labelTextRects.value = map
  // 调试输出
  if (map.size > 0) {
    for (const [id, r] of map) {
      const ann = store.annotations.find(a => a.id === id)
      const clsName = ann ? (getCls(ann.class_id)?.name || '?') : '?'
      const calcW = labelWidthForClass(ann?.class_id || 0)
      const calcH = LABEL_TAG_H
      console.log(`[label] "${clsName}" 测量: w=${r.w.toFixed(1)} h=${r.h.toFixed(1)} y=${r.y.toFixed(1)} | 计算: w=${calcW} h=${calcH}`)
    }
  }
}

// ---- Box drawing (div overlay in container-relative coords) ----
const drawing = ref(false)
let bx = 0  // box start X (container-relative)
let by = 0  // box start Y (container-relative)
let drawStartImg = { x: 0, y: 0 }  // box start in image natural pixels

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

const cxColor = computed(() => clsColor(selectedClassId.value) || "#3b82f6")
const cxStyle = computed(() => ({ background: cxColor.value + "80" }))

const annotatedCount = computed(() => store.images.filter(i => i.status === "annotated").length)
const totalCount = computed(() => store.images.length)
const progressPct = computed(() => totalCount.value === 0 ? 0 : Math.round(annotatedCount.value / totalCount.value * 100))

// ===== 显示 =====
const dw = computed(() => cw.value * store.zoom)
const dh = computed(() => ch.value * store.zoom)

const imgStyle = computed(() => ({
  width: dw.value + "px", height: dh.value + "px",
  transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)`,
}))
const svgStyle = computed(() => ({
  width: dw.value + "px", height: dh.value + "px",
  transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)`,
}))

// ===== 坐标：鼠标 → 图像自然像素 =====
function mouseToImage(e: MouseEvent): { x: number; y: number } | null {
  const c = canvasRef.value; if (!c || !cw.value || !ch.value) return null
  const r = c.getBoundingClientRect()
  // 图像左上角在容器中的位置
  const imgL = r.width / 2 - dw.value / 2 + store.panX
  const imgT = r.height / 2 - dh.value / 2 + store.panY
  const relX = e.clientX - r.left - imgL
  const relY = e.clientY - r.top - imgT
  return {
    x: (Math.max(0, Math.min(dw.value, relX)) / dw.value) * cw.value,
    y: (Math.max(0, Math.min(dh.value, relY)) / dh.value) * ch.value,
  }
}

// ===== 图像加载 =====
function onImgLoad() {
  const el = imgRef.value; const c = canvasRef.value; if (!el || !c) return
  cw.value = el.naturalWidth; ch.value = el.naturalHeight
  const tryFit = () => {
    const r = c.getBoundingClientRect()
    if (r.width && r.height) {
      const z = Math.min(r.width / cw.value, r.height / ch.value)
      store.setZoom(Math.min(z, 3))
    }
    store.setPan(0, 0)
  }
  nextTick(tryFit)
}

// ===== Crosshair =====
function updCrosshair(e: MouseEvent) {
  const c = canvasRef.value; if (!c) return
  const r = c.getBoundingClientRect()
  if (cxXRef.value) cxXRef.value.style.top = (e.clientY - r.top) + "px"
  if (cxYRef.value) cxYRef.value.style.left = (e.clientX - r.left) + "px"
}

// ===== 类别 =====
function getCls(id: number) { return taskClasses.value.find(c => c.id === id) }
function clsColor(id: number) { return getCls(id)?.color || "#3b82f6" }
function clsCount(id: number) { return store.annotations.filter(a => a.class_id === id).length }
function textPixelWidth(text: string): number {
  let w = 0
  for (const ch of text) { w += /[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/.test(ch) ? 6 : 3 }
  return Math.round(w)
}
function labelWidthForClass(classId: number): number {
  const name = getCls(classId)?.name || ""
  return Math.max(14, textPixelWidth(name) + 6)
}
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
  try { await AnnotationAPI.updateTask(task.value.id, { classes: taskClasses.value }) } catch {}
}

// ===== Box 预览 div =====
function startBoxPreview(cx: number, cy: number) {
  const el = boxPreviewRef.value; if (!el) return
  el.style.display = "block"
  el.style.left = cx + "px"
  el.style.top = cy + "px"
  el.style.width = "0px"; el.style.height = "0px"
}
function updateBoxPreview(cx: number, cy: number) {
  const el = boxPreviewRef.value; if (!el) return
  el.style.left = Math.min(bx, cx) + "px"
  el.style.top = Math.min(by, cy) + "px"
  el.style.width = Math.abs(cx - bx) + "px"
  el.style.height = Math.abs(cy - by) + "px"
}
function removeBoxPreview() {
  const el = boxPreviewRef.value; if (!el) return
  el.style.display = "none"
  el.style.left = "0px"; el.style.top = "0px"
  el.style.width = "0px"; el.style.height = "0px"
}

// ===== 画布事件 =====
function onMouseEnter(e: MouseEvent) {
  if (currentTool.value === "box") { showCrosshair.value = true; updCrosshair(e) }
}
function onMouseLeave() {
  showCrosshair.value = false
  if (drag.value.active && drag.value.ann) {
    // restore original on leave
    if (drag.value.orig) Object.assign(drag.value.ann, drag.value.orig)
  }
  drag.value = { active: false, type: "", ann: null, orig: null, startX: 0, startY: 0, handle: "" }
  if (drawing.value) { drawing.value = false; removeBoxPreview() }
}

function onMouseDown(e: MouseEvent) {
  if (!store.currentImage) return

  // ---- Select: deselect on empty-space click ----
  if (currentTool.value === "select") {
    store.selectedAnnotationId = null
    return
  }

  // ---- Pan ----
  if (currentTool.value === "pan") {
    drag.value = { active: true, type: "pan", ann: null, orig: null, startX: e.clientX, startY: e.clientY, handle: "" }
    return
  }

  // ---- Box draw ----
  if (currentTool.value === "box") {
    if (taskClasses.value.length === 0) { ElMessage.warning("请先添加类别"); return }
    if (!selectedClassId.value && taskClasses.value.length > 0) selectedClassId.value = taskClasses.value[0].id
    const pt = mouseToImage(e); if (!pt) return
    const r = canvasRef.value?.getBoundingClientRect(); if (!r) return
    bx = e.clientX - r.left
    by = e.clientY - r.top
    drawStartImg = { x: pt.x, y: pt.y }
    startBoxPreview(bx, by)
    drawing.value = true
    showCrosshair.value = true; updCrosshair(e)
    return
  }
}

function onMouseMove(e: MouseEvent) {
  if (!store.currentImage) return
  const pt = mouseToImage(e)
  if (pt) { cursorX.value = Math.round(pt.x); cursorY.value = Math.round(pt.y) }
  if (showCrosshair.value) updCrosshair(e)

  // ---- Pan drag ----
  if (drag.value.active && drag.value.type === "pan") {
    const dx = e.clientX - drag.value.startX; const dy = e.clientY - drag.value.startY
    store.setPan(store.panX + dx, store.panY + dy)
    drag.value.startX = e.clientX; drag.value.startY = e.clientY; return
  }

  // ---- Move annotation ----
  if (drag.value.active && drag.value.type === "move" && drag.value.ann) {
    const dx = (e.clientX - drag.value.startX) / dw.value
    const dy = (e.clientY - drag.value.startY) / dh.value
    const o = drag.value.orig
    if (drag.value.ann.type === "AxisAlignedBox") {
      drag.value.ann.x1 = Math.max(0, Math.min(1, o.x1 + dx))
      drag.value.ann.y1 = Math.max(0, Math.min(1, o.y1 + dy))
      drag.value.ann.x2 = Math.max(0, Math.min(1, o.x2 + dx))
      drag.value.ann.y2 = Math.max(0, Math.min(1, o.y2 + dy))
    }
    return
  }

  // ---- Resize annotation ----
  if (drag.value.active && drag.value.type.startsWith("resize-") && drag.value.ann) {
    const dx = (e.clientX - drag.value.startX) / dw.value
    const dy = (e.clientY - drag.value.startY) / dh.value
    const o = drag.value.orig; const ann = drag.value.ann; const h = drag.value.handle
    if (ann.type === "AxisAlignedBox") {
      if (h.includes("l")) ann.x1 = Math.max(0, Math.min(o.x2 - 0.01, o.x1 + dx))
      if (h.includes("r")) ann.x2 = Math.min(1, Math.max(o.x1 + 0.01, o.x2 + dx))
      if (h.includes("t")) ann.y1 = Math.max(0, Math.min(o.y2 - 0.01, o.y1 + dy))
      if (h.includes("b")) ann.y2 = Math.min(1, Math.max(o.y1 + 0.01, o.y2 + dy))
    }
    return
  }

  // ---- Box drawing preview ----
  if (drawing.value && currentTool.value === "box") {
    const r = canvasRef.value?.getBoundingClientRect(); if (!r) return
    updateBoxPreview(e.clientX - r.left, e.clientY - r.top)
    updCrosshair(e); return
  }
}

function onMouseUp(e: MouseEvent) {
  // ---- Finish box draw ----
  if (drawing.value && currentTool.value === "box") {
    drawing.value = false; removeBoxPreview()
    const pt = mouseToImage(e); if (!pt) return
    const w = Math.abs(pt.x - drawStartImg.x); const h = Math.abs(pt.y - drawStartImg.y)
    if (w > 5 && h > 5) {
      store.annotations.push({
        id: crypto.randomUUID(), type: "AxisAlignedBox",
        class_id: selectedClassId.value || 0,
        x1: Math.min(drawStartImg.x, pt.x) / cw.value,
        y1: Math.min(drawStartImg.y, pt.y) / ch.value,
        x2: Math.max(drawStartImg.x, pt.x) / cw.value,
        y2: Math.max(drawStartImg.y, pt.y) / ch.value,
      })
    }
    return
  }

  // ---- End drag ----
  if (drag.value.active) drag.value.active = false
}

// Window-level mouseup catch (for safety when mouse leaves canvas)
function onWindowMouseUp() {
  if (drag.value.active) drag.value.active = false
  if (drawing.value) { drawing.value = false; showCrosshair.value = false; removeBoxPreview() }
}

function onWheel(e: WheelEvent) {
  const d = e.deltaY > 0 ? -0.08 : 0.08
  store.setZoom(Math.max(0.1, Math.min(10, store.zoom + d)))
}

function onDblClick(_e: MouseEvent) {}

// ===== 标注选中 / 拖拽 =====
function onAnnMouseDown(e: MouseEvent, ann: any) {
  // .prevent prevents text selection, stopPropagation prevents container handler
  e.stopPropagation()

  if (currentTool.value === "select" || currentTool.value === "pan") {
    const t = e.target as HTMLElement
    const handle = t.getAttribute("data-handle")

    // ---- Resize handle ----
    if (handle && handle.startsWith("resize-")) {
      store.selectedAnnotationId = ann.id
      drag.value = { active: true, type: handle as DragState["type"], ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle }
      return
    }

    // ---- Select annotation (always selects, does NOT toggle) ----
    store.selectedAnnotationId = ann.id

    // ---- Start move drag ----
    drag.value = { active: true, type: "move", ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle: "" }
  }
}

// ===== Handles =====
function boxHandles(ann: any) {
  const x1 = ann.x1 * cw.value; const y1 = ann.y1 * ch.value
  const x2 = ann.x2 * cw.value; const y2 = ann.y2 * ch.value
  const mx = (x1 + x2) / 2; const my = (y1 + y2) / 2
  return [
    { key: "resize-tl", x: x1, y: y1 }, { key: "resize-tr", x: x2, y: y1 },
    { key: "resize-bl", x: x1, y: y2 }, { key: "resize-br", x: x2, y: y2 },
    { key: "resize-l", x: x1, y: my },   { key: "resize-r", x: x2, y: my },
    { key: "resize-t", x: mx, y: y1 },   { key: "resize-b", x: mx, y: y2 },
  ]
}

// ===== 标注操作 =====
function removeAnn(id: string) {
  store.annotations = store.annotations.filter(a => a.id !== id)
  if (store.selectedAnnotationId === id) store.selectedAnnotationId = null
}

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
    await nextTick()
    measureLabelRects()
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
const keyToolMap: Record<string, ToolName> = {
  "1": "select", "s": "select", "2": "box", "b": "box",
  "3": "rotated_box", "r": "rotated_box", "4": "polygon", "p": "polygon",
  "5": "keypoint", "k": "keypoint", "6": "ocr", "o": "ocr",
  "7": "classification", "c": "classification",
}
function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
  const k = e.key.toLowerCase()
  if (e.ctrlKey && k === "s") { e.preventDefault(); saveAnn(); return }
  if ((k === "delete" || k === "backspace") && store.selectedAnnotationId) { removeAnn(store.selectedAnnotationId); return }
  if (k === "arrowleft" || k === "a") { prevImg(); return }
  if (k === "arrowright" || k === "d") { nextImg(); return }
  if (k === "escape") { drawing.value = false; showCrosshair.value = false; store.selectedAnnotationId = null; removeBoxPreview(); return }
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
    currentTool.value = "select"
    store.setTool("select"); store.taskId = tid
    if (taskClasses.value.length > 0) selectedClassId.value = taskClasses.value[0].id
    const ir = await AnnotationAPI.getImages(t.dataset_id); const imgs = ir.data?.data || []
    store.images = imgs
    if (imgs.length > 0) await loadImg(imgs[0].id)
  } catch (e: any) { ElMessage.error("加载失败: " + (e?.msg || e?.message || ""))
  } finally { store.loading = false }
  document.addEventListener("keydown", onKey)
  window.addEventListener("mouseup", onWindowMouseUp)
  watch(() => store.annotations.length, () => measureLabelRects())
})
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey)
  window.removeEventListener("mouseup", onWindowMouseUp)
})
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
.box-preview { position:absolute; pointer-events:none; z-index:15; border:2px dashed #3b82f6; background:rgba(59,130,246,0.06); }
.ann-svg { position:absolute; top:50%; left:50%; pointer-events:none; }
.ann-img { position:absolute; top:50%; left:50%; }
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