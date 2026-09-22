<template>
  <div class="audio-timeline-canvas">
    <div ref="waveformRef" class="audio-timeline-canvas__waveform" />
    <div class="audio-timeline-canvas__controls">
      <el-button
        size="default"
        :icon="playing ? VideoPause : VideoPlay"
        circle
        @click="togglePlay"
      />
      <span class="audio-timeline-canvas__time">
        {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { VideoPlay, VideoPause } from "@element-plus/icons-vue";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { type Region } from "wavesurfer.js/dist/plugins/regions.js";
import type { AudioSegment } from "../../../api/module_annotation/audio";
import { hasSegmentWithId, type AudioRange } from "./useAudioEventTool";

/** 已创建区间（由用户拖选产生，尚未落入外部 segments）。 */
export interface CreatedRegion extends AudioRange {
  id: string;
}

/** 已更新/移除的区间（经用户拖拽调整/删除）。 */
export interface ChangedRegion extends AudioRange {
  id: string;
}

const props = withDefaults(
  defineProps<{
    /** 音频播放地址（presigned play_url），加载后渲染波形（可只读播放）。 */
    url: string;
    /** 外部音频片段（映射为 regions 高亮）。 */
    segments?: AudioSegment[];
    /** 事件类别列表（供默认取色）。 */
    classes?: any[];
    /** 当前选中片段 id（高亮描边）。 */
    selectedId?: string;
    /** 片段颜色函数：入参 `(segment, classes)`，返回 CSS 颜色。缺省用配色表。 */
    colorFor?: (segment: AudioSegment, classes: any[]) => string;
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
  /** 用户删除已有区间（拖动到外部/双击等）。 */
  (e: "removeRegion", region: ChangedRegion): void;
  /** 点击已有区间（选中）。 */
  (e: "regionClick", region: ChangedRegion): void;
  /** 播放时间实时回调（当前秒）。 */
  (e: "timeupdate", seconds: number): void;
  /** 音频解码完成（总时长秒）。 */
  (e: "ready", duration: number): void;
}>();

const waveformRef = ref<HTMLElement | null>(null);
let ws: WaveSurfer | null = null;
let regions: RegionsPlugin | null = null;
let cleanup: (() => void) | null = null;
/** 拖选监听的解绑函数（由 `enableDragSelection` 返回），组件卸载时调用。 */
let dragSelectionCleanup: (() => void) | null = null;

/** segment.id → region 映射，用于外部 segments 与 regions 高亮同步。 */
const regionBySegmentId = new Map<string, Region>();

const playing = ref(false);
const currentTime = ref(0);
const duration = ref(0);

/** 缺省取色板：使用 Element 语义色变量，避免写死主题色。 */
const PALETTE = [
  "var(--el-color-primary)",
  "var(--el-color-success)",
  "var(--el-color-warning)",
  "var(--el-color-danger)",
  "var(--el-color-info)",
];

function colorOf(segment: AudioSegment): string {
  if (props.colorFor) return props.colorFor(segment, props.classes);
  return PALETTE[Math.abs(segment.label_id) % PALETTE.length];
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** 创建或更新一个与 segment 对应的 region，并保持 id 一致。 */
function upsertRegion(segment: AudioSegment) {
  if (!regions) return;
  const existing = regionBySegmentId.get(segment.id);
  const params = {
    id: segment.id,
    start: segment.start,
    end: segment.end,
    color: colorOf(segment),
    drag: true,
    resize: true,
  };
  if (existing) {
    if (
      existing.start !== segment.start ||
      existing.end !== segment.end ||
      existing.color !== params.color
    ) {
      existing.setOptions({ start: segment.start, end: segment.end, color: params.color });
    }
  } else {
    const region = regions.addRegion(params);
    regionBySegmentId.set(segment.id, region);
  }
}

/** 将外部 segments 同步到 regions（新增/更新/删除）。 */
function syncRegions(segments: AudioSegment[]) {
  const wanted = new Set(segments.map((s) => s.id));
  for (const [id, region] of regionBySegmentId) {
    if (!wanted.has(id)) {
      region.remove();
      regionBySegmentId.delete(id);
    }
  }
  for (const seg of segments) upsertRegion(seg);
}

function togglePlay() {
  if (!ws) return;
  if (playing.value) ws.pause();
  else ws.play();
}

async function load() {
  if (!ws || !waveformRef.value) return;
  regionBySegmentId.clear();
  ws.load(props.url);
}

watch(
  () => props.url,
  () => load()
);

watch(
  () => [props.segments, props.selectedId] as const,
  () => {
    if (props.segments) syncRegions(props.segments);
  },
  { deep: true }
);

onMounted(() => {
  if (!waveformRef.value) return;
  ws = WaveSurfer.create({
    container: waveformRef.value,
    height: 96,
    waveColor: "var(--el-color-primary-light-7)",
    progressColor: "var(--el-color-primary)",
    cursorColor: "var(--el-color-primary)",
    url: props.url,
  });
  regions = ws.registerPlugin(RegionsPlugin.create());
  dragSelectionCleanup = regions.enableDragSelection({
    drag: false,
    resize: false,
    color: "var(--el-color-primary-light-5)",
  });
  const subs: Array<() => void> = [];
  subs.push(
    ws.on("error", () => {
      ElMessage.error("音频波形加载失败，请检查音频地址或网络后重试");
    })
  );
  subs.push(
    ws.on("ready", (dur) => {
      duration.value = dur;
      emit("ready", dur);
      if (props.segments) syncRegions(props.segments);
    })
  );
  subs.push(
    ws.on("play", () => (playing.value = true)),
    ws.on("pause", () => (playing.value = false)),
    ws.on("finish", () => (playing.value = false)),
    ws.on("timeupdate", (t) => {
      currentTime.value = t;
      emit("timeupdate", t);
    })
  );
  subs.push(
    regions.on("region-created", (region) => {
      // 若 region id 已存在于外部 segments，说明是 addRegion 同步产生，应保留且不触发 createRegion，
      // 否则会因「回流 → addRegion → 再次 region-created」造成虚假 createRegion 与重复删除。
      if (hasSegmentWithId(props.segments, region.id)) return;
      const created = { id: region.id, start: region.start, end: region.end };
      // 仅对拖选产生的新 region 立即移除，交由父组件生成对应 AudioSegment 后经 props 重建。
      region.remove();
      emit("createRegion", created);
    }),
    regions.on("region-updated", (region) => {
      const seg = (props.segments ?? []).find((s) => s.id === region.id);
      if (seg) emit("updateRegion", { id: region.id, start: region.start, end: region.end });
    }),
    regions.on("region-removed", (region) => {
      const seg = (props.segments ?? []).find((s) => s.id === region.id);
      if (seg) {
        regionBySegmentId.delete(region.id);
        emit("removeRegion", { id: region.id, start: region.start, end: region.end });
      }
    }),
    regions.on("region-clicked", (region) => {
      emit("regionClick", { id: region.id, start: region.start, end: region.end });
    })
  );

  cleanup = () => subs.forEach((un) => un());
});

onUnmounted(() => {
  cleanup?.();
  cleanup = null;
  dragSelectionCleanup?.();
  dragSelectionCleanup = null;
  regionBySegmentId.clear();
  const instance = ws;
  ws = null;
  regions = null;
  void instance?.destroy();
});

/** 播放控制（供父组件/工作台调用）。 */
defineExpose({
  play: () => ws?.play(),
  pause: () => ws?.pause(),
  seek: (seconds: number) => ws?.setTime(seconds),
  setTime: (seconds: number) => ws?.setTime(seconds),
});
</script>

<style scoped>
.audio-timeline-canvas {
  display: flex;
  flex-direction: column;
  gap: var(--el-margin-base);
  height: 100%;
}

.audio-timeline-canvas__waveform {
  width: 100%;
  min-height: 96px;
}

.audio-timeline-canvas__controls {
  display: flex;
  align-items: center;
  gap: var(--el-margin-base);
}

.audio-timeline-canvas__time {
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-base);
}
</style>
