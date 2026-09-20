<template>
  <g>
    <rect
      v-if="state.boxDrafting.value && state.boxStart.value && state.boxEnd.value"
      :x="Math.min(state.boxStart.value.x, state.boxEnd.value.x) * cw"
      :y="Math.min(state.boxStart.value.y, state.boxEnd.value.y) * ch"
      :width="Math.abs(state.boxEnd.value.x - state.boxStart.value.x) * cw"
      :height="Math.abs(state.boxEnd.value.y - state.boxStart.value.y) * ch"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.pending.value"
      :key="'kp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="4"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
