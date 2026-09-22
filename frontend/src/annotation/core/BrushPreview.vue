<template>
  <g>
    <polyline
      v-for="(stroke, si) in (state?.strokes || [])"
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
import { computed } from "vue";

const props = defineProps<{
  state: any;
  cw: number;
  ch: number;
  pointerNone?: boolean;
  brushSize?: number;
}>();
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const strokeWidth = computed(() => props.brushSize ?? 8);
function strokePts(stroke: any[]): string {
  if (!stroke || stroke.length === 0) return "";
  return stroke
    .map((p) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ");
}
</script>
