<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <rect
      :x="ann.x1 * cw"
      :y="ann.y1 * ch"
      :width="(ann.x2 - ann.x1) * cw"
      :height="(ann.y2 - ann.y1) * ch"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
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
        :style="peStyle"
        class="handle"
        vector-effect="non-scaling-stroke"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, h)"
      />
    </template>
    <AnnotationLabelRenderer
      :label-x="ann.x1 * cw"
      :base-y="ann.y1 * ch - 2"
      :label="clsName(ann)"
      :color="color(ann)"
      :font-size="fontSize"
      :tag-h="tagH"
    />
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
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
  pointerNone?: boolean;
}>();

const emit = defineEmits<{
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
}>();

const handles = ["tl", "tr", "bl", "br", "tc", "bc", "ml", "mr"];
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

function handlePos(a: Annotation, h: string) {
  const x = h.includes("l") ? a.x1 : h.includes("r") ? a.x2 : (a.x1 + a.x2) / 2;
  const y = h.includes("t") ? a.y1 : h.includes("b") ? a.y2 : (a.y1 + a.y2) / 2;
  return { x: x * props.cw, y: y * props.ch };
}
</script>
