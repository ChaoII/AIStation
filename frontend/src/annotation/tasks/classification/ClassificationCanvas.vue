<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id" :data-handle="ann.id">
    <text :x="10" :y="20" fill="#fff" font-size="6" font-family="Microsoft YaHei,sans-serif">
      {{ label(ann) }}
    </text>
  </g>
</template>

<script setup lang="ts">
import type { Annotation } from "../../core/types";

const props = defineProps<{
  annotations: Annotation[];
  clsName: (a: Annotation) => string;
  color: (a: Annotation) => string;
}>();

function label(a: Annotation) {
  if (Array.isArray(a.class_ids) && a.class_ids.length) {
    return a.class_ids.map((id: number) => props.clsName({ ...a, class_id: id })).join(" / ");
  }
  return props.clsName(a);
}
</script>
