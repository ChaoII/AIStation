<template>
  <g class="ann-label">
    <rect
      :x="labelX"
      :y="baseY - tagH - 4"
      :width="w + 8"
      :height="tagH + 4"
      :fill="color"
      :stroke="color"
      stroke-width="0.5"
      rx="1"
      vector-effect="non-scaling-stroke"
    />
    <text
      ref="textRef"
      :x="labelX + 2"
      :y="baseY"
      fill="#fff"
      font-weight="500"
      text-anchor="start"
      font-family="Microsoft YaHei,sans-serif"
      :font-size="fontSize"
      dominant-baseline="text-after-edge"
    >{{ label }}</text>
  </g>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";

const props = defineProps<{
  labelX: number;
  baseY: number;
  label: string;
  color: string;
  fontSize: number;
  tagH: number;
}>();

const textRef = ref<SVGTextElement | null>(null);
const w = ref(0);

// 高度用确定性的 tagH（随字号线性），宽度用同步 getComputedTextLength——无异步跳变
function measure() {
  const el = textRef.value;
  if (!el) return;
  try {
    const len = el.getComputedTextLength();
    if (len > 0) w.value = len;
  } catch {
    /* ignore */
  }
}

onMounted(measure);
watch(() => props.label, measure);
watch(() => props.fontSize, measure);

defineExpose({ measure });
</script>
