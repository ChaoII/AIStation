<!--
  GridSpotlight —— 跟随鼠标的「聚光淡网格」背景层。

  设计取舍：这是**视觉特效**（不是通用能力），故不引第三方；零依赖、~60 行。
  若要「粒子/连线网络跟随鼠标」，请改用 tsParticles（见对话中的选型对比）。

  交互：监听 window 的 mousemove（passive），把光标位置写入 CSS 变量 --mx/--my；
  网格用 radial-gradient 做 mask，只在光标附近显现 → 像一束聚光扫过淡网格。
  自身 pointer-events: none，不遮挡表单。
-->
<template>
  <div
    class="grid-spotlight"
    :class="{ 'is-active': active }"
    :style="{
      '--gs-cell': `${cell}px`,
      '--gs-radius': `${radius}px`,
      '--gs-color': color,
      '--gs-line': lineColor,
      '--gs-glow': glowColor,
      '--gs-grid-opacity': gridOpacity,
      '--gs-glow-opacity': glowOpacity,
    }"
  >
    <div class="grid-spotlight__grid" />
    <div class="grid-spotlight__glow" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

interface Props {
  /** 网格单元尺寸（px） */
  cell?: number;
  /** 聚光半径（px） */
  radius?: number;
  /** 主色（默认取 Element Plus 主色变量） */
  color?: string;
  /** 网格线颜色（含透明度） */
  lineColor?: string;
  /** 光标光晕颜色（含透明度） */
  glowColor?: string;
  /** 网格线透明度 */
  gridOpacity?: number;
  /** 光标光晕透明度 */
  glowOpacity?: number;
}

withDefaults(defineProps<Props>(), {
  cell: 46,
  radius: 220,
  color: "var(--el-color-primary, #409eff)",
  lineColor: "rgba(64, 158, 255, 0.45)",
  glowColor: "rgba(64, 158, 255, 0.55)",
  gridOpacity: 0.35,
  glowOpacity: 0.16,
});

const active = ref(false);

function onMove(e: MouseEvent) {
  const el = e.currentTarget as Window | null;
  const x = e.clientX;
  const y = e.clientY;
  // 写入根元素变量（组件自身也监听 window，故直接写 documentElement）
  const root = document.documentElement;
  root.style.setProperty("--gs-mx", `${x}px`);
  root.style.setProperty("--gs-my", `${y}px`);
  if (!active.value) active.value = true;
  void el;
}

function onLeave() {
  active.value = false;
}

onMounted(() => {
  // 触摸设备不启用（无 hover 语义）
  if (window.matchMedia("(hover: none)").matches) return;
  window.addEventListener("mousemove", onMove, { passive: true });
  window.addEventListener("mouseout", onLeave);
});

onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMove);
  window.removeEventListener("mouseout", onLeave);
});
</script>

<style lang="scss" scoped>
.grid-spotlight {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.grid-spotlight__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, var(--gs-line) 1px, transparent 1px),
    linear-gradient(to bottom, var(--gs-line) 1px, transparent 1px);
  background-size: var(--gs-cell) var(--gs-cell);
  opacity: 0;
  transition: opacity 0.35s ease;
  // 只在光标附近显现（聚光）
  mask-image: radial-gradient(
    circle var(--gs-radius) at var(--gs-mx, 50%) var(--gs-my, 50%),
    rgba(0, 0, 0, 0.9),
    rgba(0, 0, 0, 0) 72%
  );
  -webkit-mask-image: radial-gradient(
    circle var(--gs-radius) at var(--gs-mx, 50%) var(--gs-my, 50%),
    rgba(0, 0, 0, 0.9),
    rgba(0, 0, 0, 0) 72%
  );
}

.grid-spotlight__glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    circle var(--gs-radius) at var(--gs-mx, 50%) var(--gs-my, 50%),
    var(--gs-glow),
    transparent 70%
  );
  opacity: 0;
  transition: opacity 0.35s ease;
}

.grid-spotlight.is-active .grid-spotlight__grid {
  opacity: var(--gs-grid-opacity);
}

.grid-spotlight.is-active .grid-spotlight__glow {
  opacity: var(--gs-glow-opacity);
}

@media (prefers-reduced-motion: reduce) {
  .grid-spotlight__grid,
  .grid-spotlight__glow {
    transition: none;
  }
}
</style>
