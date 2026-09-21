<template>
  <g v-for="ann in rendered" :key="ann.id" :data-ann-id="ann.id">
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
    <text
      v-if="instanceLabel(ann)"
      :x="Math.min(...(ann.points || []).map((p: any) => p.x)) * cw"
      :y="Math.min(...(ann.points || []).map((p: any) => p.y)) * ch - 2"
      font-size="6"
      fill="#fff"
      stroke="#000"
      stroke-width="0.4"
      paint-order="stroke"
      :style="{ pointerEvents: 'none' }"
    >
      {{ instanceLabel(ann) }}
    </text>
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
import { useSegmentTool } from "../segmentation/useSegmentTool";
import { panopticClasses } from "./sharedState";

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
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

// 整体渲染列表：thing/stuff 均按录入顺序渲染（stuff 垫底由填充背景标注承担）
const rendered = computed(() => [...props.annotations]);

function isInstanceClass(ann: Annotation): boolean {
  const cls = panopticClasses.value.find((c) => c.id === ann.class_id);
  return !!cls?.is_instance;
}

function path(a: Annotation) {
  return seg.polygonPath(a, props.cw, props.ch);
}
function midpoints(a: Annotation) {
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

// thing 实例号：按类别分组、组内按数组顺序从 1 编号
function instanceLabel(ann: Annotation): string {
  if (!isInstanceClass(ann)) return "";
  const sameClass = props.annotations.filter(
    (a) => a.type === "Polygon" && isInstanceClass(a) && a.class_id === ann.class_id
  );
  const idx = sameClass.findIndex((a) => a.id === ann.id);
  const name = props.clsName(ann);
  return `${name}#${idx + 1}`;
}
</script>
