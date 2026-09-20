<template>
  <g class="ann-label">
    <rect
      :x="labelX"
      :y="baseY - (h || tagH) - 4"
      :width="(w > 0 ? w : 24) + 8"
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
    >
      {{ label }}
    </text>
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
const h = ref(0);

// 直接用文字真实渲染 bbox 同步测量背景宽高，保证背景始终贴合文字、随字号平滑（无跳变）
function measure() {
  requestAnimationFrame(() => {
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
  });
}

onMounted(measure);
watch(() => [props.label, props.fontSize], measure);

defineExpose({ measure });
</script>
