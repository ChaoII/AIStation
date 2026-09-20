<template>
  <g v-if="state.step.value > 0">
    <line
      v-if="state.pt1.value && state.last.value"
      :x1="state.pt1.value.x * cw"
      :y1="state.pt1.value.y * ch"
      :x2="state.last.value.x * cw"
      :y2="state.last.value.y * ch"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <line
      v-if="state.pt1.value && state.pt2.value && state.last.value"
      :x1="state.pt2.value.x * cw"
      :y1="state.pt2.value.y * ch"
      :x2="state.last.value.x * cw"
      :y2="state.last.value.y * ch"
      stroke="#f56c6c"
      stroke-width="1"
      stroke-dasharray="2 2"
    />
    <circle
      v-if="state.pt1.value"
      :cx="state.pt1.value.x * cw"
      :cy="state.pt1.value.y * ch"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <circle
      v-if="state.pt2.value"
      :cx="state.pt2.value.x * cw"
      :cy="state.pt2.value.y * ch"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <rect
      v-if="state.preview.value"
      :x="state.preview.value.cx * cw - (state.preview.value.width * cw) / 2"
      :y="state.preview.value.cy * ch - (state.preview.value.height * ch) / 2"
      :width="state.preview.value.width * cw"
      :height="state.preview.value.height * ch"
      fill="none"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
      :transform="`rotate(${(state.preview.value.angle * 180) / Math.PI} ${state.preview.value.cx * cw} ${state.preview.value.cy * ch})`"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
