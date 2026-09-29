<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <polygon
      :points="pts(ann)"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <text
      v-if="ann.text"
      :x="tx(ann)"
      :y="ty(ann)"
      fill="#fff"
      font-size="6"
      font-family="Microsoft YaHei,sans-serif"
      :style="{ pointerEvents: pointerNone ? 'none' : 'none' }"
    >
      {{ ann.text }}
    </text>
    <template v-if="ann.id === selectedId">
      <template v-if="ann.source === 'rect'">
        <circle
          v-for="c in rectCorners"
          :key="c.h"
          :cx="ann.points?.[c.i]?.x * cw"
          :cy="ann.points?.[c.i]?.y * ch"
          r="4"
          fill="#fff"
          stroke="#1a1a1a"
          stroke-width="1.5"
          class="handle"
          :style="peStyle"
          :data-handle="'ocr-' + c.h"
          @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'ocr-' + c.h)"
        />
      </template>
      <template v-else>
        <circle
          v-for="(pt, i) in ann.points"
          :key="i"
          :cx="pt.x * cw"
          :cy="pt.y * ch"
          r="4"
          fill="#fff"
          stroke="#1a1a1a"
          stroke-width="1.5"
          class="handle"
          :style="peStyle"
          :data-handle="'ocr-' + i"
          @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'ocr-' + i)"
        />
      </template>
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Annotation } from "../../core/types";

const props = defineProps<{
  annotations: Annotation[];
  cw: number;
  ch: number;
  selectedId: string;
  color: (a: Annotation) => string;
  clsName: (a: Annotation) => string;
  fontSize: number;
  tagH: number;
  stroke?: number;
  selStroke?: number;
  pointerNone?: boolean;
}>();

defineEmits<{
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
}>();

const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

const rectCorners = [
  { h: "tl", i: 0 },
  { h: "tr", i: 1 },
  { h: "br", i: 2 },
  { h: "bl", i: 3 },
];

function pts(a: Annotation) {
  return (a.points || []).map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ");
}
function tx(ann: Annotation): number {
  return (minX(ann) + 0.01) * props.cw;
}
function ty(ann: Annotation): number {
  return (minY(ann) + 0.01) * props.ch + 8;
}
function minX(ann: Annotation): number {
  return Math.min(...(ann.points || []).map((p: any) => p.x));
}
function minY(ann: Annotation): number {
  return Math.min(...(ann.points || []).map((p: any) => p.y));
}
</script>
