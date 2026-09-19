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
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <circle
      v-for="(kp, i) in ann.keypoints"
      :key="i"
      :cx="kp.x * cw"
      :cy="kp.y * ch"
      r="4"
      fill="#fff"
      :stroke="color(ann)"
      stroke-width="1.5"
      class="handle"
      :data-handle="'kp-' + i"
      @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'kp-' + i)"
    />
    <text
      v-for="(kp, i) in ann.keypoints"
      :key="'t' + i"
      :x="kp.x * cw + 8"
      :y="kp.y * ch - 4"
      fill="#606266"
      font-size="5"
    >{{ kp.name }}</text>
    <AnnotationLabelRenderer
      :label-x="bb(ann).x1 * cw"
      :base-y="bb(ann).y1 * ch - 2"
      :label="clsName(ann)"
      :color="color(ann)"
      :font-size="fontSize"
      :tag-h="tagH"
    />
  </g>
</template>

<script setup lang="ts">
import type { Annotation } from "../../core/types";
import AnnotationLabelRenderer from "../../core/AnnotationLabelRenderer.vue";

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
}>();

const emit = defineEmits<{
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
}>();

const stroke = props.stroke ?? 1.5;
const selStroke = props.selStroke ?? 2;

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
</script>
