<template>
  <g class="det-track-overlay">
    <template v-for="p in paths" :key="p.trackId">
      <polyline
        v-if="p.points.length > 1"
        :points="pointsStr(p.points)"
        fill="none"
        :stroke="p.color"
        :stroke-width="p.selected ? selStroke : stroke"
        :stroke-dasharray="p.selected ? 'none' : '6 4'"
        vector-effect="non-scaling-stroke"
      />
      <circle
        v-for="(pt, i) in p.points"
        :key="i"
        :cx="pt.x * cw"
        :cy="pt.y * ch"
        :r="p.selected ? 4 : 2.5"
        :fill="p.color"
        :stroke="p.selected ? '#fff' : 'none'"
        :stroke-width="p.selected ? 1 : 0"
        vector-effect="non-scaling-stroke"
      />
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Point } from "../../core/types";

const props = defineProps<{
  /** 各轨迹的跨帧连线点位（归一化坐标） */
  paths: { trackId: string; points: Point[]; color: string; selected: boolean }[];
  cw: number;
  ch: number;
  stroke?: number;
  selStroke?: number;
}>();

const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2.5);

function pointsStr(points: Point[]): string {
  return points.map((p) => `${p.x * props.cw},${p.y * props.ch}`).join(" ");
}
</script>
