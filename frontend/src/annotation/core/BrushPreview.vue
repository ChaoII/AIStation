<template>
  <g>
    <polyline
      v-for="(stroke, si) in strokes"
      :key="si"
      :points="strokePts(stroke)"
      fill="none"
      stroke="#3b82f6"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
      :style="peStyle"
    />
  </g>
</template>

<script setup lang="ts">
import { computed, unref } from "vue";
import type { Point } from "./types";

const props = defineProps<{
  state: any;
  cw: number;
  ch: number;
  zoom?: number;
  pointerNone?: boolean;
  brushSize?: number;
}>();
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
// 状态下可能直接传 ref（如任务插件 `state: { strokes: brush.strokes }`），也可能传普通数组；
// 用 unref 兼容两者，非响应式对象内嵌 ref 不会被 Vue 自动解包。
const strokes = computed<Point[][]>(() => unref(props.state?.strokes) ?? []);
const strokeWidth = computed(
  () => unref(props.state?.brushSize) ?? unref(props.brushSize) ?? 8
);
function strokePts(stroke: any[]): string {
  if (!stroke || stroke.length === 0) return "";
  return stroke
    .map((p) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ");
}
</script>
