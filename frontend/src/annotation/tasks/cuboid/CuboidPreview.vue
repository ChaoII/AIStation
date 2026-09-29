<template>
  <g data-preview="cuboid">
    <!-- 已放置的点标记 -->
    <circle
      v-for="(pt, i) in placedPts"
      :key="'pt' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="4"
      fill="#fff"
      stroke="#3b82f6"
      stroke-width="1.5"
      :style="peStyle"
    />
    <!-- 底边预览线 -->
    <line
      v-if="edgePts"
      :x1="edgePts.x1"
      :y1="edgePts.y1"
      :x2="edgePts.x2"
      :y2="edgePts.y2"
      stroke="#3b82f6"
      stroke-width="1.5"
      :style="peStyle"
    />
    <!-- 底面预览（旋转矩形） -->
    <polygon
      v-if="basePts"
      :points="basePts"
      fill="#3b82f6"
      fill-opacity="0.12"
      stroke="#3b82f6"
      stroke-width="1.5"
      :style="peStyle"
    />
    <!-- 高度预览：顶面 + 4 条竖棱 -->
    <template v-if="basePts && height > 0">
      <polygon
        :points="topPts"
        fill="#3b82f6"
        fill-opacity="0.12"
        stroke="#3b82f6"
        stroke-width="1"
        stroke-dasharray="3 2"
        :style="peStyle"
      />
      <line
        v-for="i in 4"
        :key="'hv' + i"
        :x1="baseCorners[i - 1].x"
        :y1="baseCorners[i - 1].y"
        :x2="topCornersArr[i - 1].x"
        :y2="topCornersArr[i - 1].y"
        stroke="#3b82f6"
        stroke-width="1"
        stroke-dasharray="3 2"
        :style="peStyle"
      />
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  state: any;
  cw: number;
  ch: number;
  pointerNone?: boolean;
}>();

const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const px = computed(() => props.state?.preview?.value || {});

const placedPts = computed(() => [px.value.pt1, px.value.pt2, px.value.pt3].filter(Boolean));

const edgePts = computed(() => {
  const a = px.value.pt1;
  const b = px.value.pt2;
  if (!a || !b) return null;
  return {
    x1: a.x * props.cw,
    y1: a.y * props.ch,
    x2: b.x * props.cw,
    y2: b.y * props.ch,
  };
});

const height = computed(() => px.value.height || 0);

function baseCornersFrom(geom: any) {
  if (!geom) return [];
  const hw = (geom.width * props.cw) / 2;
  const hh = (geom.height * props.ch) / 2;
  const a1 = geom.angle1;
  const a2 = geom.angle2;
  const d1 = { x: Math.cos(a1), y: Math.sin(a1) };
  const d2 = { x: Math.cos(a2), y: Math.sin(a2) };
  const cx = geom.cx * props.cw;
  const cy = geom.cy * props.ch;
  const local: [number, number][] = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  return local.map(([lx, ly]) => ({
    x: cx + lx * d1.x + ly * d2.x,
    y: cy + lx * d1.y + ly * d2.y,
  }));
}

const baseCorners = computed(() => baseCornersFrom(px.value.baseGeom));
const basePts = computed(() =>
  baseCorners.value.length ? baseCorners.value.map((p) => `${p.x},${p.y}`).join(" ") : ""
);

const topCornersArr = computed(() => {
  const up = height.value * props.ch;
  return baseCorners.value.map((p) => ({ x: p.x, y: p.y - up }));
});
const topPts = computed(() =>
  topCornersArr.value.length ? topCornersArr.value.map((p) => `${p.x},${p.y}`).join(" ") : ""
);
</script>
