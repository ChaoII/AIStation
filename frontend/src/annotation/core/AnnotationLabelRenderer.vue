<template>
  <g class="ann-label">
    <rect
      :x="labelX"
      :y="baseY - (h || tagH) - 4"
      :width="w + 8"
      :height="(h || tagH) + 4"
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
import { ref, watch, onMounted, nextTick } from "vue";

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
const h = ref(0);

function measure() {
  const el = textRef.value;
  if (!el) return;
  try {
    const b = el.getBBox();
    if (b.width > 0 && b.height > 0) {
      w.value = b.width;
      h.value = b.height;
    }
  } catch {
    /* ignore */
  }
}

function remeasure() {
  nextTick(() => measure());
}

onMounted(remeasure);
watch(() => props.label, remeasure);
watch(() => props.fontSize, remeasure);

defineExpose({ measure });
</script>
