<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <polyline
      :points="linePoints(ann)"
      fill="none"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
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
        v-for="(pt, i) in midpoints(ann)"
        :key="'ins-' + i"
        :cx="pt.x"
        :cy="pt.y"
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

function linePoints(a: Annotation): string {
  return (a.points || []).map((p: any) => `${p.x * props.cw},${p.y * props.ch}`).join(" ");
}

function midpoints(a: Annotation): { x: number; y: number }[] {
  const pts = a.points || [];
  const out: { x: number; y: number }[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    out.push({
      x: ((pts[i].x + pts[i + 1].x) / 2) * props.cw,
      y: ((pts[i].y + pts[i + 1].y) / 2) * props.ch,
    });
  }
  return out;
}
</script>
