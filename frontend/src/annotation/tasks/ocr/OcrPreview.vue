<template>
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
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
const pts = computed(() =>
  props.state.quadPoints.value.map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ")
);
</script>
