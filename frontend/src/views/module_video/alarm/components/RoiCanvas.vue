<template>
  <div ref="rootRef" class="roi-canvas">
    <div class="roi-canvas__toolbar">
      <el-button size="small" :disabled="disabled || !points.length" @click="undo">撤销</el-button>
      <el-button size="small" :disabled="disabled || !points.length" @click="clear">清空</el-button>
      <span class="roi-canvas__tip">{{ tip }}</span>
    </div>

    <div class="roi-canvas__stage">
      <Stage :config="{ width: stageW, height: stageH, listening: !disabled }" @click="handleClick">
        <Layer>
          <!-- 底图占位（未传快照时显示） -->
          <Rect
            :config="{
              x: frame.x,
              y: frame.y,
              width: frame.width,
              height: frame.height,
              fill: '#f5f7fa',
              listening: false,
            }"
          />
          <!-- 底图快照：等比 contain 铺满画布（letterbox） -->
          <KonvaImage
            v-if="bgImage"
            :config="{
              image: bgImage,
              x: frame.x,
              y: frame.y,
              width: frame.width,
              height: frame.height,
              listening: false,
            }"
          />
          <!-- 画面区域边框 -->
          <Rect
            :config="{
              x: frame.x,
              y: frame.y,
              width: frame.width,
              height: frame.height,
              stroke: '#dcdfe6',
              strokeWidth: 1,
              listening: false,
            }"
          />
          <!-- 多边形/折线：polygon 闭合，polyline 不闭合 -->
          <Line
            v-if="pixelPoints.length >= 4"
            :config="{
              points: pixelPoints,
              closed: mode === 'polygon',
              fill: mode === 'polygon' ? 'rgba(64, 158, 255, 0.2)' : undefined,
              stroke: '#409eff',
              strokeWidth: 2,
              listening: false,
            }"
          />
          <!-- 顶点：可拖拽 -->
          <Circle
            v-for="(p, i) in pixelVertices"
            :key="i"
            :config="{
              x: p[0],
              y: p[1],
              radius: 5,
              fill: '#409eff',
              stroke: '#fff',
              strokeWidth: 1,
              draggable: !disabled,
              name: 'vertex',
            }"
            @dragend="onVertexDragEnd(i, $event)"
          />
        </Layer>
      </Stage>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Circle, Image as KonvaImage, Layer, Line, Rect, Stage } from "vue-konva";
import type { KonvaEventObject } from "konva/lib/Node";

/** 画布模式：polygon 闭合多边形（ROI），polyline 开放折线（绊线） */
const props = withDefaults(
  defineProps<{
    mode?: "polygon" | "polyline";
    /** 底图快照 URL（可选），等比 contain 铺满画布 */
    background?: string;
    disabled?: boolean;
  }>(),
  { mode: "polygon", background: "", disabled: false }
);

/** v-model：归一化坐标点列 [[x,y],...]，0~1 */
const model = defineModel<number[][]>({ default: () => [] });

const rootRef = ref<HTMLElement | null>(null);
const stageW = ref(640);
const stageH = ref(360);
const bgImage = ref<HTMLImageElement | null>(null);

/** 内部以归一化点列存储，渲染时换算为像素 */
const points = ref<number[][]>([]);

/** 画面显示区域：底图等比 contain 后的矩形（无底图时即整块画布） */
const frame = computed(() => {
  const img = bgImage.value;
  if (!img || !img.naturalWidth || !img.naturalHeight) {
    return { x: 0, y: 0, width: stageW.value, height: stageH.value };
  }
  const scale = Math.min(stageW.value / img.naturalWidth, stageH.value / img.naturalHeight);
  const width = img.naturalWidth * scale;
  const height = img.naturalHeight * scale;
  return { x: (stageW.value - width) / 2, y: (stageH.value - height) / 2, width, height };
});

const pixelVertices = computed(() =>
  points.value.map(([x, y]) => [
    frame.value.x + x * frame.value.width,
    frame.value.y + y * frame.value.height,
  ])
);
const pixelPoints = computed(() => pixelVertices.value.flatMap(([x, y]) => [x, y]));

const tip = computed(() => {
  if (props.disabled) return "画布已禁用";
  const shape = props.mode === "polygon" ? "闭合多边形（ROI）" : "折线（绊线）";
  return `点击画面按序加点，生成${shape}；拖动顶点可调整位置`;
});

const round6 = (v: number) => Number(v.toFixed(6));
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** 规整外部传入的点列（过滤非法项、裁剪到 0~1、保留 6 位小数） */
function normalizePoints(input: number[][] | undefined | null): number[][] {
  if (!Array.isArray(input)) return [];
  return input
    .filter(
      (p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])
    )
    .map((p) => [round6(clamp01(p[0])), round6(clamp01(p[1]))] as number[]);
}

function samePoints(a: number[][], b: number[][]): boolean {
  return a.length === b.length && a.every((p, i) => p[0] === b[i][0] && p[1] === b[i][1]);
}

/** 回写 v-model */
function sync() {
  model.value = points.value.map(([x, y]) => [round6(x), round6(y)]);
}

watch(
  () => model.value,
  (val) => {
    const next = normalizePoints(val);
    if (!samePoints(points.value, next)) points.value = next;
  },
  { deep: true, immediate: true }
);

function handleClick(e: KonvaEventObject<MouseEvent>) {
  if (props.disabled) return;
  // 点击已有顶点时不新增点（由拖拽处理）
  if (e.target.name() === "vertex") return;
  const pos = e.target.getStage()?.getPointerPosition();
  if (!pos) return;
  const f = frame.value;
  const x = (pos.x - f.x) / f.width;
  const y = (pos.y - f.y) / f.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  points.value = [...points.value, [round6(x), round6(y)]];
  sync();
}

function onVertexDragEnd(index: number, e: KonvaEventObject<DragEvent>) {
  if (props.disabled) return;
  const f = frame.value;
  const x = clamp01((e.target.x() - f.x) / f.width);
  const y = clamp01((e.target.y() - f.y) / f.height);
  const next = points.value.map((p, i) => (i === index ? [round6(x), round6(y)] : p));
  points.value = next;
  sync();
}

function undo() {
  if (props.disabled) return;
  points.value = points.value.slice(0, -1);
  sync();
}

function clear() {
  if (props.disabled) return;
  points.value = [];
  sync();
}

/** 底图快照加载：加载完成后按实际宽高比做 contain 计算 */
watch(
  () => props.background,
  (url) => {
    if (!url) {
      bgImage.value = null;
      return;
    }
    const img = new window.Image();
    img.onload = () => {
      bgImage.value = img;
    };
    img.onerror = () => {
      bgImage.value = null;
    };
    img.src = url;
  },
  { immediate: true }
);

// 容器尺寸自适应：保持 16:9 画布，底图按 contain 适配（letterbox）
// 注意：必须观测“外层包裹容器”而非 Konva 自身撑大的舞台容器，否则会形成自反馈锁定尺寸
let ro: ResizeObserver | null = null;
onMounted(() => {
  const el = rootRef.value;
  if (!el) return;
  const apply = () => {
    stageW.value = Math.max(240, el.clientWidth);
    stageH.value = Math.round(stageW.value * (9 / 16));
  };
  apply();
  ro = new ResizeObserver(apply);
  ro.observe(el);
});

onBeforeUnmount(() => {
  ro?.disconnect();
  ro = null;
});
</script>

<style scoped>
.roi-canvas {
  /* 允许在 flex 容器（el-form-item__content）中收缩，避免被 Konva 舞台撑宽 */
  min-width: 0;
}

.roi-canvas__toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.roi-canvas__tip {
  font-size: 12px;
  color: #909399;
}

.roi-canvas__stage {
  width: 100%;
}
</style>
