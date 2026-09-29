<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <!-- 顶面平行四边形（底部平行四边形沿竖直方向平移 -top_cy） -->
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
    <!-- 底部平行四边形 -->
    <polygon
      :points="bottomPoints(ann)"
      :fill="ann.id === selectedId ? color(ann) + '28' : color(ann) + '14'"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <!-- 底面 4 角：拖对角改平行四边形 -->
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
      >
        <title>拖动缩放底面</title>
      </circle>
      <!-- 高度手柄：底面中心上方，沿竖直方向拖动调整高度 -->
      <circle
        :cx="ann.cx * cw"
        :cy="ann.cy * ch - (ann.top_cy || 0) * ch"
        r="5"
        fill="#fff"
        stroke="#409eff"
        stroke-width="2"
        class="handle"
        :style="peStyle"
        :data-handle="'cuboid-h'"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'cuboid-h')"
      >
        <title>调整高度（沿竖直方向）</title>
      </circle>
      <!-- 航向角手柄：底面「长边」中点外侧一点，绕中心旋转改 angle1/angle2/ry -->
      <circle
        :cx="rotateHandlePos(ann).x"
        :cy="rotateHandlePos(ann).y"
        r="5"
        fill="#fff"
        stroke="#67c23a"
        stroke-width="2"
        class="handle"
        :style="peStyle"
        :data-handle="'cuboid-rotate'"
        @mousedown.stop.prevent="$emit('rotate-down', $event, ann)"
      >
        <title>拖动旋转航向角（同步 angle1 / angle2 / 3D 的 ry）</title>
      </circle>
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

const handles = ["tl", "tr", "br", "bl"];
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

/** 旋转手柄位置：底面「长边」（沿 d1）中点沿 d1 方向外推一小段。 */
function rotateHandlePos(a: Annotation): { x: number; y: number } {
  const { d1 } = dirs(a);
  const hw = (a.w * props.cw) / 2;
  const cx = a.cx * props.cw;
  const cy = a.cy * props.ch;
  const push = hw + Math.min(24, props.cw * 0.04);
  return { x: cx + d1.x * push, y: cy + d1.y * push };
}

function dirs(a: Annotation) {
  const a1 = a.angle1 ?? a.yaw ?? 0;
  const a2 = a.angle2 ?? a1 + Math.PI / 2;
  return {
    d1: { x: Math.cos(a1), y: Math.sin(a1) },
    d2: { x: Math.cos(a2), y: Math.sin(a2) },
  };
}

function corner(a: Annotation, idx: number): { x: number; y: number } {
  const { d1, d2 } = dirs(a);
  const hw = (a.w * props.cw) / 2;
  const hh = (a.h * props.ch) / 2;
  const cx = a.cx * props.cw;
  const cy = a.cy * props.ch;
  const local: [number, number][] = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  const [lx, ly] = local[idx] || [0, 0];
  return { x: cx + lx * d1.x + ly * d2.x, y: cy + lx * d1.y + ly * d2.y };
}

// 顶面 = 底面沿竖直方向（图像向上）上移 height，无 pitch/roll 倾斜
function topCorner(a: Annotation, idx: number): { x: number; y: number } {
  const c = corner(a, idx);
  const H = (a.top_cy ?? a.depth ?? 0) * props.ch;
  return { x: c.x, y: c.y - H };
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
</script>
