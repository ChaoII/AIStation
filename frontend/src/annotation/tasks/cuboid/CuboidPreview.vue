<template>
  <g>
    <polyline
      v-if="previewPt1 && previewPt2"
      :points="edgePts"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
    />
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
const previewPt1 = computed(() => props.state?.preview?.value?.pt1);
const previewPt2 = computed(() => props.state?.preview?.value?.pt2);
const edgePts = computed(() => {
  if (!previewPt1.value || !previewPt2.value) return "";
  return `${previewPt1.value.x * props.cw},${previewPt1.value.y * props.ch} ${previewPt2.value.x * props.cw},${previewPt2.value.y * props.ch}`;
});
</script>
