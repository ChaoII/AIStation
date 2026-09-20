<template>
  <g v-if="state.preview.value">
    <rect
      :x="state.preview.value.x * cw"
      :y="state.preview.value.y * ch"
      :width="state.preview.value.w * cw"
      :height="state.preview.value.h * ch"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
