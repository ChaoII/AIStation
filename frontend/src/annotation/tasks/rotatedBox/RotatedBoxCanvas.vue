<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <rect
      :x="ann.cx * cw - (ann.width * cw) / 2"
      :y="ann.cy * ch - (ann.height * ch) / 2"
      :width="ann.width * cw"
      :height="ann.height * ch"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      :transform="`rotate(${(ann.angle * 180) / Math.PI} ${ann.cx * cw} ${ann.cy * ch})`"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <line
        :x1="handlePos(ann, 'tc').x"
        :y1="handlePos(ann, 'tc').y"
        :x2="rotateHandlePos(ann).x"
        :y2="rotateHandlePos(ann).y"
        :stroke="color(ann)"
        stroke-width="1"
      />
      <circle
        :cx="rotateHandlePos(ann).x"
        :cy="rotateHandlePos(ann).y"
        r="3"
        fill="#fff"
        :stroke="color(ann)"
        stroke-width="1.5"
        class="handle"
        :style="peStyle"
        @mousedown.stop.prevent="$emit('rotate-down', $event, ann)"
      />
      <rect
        v-for="h in handles"
        :key="h"
        :x="handlePos(ann, h).x - 4"
        :y="handlePos(ann, h).y - 4"
        width="8"
        height="8"
        fill="#fff"
        stroke="#1a1a1a"
        stroke-width="1.5"
        :data-handle="h"
        class="handle"
        :style="peStyle"
        vector-effect="non-scaling-stroke"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, h)"
      />
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
  (e: "rotate-down", ev: MouseEvent, ann: Annotation): void;
}>();

const handles = ["tl", "tr", "bl", "br"];
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

function handlePos(a: Annotation, key: string) {
  const hw = (a.width * props.cw) / 2;
  const hh = (a.height * props.ch) / 2;
  const cos = Math.cos(a.angle);
  const sin = Math.sin(a.angle);
  const map: Record<string, [number, number]> = {
    tl: [-hw, -hh],
    tr: [hw, -hh],
    bl: [-hw, hh],
    br: [hw, hh],
    tc: [0, -hh],
  };
  const [lx, ly] = map[key] || [0, 0];
  return {
    x: a.cx * props.cw + lx * cos - ly * sin,
    y: a.cy * props.ch + lx * sin + ly * cos,
  };
}

function rotateHandlePos(a: Annotation) {
  const tc = handlePos(a, "tc");
  const cx = a.cx * props.cw;
  const cy = a.cy * props.ch;
  const dx = tc.x - cx;
  const dy = tc.y - cy;
  const len = Math.hypot(dx, dy) || 1;
  const off = 25;
  return { x: tc.x + (dx / len) * off, y: tc.y + (dy / len) * off };
}
</script>
