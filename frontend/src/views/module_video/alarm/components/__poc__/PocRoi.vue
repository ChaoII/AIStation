<template>
  <div class="poc-roi">
    <div class="poc-roi__toolbar">
      <el-button size="small" type="primary" @click="clear">清空</el-button>
      <el-button size="small" @click="undo">撤销</el-button>
      <span class="poc-roi__tip">点击画布按序加点，生成闭合多边形（归一化坐标）</span>
    </div>

    <!-- 画布容器：宽度自适应，按 16:9 计算高度 -->
    <div ref="wrapRef" class="poc-roi__stage">
      <Stage :config="{ width: stageW, height: stageH }" @click="handleClick">
        <Layer>
          <!-- 底图区域占位（真实组件用快照图） -->
          <Line
            :config="{
              points: [0, 0, stageW, 0, stageW, stageH, 0, stageH],
              closed: true,
              fill: '#f5f7fa',
              stroke: '#dcdfe6',
              strokeWidth: 1,
            }"
          />
          <!-- 多边形：闭合 -->
          <Line
            :config="{
              points: pixelPoints,
              closed: true,
              fill: 'rgba(64, 158, 255, 0.2)',
              stroke: '#409eff',
              strokeWidth: 2,
            }"
          />
          <!-- 顶点 -->
          <Circle
            v-for="(p, i) in pixelVertices"
            :key="i"
            :config="{
              x: p[0],
              y: p[1],
              radius: 4,
              fill: '#409eff',
              stroke: '#fff',
              strokeWidth: 1,
              name: 'vertex',
            }"
          />
        </Layer>
      </Stage>
    </div>

    <div class="poc-roi__json">
      <div class="poc-roi__json-title">v-model（归一化点列）</div>
      <pre>{{ json }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Circle, Layer, Line, Stage } from "vue-konva";
import type { KonvaEventObject } from "konva/lib/Node";

/** 归一化点列 [[x,y],...]，0~1 */
const model = defineModel<number[][]>({ default: () => [] });

const wrapRef = ref<HTMLElement | null>(null);
const stageW = ref(640);
const stageH = ref(360);

/** 内部以归一化点列存储，渲染时换算为像素 */
const points = ref<number[][]>([]);

const pixelPoints = computed(() => points.value.flatMap(([x, y]) => [x * stageW.value, y * stageH.value]));
const pixelVertices = computed(() => points.value.map(([x, y]) => [x * stageW.value, y * stageH.value]));
const json = computed(() => JSON.stringify(points.value, null, 2));

function sync() {
  model.value = points.value.map(([x, y]) => [Number(x.toFixed(6)), Number(y.toFixed(6))]);
}

function handleClick(e: KonvaEventObject<MouseEvent>) {
  // 点击已有顶点时不新增点
  if (e.target.name() === "vertex") return;
  const stage = e.target.getStage();
  const pos = stage?.getPointerPosition();
  if (!pos) return;
  points.value = [...points.value, [pos.x / stageW.value, pos.y / stageH.value]];
  sync();
}

function undo() {
  points.value = points.value.slice(0, -1);
  sync();
}

function clear() {
  points.value = [];
  sync();
}

// 容器尺寸自适应（POC 用 16:9）
let ro: ResizeObserver | null = null;
onMounted(() => {
  const el = wrapRef.value;
  if (!el) return;
  ro = new ResizeObserver(() => {
    stageW.value = Math.max(200, el.clientWidth);
    stageH.value = Math.round(stageW.value * (9 / 16));
  });
  ro.observe(el);
});

onBeforeUnmount(() => {
  ro?.disconnect();
  ro = null;
});
</script>

<style scoped>
.poc-roi__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.poc-roi__tip {
  color: #909399;
  font-size: 12px;
}

.poc-roi__stage {
  width: 100%;
}

.poc-roi__json {
  margin-top: 8px;
}

.poc-roi__json-title {
  margin-bottom: 4px;
  color: #606266;
  font-size: 12px;
}

.poc-roi__json pre {
  max-height: 160px;
  padding: 8px;
  overflow: auto;
  font-size: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
</style>
