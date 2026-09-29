<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <rect
      v-if="ann.bounding_box"
      :x="bb(ann).x1 * cw"
      :y="bb(ann).y1 * ch"
      :width="(bb(ann).x2 - bb(ann).x1) * cw"
      :height="(bb(ann).y2 - bb(ann).y1) * ch"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'kpb-move')"
    />
    <template v-if="ann.id === selectedId && ann.bounding_box">
      <rect
        v-for="h in handles"
        :key="h"
        :x="hbPos(ann, h).x - 4"
        :y="hbPos(ann, h).y - 4"
        width="8"
        height="8"
        fill="#fff"
        stroke="#1a1a1a"
        stroke-width="1.5"
        class="handle"
        :style="peStyle"
        :data-handle="'kpb-' + h"
        vector-effect="non-scaling-stroke"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'kpb-' + h)"
      />
    </template>
    <circle
      v-for="(kp, i) in ann.keypoints"
      :key="i"
      :cx="kp.x * cw"
      :cy="kp.y * ch"
      r="4"
      fill="#fff"
      :stroke="kp.color || color(ann)"
      stroke-width="1.5"
      class="handle"
      :style="peStyle"
      :data-handle="'kp-' + i"
      @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'kp-' + i)"
    />
    <g v-for="(kp, i) in ann.keypoints" :key="'l' + i">
      <rect
        :x="kp.x * cw + 8 - 2"
        :y="kp.y * ch - 4 - (fontSize + 6)"
        :width="kp.name.length * fontSize + 6"
        :height="fontSize + 6"
        rx="2"
        fill="#ffffff"
        fill-opacity="0.9"
        :stroke="kp.color || color(ann)"
        stroke-width="0.8"
        :style="peStyle"
      />
      <text
        :x="kp.x * cw + 8"
        :y="kp.y * ch - 4"
        :fill="kp.color || color(ann)"
        :font-size="fontSize"
        dominant-baseline="text-after-edge"
        :style="peStyle"
      >
        {{ kp.name }}
      </text>
    </g>
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

const handles = ["tl", "tr", "bl", "br", "tc", "bc", "ml", "mr"];
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

function bb(a: Annotation) {
  const b = a.bounding_box;
  if (!b) return { x1: 0, y1: 0, x2: 1, y2: 1 };
  return {
    x1: b.cx - b.width / 2,
    y1: b.cy - b.height / 2,
    x2: b.cx + b.width / 2,
    y2: b.cy + b.height / 2,
  };
}

function hbPos(a: Annotation, h: string) {
  const b = bb(a);
  const x = h.includes("l") ? b.x1 : h.includes("r") ? b.x2 : (b.x1 + b.x2) / 2;
  const y = h.includes("t") ? b.y1 : h.includes("b") ? b.y2 : (b.y1 + b.y2) / 2;
  return { x: x * props.cw, y: y * props.ch };
}
</script>
