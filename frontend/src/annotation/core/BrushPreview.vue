<template>
  <g>
    <polyline
      v-for="(stroke, si) in strokes"
      :key="si"
      :points="strokePts(stroke)"
      fill="none"
      :stroke="isLasso ? lassoColor : '#3b82f6'"
      :stroke-width="isLasso ? 1.5 : strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
      :style="peStyle"
    />
    <line
      v-if="isLasso && closePreview"
      :x1="closePreview.x1"
      :y1="closePreview.y1"
      :x2="closePreview.x2"
      :y2="closePreview.y2"
      :stroke="lassoColor"
      stroke-width="1"
      stroke-dasharray="4 4"
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
const strokes = computed<Point[][]>(() => unref(props.state?.strokes) ?? []);
const isLasso = computed(() => unref(props.state?.mode) === "lasso");
const lassoColor = "#3b82f6";
const strokeWidth = computed(
  () => unref(props.state?.brushSize) ?? unref(props.brushSize) ?? 8
);
// 套索闭合预览：首条第一点 → 末条最后一点
const closePreview = computed(() => {
  const s = strokes.value;
  if (!s.length) return null;
  const first = s[0]?.[0];
  const last = s[s.length - 1]?.[s[s.length - 1].length - 1];
  if (!first || !last) return null;
  return {
    x1: first.x * props.cw,
    y1: first.y * props.ch,
    x2: last.x * props.cw,
    y2: last.y * props.ch,
  };
});
function strokePts(stroke: any[]): string {
  if (!stroke || stroke.length === 0) return "";
  return stroke
    .map((p) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ");
}
</script>
