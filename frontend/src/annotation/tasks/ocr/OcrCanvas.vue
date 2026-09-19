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
    <template v-if="ann.id === selectedId">
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
    <AnnotationLabelRenderer
      :label-x="bbox(ann).x1 * cw"
      :base-y="bbox(ann).y1 * ch - 2"
      :label="ann.text || clsName(ann)"
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

const stroke = props.stroke ?? 1.5;
const selStroke = props.selStroke ?? 2;
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

function pts(a: Annotation) {
  return (a.points || []).map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ");
}
function bbox(a: Annotation) {
  const xs = (a.points || []).map((p: any) => p.x);
  const ys = (a.points || []).map((p: any) => p.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys) };
}
</script>
