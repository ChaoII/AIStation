<template>
  <div class="roi-editor">
    <div ref="wrapRef" class="roi-stage">
      <LivePlayer
        ref="playerRef"
        :stream-id="streamId"
        stream-type="flv"
        @load="onPlayerLoad"
        @error="onPlayerError"
      >
        <template #overlay>
          <svg
            class="roi-svg"
            :viewBox="`0 0 ${stage.w} ${stage.h}`"
            @click="onStageClick"
            @dblclick.prevent="closePolygon"
          >
            <polygon
              v-if="points.length >= 2"
              :points="polygonPoints"
              fill="rgba(64,158,255,0.25)"
              stroke="#409eff"
              stroke-width="2"
            />
            <circle
              v-for="(p, i) in displayPoints"
              :key="i"
              :cx="p[0]"
              :cy="p[1]"
              r="4"
              fill="#fff"
              stroke="#409eff"
              stroke-width="2"
            />
          </svg>
        </template>
      </LivePlayer>
      <div v-if="!streamId" class="roi-hint">该点位无可用流，无法绘制 ROI</div>
    </div>
    <div class="roi-actions">
      <span class="roi-count">已选 {{ points.length }} 个点</span>
      <el-button size="small" @click="undoPoint">撤销</el-button>
      <el-button size="small" @click="clearPoints">清空</el-button>
      <el-button size="small" type="primary" @click="closePolygon">闭合</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onBeforeUnmount, onMounted, nextTick } from "vue";
import LivePlayer from "./LivePlayer.vue";

const props = defineProps<{
  modelValue: number[][] | null;
  streamId?: string;
}>();

const emit = defineEmits<{ (e: "update:modelValue", val: number[][] | null): void }>();

const wrapRef = ref<HTMLDivElement | null>(null);
const playerRef = ref<any>(null);
const stage = reactive({ w: 640, h: 360 });
const videoSize = reactive({ w: 0, h: 0 });
const points = ref<number[][]>(toPoints(props.modelValue));

function toPoints(val: number[][] | null): number[][] {
  return Array.isArray(val) ? val.map((p) => [Number(p[0]), Number(p[1])]) : [];
}

const contentRect = computed(() => {
  const { w, h } = stage;
  const vw = videoSize.w || 16;
  const vh = videoSize.h || 9;
  const scale = Math.min(w / vw, h / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  return { x: (w - dw) / 2, y: (h - dh) / 2, w: dw, h: dh };
});

const displayPoints = computed(() =>
  points.value.map(([nx, ny]) => [
    contentRect.value.x + nx * contentRect.value.w,
    contentRect.value.y + ny * contentRect.value.h,
  ])
);

const polygonPoints = computed(() => displayPoints.value.map(([x, y]) => `${x},${y}`).join(" "));

function measureStage() {
  const el = wrapRef.value;
  if (!el) return;
  const video = playerRef.value?.getVideoElement?.();
  if (video?.videoWidth) {
    videoSize.w = video.videoWidth;
    videoSize.h = video.videoHeight;
  }
  stage.w = el.clientWidth || 640;
  stage.h = el.clientHeight || 360;
}

function onPlayerLoad() {
  nextTick(measureStage);
}

function onPlayerError() {
  /* 保留画布，允许在无流时仍显示已有 ROI */
}

function onStageClick(e: MouseEvent) {
  const video = playerRef.value?.getVideoElement?.();
  const box = video?.getBoundingClientRect();
  if (!box) return;
  const nx = (e.clientX - box.left - contentRect.value.x) / contentRect.value.w;
  const ny = (e.clientY - box.top - contentRect.value.y) / contentRect.value.h;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return;
  points.value = [...points.value, [round4(nx), round4(ny)]];
  emit("update:modelValue", points.value);
}

function undoPoint() {
  points.value = points.value.slice(0, -1);
  emit("update:modelValue", points.value.length ? points.value : null);
}

function clearPoints() {
  points.value = [];
  emit("update:modelValue", null);
}

function closePolygon() {
  if (points.value.length < 3) return;
  emit("update:modelValue", points.value);
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}

// 外部（编辑回填）更新时同步内部点集，避免覆盖用户正在编辑的内容
watch(
  () => props.modelValue,
  (val) => {
    if (JSON.stringify(toPoints(val)) !== JSON.stringify(points.value)) {
      points.value = toPoints(val);
    }
  }
);

let ro: ResizeObserver | null = null;
onMounted(() => {
  nextTick(measureStage);
  if (wrapRef.value) {
    ro = new ResizeObserver(() => measureStage());
    ro.observe(wrapRef.value);
  }
});
onBeforeUnmount(() => {
  if (ro) ro.disconnect();
});
</script>

<style scoped>
.roi-editor {
  width: 100%;
}

.roi-stage {
  position: relative;
  width: 100%;
  height: 320px;
  overflow: hidden;
  background: #000;
  border-radius: 6px;
}

.roi-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}

.roi-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #ccc;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.5);
}

.roi-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.roi-count {
  margin-right: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
