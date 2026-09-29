<template>
  <g v-if="state.step.value > 0">
    <!-- 已确定的边 p1→p2（实线） -->
    <line
      v-if="state.pt1.value && state.pt2.value"
      :x1="px(state.pt1.value)"
      :y1="py(state.pt1.value)"
      :x2="px(state.pt2.value)"
      :y2="py(state.pt2.value)"
      stroke="#f56c6c"
      stroke-width="2"
    />
    <!-- p1 到当前鼠标：第一个边方向引导 -->
    <line
      v-if="state.pt1.value && state.last.value && !state.pt2.value"
      :x1="px(state.pt1.value)"
      :y1="py(state.pt1.value)"
      :x2="px(state.last.value)"
      :y2="py(state.last.value)"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <!-- p2 到当前鼠标：垂直方向引导 -->
    <line
      v-if="state.pt1.value && state.pt2.value && state.last.value"
      :x1="px(state.pt2.value)"
      :y1="py(state.pt2.value)"
      :x2="px(state.last.value)"
      :y2="py(state.last.value)"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <!-- 高度垂线：当前鼠标到边 -->
    <line
      v-if="state.pt1.value && state.pt2.value && state.last.value"
      :x1="px(state.last.value)"
      :y1="py(state.last.value)"
      :x2="px(foot)"
      :y2="py(foot)"
      stroke="#67c23a"
      stroke-width="1"
      stroke-dasharray="2 2"
    />
    <circle
      v-if="state.pt1.value"
      :cx="px(state.pt1.value)"
      :cy="py(state.pt1.value)"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <circle
      v-if="state.pt2.value"
      :cx="px(state.pt2.value)"
      :cy="py(state.pt2.value)"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <circle
      v-if="state.last.value"
      :cx="px(state.last.value)"
      :cy="py(state.last.value)"
      r="3"
      fill="#e6a23c"
      stroke="#e6a23c"
      stroke-width="1"
    />
    <rect
      v-if="state.preview.value"
      :x="state.preview.value.cx * cw - (state.preview.value.width * cw) / 2"
      :y="state.preview.value.cy * ch - (state.preview.value.height * ch) / 2"
      :width="state.preview.value.width * cw"
      :height="state.preview.value.height * ch"
      fill="none"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
      :transform="`rotate(${(state.preview.value.angle * 180) / Math.PI} ${state.preview.value.cx * cw} ${state.preview.value.cy * ch})`"
    />
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();

function px(p: any) {
  return p.x * props.cw;
}
function py(p: any) {
  return p.y * props.ch;
}

// 当前鼠标到边 p1p2 的垂足（在图像归一化坐标）
const foot = computed(() => {
  const a = props.state.pt1.value;
  const b = props.state.pt2.value;
  const p = props.state.last.value;
  if (!a || !b || !p) return null;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) return null;
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / (len * len);
  return { x: a.x + t * dx, y: a.y + t * dy };
});
</script>
