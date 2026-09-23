<template>
  <g>
    <!-- 已确定点折线（实线） -->
    <polyline
      v-if="points.length"
      :points="fixedPts"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
    />
    <!-- 已确定点小圈 -->
    <circle
      v-for="(pt, i) in points"
      :key="'pp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="3"
      fill="#fff"
      stroke="#3b82f6"
      stroke-width="1"
    />
    <!-- 首点：鼠标靠近时放大为闭合提示圈 -->
    <circle
      v-if="points.length && nearFirst"
      :cx="points[0].x * cw"
      :cy="points[0].y * ch"
      :r="12"
      fill="none"
      stroke="#3b82f6"
      stroke-width="2"
      class="close-hint"
    />
    <circle
      v-else-if="points.length"
      :cx="points[0].x * cw"
      :cy="points[0].y * ch"
      r="4"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
    />
    <!-- 末点 → 鼠标 跟随预览虚线 -->
    <line
      v-if="points.length && cursor"
      :x1="points[points.length - 1].x * cw"
      :y1="points[points.length - 1].y * ch"
      :x2="cursor.x * cw"
      :y2="cursor.y * ch"
      stroke="#3b82f6"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <!-- 鼠标跟随点 -->
    <circle
      v-if="cursor"
      :cx="cursor.x * cw"
      :cy="cursor.y * ch"
      r="3.5"
      fill="#3b82f6"
    />
  </g>
</template>
<script setup lang="ts">
import { computed, unref } from "vue";
import type { Point } from "../../core/types";

const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();

const points = computed<Point[]>(() => unref(props.state?.points) ?? []);
const cursor = computed<Point | null>(() => unref(props.state?.cursor) ?? null);
const closeRadiusPx = computed<number>(() => unref(props.state?.closeRadiusPx) ?? 14);

const fixedPts = computed(
  () =>
    points.value
      .map((p: Point) => `${p.x * props.cw},${p.y * props.ch}`)
      .join(" ")
);

// 鼠标是否靠近首点（屏幕像素距离），用于首点圈放大提示
const nearFirst = computed(() => {
  const first = points.value[0];
  const cur = cursor.value;
  if (!first || !cur || !props.cw || !props.ch) return false;
  const dx = (cur.x - first.x) * props.cw * (props.zoom || 1);
  const dy = (cur.y - first.y) * props.ch * (props.zoom || 1);
  return Math.sqrt(dx * dx + dy * dy) <= closeRadiusPx.value;
});
</script>
