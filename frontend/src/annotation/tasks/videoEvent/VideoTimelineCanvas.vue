<template>
  <div class="video-timeline-canvas">
    <div ref="trackRef" class="vtc-track" @mousedown="onTrackMouseDown">
      <div v-for="seg in props.segments" :key="seg.id" class="vtc-region-wrap" :style="pos(seg.start, seg.end)">
        <div
          class="vtc-region"
          :class="{ active: seg.id === props.selectedId }"
          :style="{ background: colorOf(seg) }"
          @mousedown.stop="onRegionMouseDown($event, seg, 'move')"
        >
          <span class="vtc-region-label">{{ clsName(seg) }}</span>
          <span
            class="vtc-handle vtc-handle--left"
            @mousedown.stop="onRegionMouseDown($event, seg, 'left')"
          />
          <span
            class="vtc-handle vtc-handle--right"
            @mousedown.stop="onRegionMouseDown($event, seg, 'right')"
          />
        </div>
      </div>
      <div v-if="previewRange" class="vtc-region vtc-preview" :style="pos(previewRange.start, previewRange.end)" />
      <div v-if="draftRange" class="vtc-region vtc-draft" :style="pos(draftRange.start, draftRange.end)" />
    </div>
    <div class="vtc-scale" :class="{ 'is-empty': !duration }">
      <span class="vtc-scale-item">{{ formatTime(0) }}</span>
      <span v-if="duration > 0" class="vtc-scale-item">{{ formatTime(duration) }}</span>
    </div>
    <div v-if="!duration" class="vtc-empty">
      <el-empty description="视频时长未知，无法标注" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import type { VideoSegment } from "../../../api/module_annotation/videoEvent";
import { clampVideoRange, segmentToRange, type VideoRange } from "./useVideoEventTool";

/** 已创建区间（由用户拖选产生，尚未落入外部 segments）。 */
export interface CreatedRegion extends VideoRange {
  id: string;
}

/** 已更新/移除的区间（经用户拖拽调整/删除）。 */
export interface ChangedRegion extends VideoRange {
  id: string;
}

const props = withDefaults(
  defineProps<{
    /** 视频总时长（秒），用于时间轴 `0..duration` 刻度与拖选钳制。 */
    duration: number;
    /** 外部视频事件片段（映射为区间高亮）。 */
    segments?: VideoSegment[];
    /** 事件类别列表（供默认取色）。 */
    classes?: any[];
    /** 当前选中片段 id（高亮描边）。 */
    selectedId?: string;
    /** 片段颜色函数：入参 `(segment, classes)`，返回 CSS 颜色。缺省用配色表。 */
    colorFor?: (segment: VideoSegment, classes: any[]) => string;
  }>(),
  {
    segments: () => [],
    classes: () => [],
    selectedId: "",
    colorFor: undefined,
  }
);

const emit = defineEmits<{
  /** 用户拖选生成新区间（尚未落入外部 segments）。 */
  (e: "createRegion", region: CreatedRegion): void;
  /** 用户拖拽调整已有区间。 */
  (e: "updateRegion", region: ChangedRegion): void;
  /** 用户删除区间（可经面板触发，画布据此清除预览）。 */
  (e: "removeRegion", region: ChangedRegion): void;
  /** 点击已有区间（选中）。 */
  (e: "regionClick", region: ChangedRegion): void;
}>();

const trackRef = ref<HTMLElement | null>(null);

/** 缺省取色板：使用 Element 语义色变量，避免写死主题色。 */
const PALETTE = [
  "var(--el-color-primary)",
  "var(--el-color-success)",
  "var(--el-color-warning)",
  "var(--el-color-danger)",
  "var(--el-color-info)",
];

function colorOf(segment: VideoSegment): string {
  if (props.colorFor) return props.colorFor(segment, props.classes);
  return PALETTE[Math.abs(segment.label_id) % PALETTE.length];
}

function clsName(segment: VideoSegment): string {
  return props.classes.find((c) => c.id === segment.label_id)?.name ?? `#${segment.label_id}`;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** 区间换算为相对轨道的百分比位置（左右偏移+宽度）。 */
function pos(start: number, end: number): { left: string; width: string } {
  const d = props.duration > 0 ? props.duration : 1;
  const left = Math.max(0, Math.min(100, (start / d) * 100));
  const width = Math.max(0, Math.min(100 - left, ((end - start) / d) * 100));
  return { left: `${left}%`, width: `${width}%` };
}

/** 将鼠标 clientX 换算为视频秒（基于轨道宽度与总时长），轨道未就绪/时长为 0 时返回 null。 */
function clientToSeconds(clientX: number): number | null {
  const track = trackRef.value;
  if (!track || props.duration <= 0) return null;
  const rect = track.getBoundingClientRect();
  if (rect.width <= 0) return null;
  const ratio = (clientX - rect.left) / rect.width;
  return ratio * props.duration;
}

/** 拖选「生成新区间」状态。 */
let selectActive = false;
let selectStartTime = 0;
let selectStartX = 0;
const previewRange = ref<VideoRange | null>(null);

/** 拖拽「移动/缩放已有区间」状态。 */
interface RegionDragState {
  id: string;
  mode: "move" | "left" | "right";
  orig: VideoRange;
  startX: number;
}
let regionDrag: RegionDragState | null = null;
const draftRange = ref<VideoRange | null>(null);

/** 判定「点击」与「拖选」的最小像素距离。 */
const CLICK_DISTANCE = 5;

function onTrackMouseDown(e: MouseEvent) {
  const t = clientToSeconds(e.clientX);
  if (t == null) return;
  selectActive = true;
  selectStartTime = t;
  selectStartX = e.clientX;
  previewRange.value = null;
  window.addEventListener("mousemove", onSelectMove);
  window.addEventListener("mouseup", onSelectUp);
}

function onSelectMove(e: MouseEvent) {
  if (!selectActive) return;
  const t = clientToSeconds(e.clientX);
  if (t == null) return;
  previewRange.value = clampVideoRange(selectStartTime, t, props.duration);
}

function onSelectUp(e: MouseEvent) {
  if (!selectActive) return;
  selectActive = false;
  window.removeEventListener("mousemove", onSelectMove);
  window.removeEventListener("mouseup", onSelectUp);
  const t = clientToSeconds(e.clientX);
  const range = previewRange.value;
  previewRange.value = null;
  if (t == null || !range) return;
  // 仅在真正拖选（非点击）且长度 > 0 时生成区间，避免点击产生零宽事件。
  if (range.end - range.start > 0 && Math.abs(e.clientX - selectStartX) > CLICK_DISTANCE) {
    emit("createRegion", { id: crypto.randomUUID(), start: range.start, end: range.end });
  }
}

function onRegionMouseDown(e: MouseEvent, seg: VideoSegment, mode: RegionDragState["mode"]) {
  const t = clientToSeconds(e.clientX);
  if (t == null) return;
  // 点击已有区间即选中。
  emit("regionClick", { id: seg.id, ...segmentToRange(seg) });
  regionDrag = { id: seg.id, mode, orig: segmentToRange(seg), startX: e.clientX };
  draftRange.value = { ...segmentToRange(seg) };
  window.addEventListener("mousemove", onRegionMove);
  window.addEventListener("mouseup", onRegionUp);
}

function onRegionMove(e: MouseEvent) {
  if (!regionDrag) return;
  const track = trackRef.value;
  if (!track || props.duration <= 0) return;
  const rect = track.getBoundingClientRect();
  const delta = ((e.clientX - regionDrag.startX) / rect.width) * props.duration;
  const { orig, mode } = regionDrag;
  if (mode === "move") {
    const moved = clampVideoRange(orig.start + delta, orig.end + delta, props.duration);
    draftRange.value = moved;
    return;
  }
  // 缩放左右端点：单侧钳制，保证区间长度 > 0。
  const MIN_LEN = 0.05;
  if (mode === "left") {
    const start = Math.max(0, Math.min(orig.end - MIN_LEN, orig.start + delta));
    draftRange.value = { start, end: orig.end };
  } else {
    const end = Math.min(props.duration, Math.max(orig.start + MIN_LEN, orig.end + delta));
    draftRange.value = { start: orig.start, end };
  }
}

function onRegionUp() {
  if (!regionDrag) return;
  const { id, orig } = regionDrag;
  const final = draftRange.value;
  regionDrag = null;
  draftRange.value = null;
  window.removeEventListener("mousemove", onRegionMove);
  window.removeEventListener("mouseup", onRegionUp);
  if (
    final &&
    final.end - final.start > 0 &&
    (Math.abs(final.start - orig.start) > 0.001 || Math.abs(final.end - orig.end) > 0.001)
  ) {
    emit("updateRegion", { id, start: final.start, end: final.end });
  }
}

/** 卸载时清理拖选/拖拽监听与临时状态（避免跨实例残留）。 */
function cleanup() {
  selectActive = false;
  previewRange.value = null;
  regionDrag = null;
  draftRange.value = null;
  window.removeEventListener("mousemove", onSelectMove);
  window.removeEventListener("mouseup", onSelectUp);
  window.removeEventListener("mousemove", onRegionMove);
  window.removeEventListener("mouseup", onRegionUp);
}

onMounted(cleanup);
onUnmounted(cleanup);
</script>

<style scoped>
.video-timeline-canvas {
  display: flex;
  flex-direction: column;
  gap: var(--el-margin-base);
  height: 100%;
  position: relative;
}

.vtc-track {
  position: relative;
  width: 100%;
  height: 44px;
  flex: none;
  cursor: crosshair;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}

.vtc-region-wrap {
  position: absolute;
  top: 0;
  height: 100%;
}

.vtc-region {
  position: absolute;
  top: 0;
  height: 100%;
  opacity: 0.8;
  cursor: grab;
}

.vtc-region.active {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}

.vtc-region-label {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: calc(100% - 8px);
  pointer-events: none;
}

.vtc-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
}

.vtc-handle--left {
  left: 0;
}

.vtc-handle--right {
  right: 0;
}

.vtc-preview {
  background: var(--el-color-primary);
  opacity: 0.3;
  pointer-events: none;
  cursor: crosshair;
}

.vtc-draft {
  background: var(--el-color-warning);
  opacity: 0.45;
  pointer-events: none;
  cursor: grabbing;
}

.vtc-scale {
  display: flex;
  justify-content: space-between;
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-base);
  padding: 0 2px;
}

.vtc-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
