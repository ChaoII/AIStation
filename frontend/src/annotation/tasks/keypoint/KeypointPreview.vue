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
    <g v-for="(pt, i) in state.pending.value" :key="'l' + i">
      <rect
        :x="pt.x * cw + 8 - 2"
        :y="pt.y * ch - 4 - (fontSize + 6)"
        :width="pt.name.length * fontSize + 6"
        :height="fontSize + 6"
        rx="2"
        fill="#ffffff"
        fill-opacity="0.9"
        :stroke="pt.color || '#e6a23c'"
        stroke-width="0.8"
      />
      <text
        :x="pt.x * cw + 8"
        :y="pt.y * ch - 4"
        :fill="pt.color || '#e6a23c'"
        :font-size="fontSize"
        dominant-baseline="text-after-edge"
      >
        {{ pt.name }}
      </text>
    </g>
    <circle
      v-for="(pt, i) in state.pending.value"
      :key="'kp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="4"
      fill="none"
      :stroke="pt.color || '#e6a23c'"
      stroke-width="1.5"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number; fontSize: number }>();
</script>
