<template>
  <g v-if="state.mode.value === 'rect' && state.first.value">
    <rect
      :x="rx"
      :y="ry"
      :width="rw"
      :height="rh"
      fill="rgba(230,162,60,0.12)"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      :cx="state.first.value.x * cw"
      :cy="state.first.value.y * ch"
      r="3"
      fill="#fff"
      stroke="#e6a23c"
      stroke-width="1"
    />
  </g>
  <g v-if="state.mode.value === 'quad' && state.quadPoints.value.length">
    <polyline
      :points="pts"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.quadPoints.value"
      :key="'oq' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="3"
      fill="#fff"
      stroke="#e6a23c"
      stroke-width="1"
    />
    <circle
      v-if="state.quadPoints.value.length >= 4"
      :cx="state.quadPoints.value[0].x * cw"
      :cy="state.quadPoints.value[0].y * ch"
      r="6"
      fill="none"
      stroke="#67c23a"
      stroke-width="1.5"
      stroke-dasharray="2 2"
    />
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
const pts = computed(() =>
  props.state.quadPoints.value.map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ")
);
const rx = computed(() => {
  const a = props.state.first.value;
  const b = props.state.last.value ?? a;
  return Math.min(a.x, b.x) * props.cw;
});
const ry = computed(() => {
  const a = props.state.first.value;
  const b = props.state.last.value ?? a;
  return Math.min(a.y, b.y) * props.ch;
});
const rw = computed(() => {
  const a = props.state.first.value;
  const b = props.state.last.value ?? a;
  return Math.abs(b.x - a.x) * props.cw;
});
const rh = computed(() => {
  const a = props.state.first.value;
  const b = props.state.last.value ?? a;
  return Math.abs(b.y - a.y) * props.ch;
});
</script>
