<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <!-- 顶面平行四边形（底部矩形沿 y 平移 -top_cy） -->
    <polygon
      :points="topPoints(ann)"
      data-role="top"
      fill="none"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <!-- 4 条竖直棱线 -->
    <line
      v-for="i in 4"
      :key="'edge-' + i"
      :x1="corner(ann, i - 1).x"
      :y1="corner(ann, i - 1).y"
      :x2="topCorner(ann, i - 1).x"
      :y2="topCorner(ann, i - 1).y"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
    />
    <!-- 底部旋转矩形 -->
    <polygon
      :points="bottomPoints(ann)"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <circle
        v-for="h in handles"
        :key="'rot-' + h"
        :cx="handlePos(ann, h).x"
        :cy="handlePos(ann, h).y"
        r="4"
        fill="#fff"
        stroke="#1a1a1a"
        stroke-width="1.5"
        :data-handle="h"
        class="handle"
        :style="peStyle"
        vector-effect="non-scaling-stroke"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, h)"
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
        :data-handle="'rotate'"
        @mousedown.stop.prevent="$emit('rotate-down', $event, ann)"
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

function corner(a: Annotation, idx: number): { x: number; y: number } {
  const hw = (a.w * props.cw) / 2;
  const hh = (a.h * props.ch) / 2;
  const cos = Math.cos(a.yaw);
  const sin = Math.sin(a.yaw);
  const map: Record<number, [number, number]> = {
    0: [-hw, -hh],
    1: [hw, -hh],
    2: [hw, hh],
    3: [-hw, hh],
  };
  const [lx, ly] = map[idx] || [0, 0];
  return { x: a.cx * props.cw + lx * cos - ly * sin, y: a.cy * props.ch + lx * sin + ly * cos };
}

function topCorner(a: Annotation, idx: number): { x: number; y: number } {
  const c = corner(a, idx);
  return { x: c.x, y: c.y - a.top_cy * props.ch };
}

function pts(ann: Annotation, fn: (a: Annotation, i: number) => { x: number; y: number }): string {
  return [0, 1, 2, 3]
    .map((i) => {
      const p = fn(ann, i);
      return `${p.x},${p.y}`;
    })
    .join(" ");
}

function bottomPoints(ann: Annotation): string {
  return pts(ann, (a, i) => corner(a, i));
}

function topPoints(ann: Annotation): string {
  return pts(ann, (a, i) => topCorner(a, i));
}

function handlePos(a: Annotation, key: string) {
  const idx = { tl: 0, tr: 1, br: 2, bl: 3 }[key as string] ?? 0;
  return corner(a, idx);
}

function rotateHandlePos(a: Annotation) {
  const tc = corner(a, 0);
  const cx = a.cx * props.cw;
  const cy = a.cy * props.ch;
  const dx = tc.x - cx;
  const dy = tc.y - cy;
  const len = Math.hypot(dx, dy) || 1;
  const off = 25;
  return { x: tc.x + (dx / len) * off, y: tc.y + (dy / len) * off };
}
</script>
