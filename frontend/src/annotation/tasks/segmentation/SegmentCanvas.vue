<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <rect
      :x="bbox(ann).x"
      :y="bbox(ann).y"
      :width="bbox(ann).w"
      :height="bbox(ann).h"
      :stroke="color(ann)"
      stroke-width="1"
      fill="none"
      stroke-dasharray="4 2"
      class="seg-bbox-reference"
      vector-effect="non-scaling-stroke"
      style="pointer-events: none"
    />
    <path
      :d="path(ann)"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      fill-rule="evenodd"
      :fill="color(ann) + '20'"
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
        :data-handle="'poly-' + i"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'poly-' + i)"
      />
      <circle
        v-for="(pt, i) in ann.points"
        :key="'ins-' + i"
        :cx="midpoints(ann)[i]?.x"
        :cy="midpoints(ann)[i]?.y"
        r="3"
        fill="#fff"
        stroke="#3b82f6"
        stroke-width="1"
        class="handle"
        :style="peStyle"
        :data-handle="'poly-ins-' + i"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'poly-ins-' + i)"
      />
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Annotation, Point } from "../../core/types";
import { useSegmentTool } from "./useSegmentTool";

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

const seg = useSegmentTool();
const stroke = computed(() => props.stroke ?? 1.5);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const selStroke = computed(() => props.selStroke ?? 2);

function path(a: Annotation) {
  return seg.polygonPath(a, props.cw, props.ch);
}
function bbox(a: Annotation) {
  if (!a.points || a.points.length === 0) return { x: 0, y: 0, w: 0, h: 0 };
  return seg.polyBBox(a, props.cw, props.ch);
}
function midpoints(a: Annotation) {
  const pts = a.points || [];
  return pts.map((p: Point, i: number) => {
    const n = pts[(i + 1) % pts.length];
    return { x: ((p.x + n.x) / 2) * props.cw, y: ((p.y + n.y) / 2) * props.ch };
  });
}
</script>
