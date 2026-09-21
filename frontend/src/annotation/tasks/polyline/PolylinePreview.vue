<template>
  <g v-if="state.points.value.length">
    <polyline
      :points="pts"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.points.value"
      :key="'pp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="3"
      fill="#fff"
      stroke="#3b82f6"
      stroke-width="1"
    />
    <circle
      :cx="state.points.value[0].x * cw"
      :cy="state.points.value[0].y * ch"
      r="4"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
    />
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
const pts = computed(() =>
  props.state.points.value.map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ")
);
</script>
