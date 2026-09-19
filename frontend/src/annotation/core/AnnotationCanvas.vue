<template>
  <div ref="wrap" class="annotation-canvas" :style="{ cursor }" @mousedown="onMousedown" @wheel.prevent="onWheel">
    <img
      v-if="imgUrl"
      ref="imgRef"
      :src="imgUrl"
      class="ann-img"
      :style="canvas.svgStyle()"
      @load="onImgLoad"
    />
    <svg
      v-if="imageLoaded"
      class="ann-svg"
      :style="canvas.svgStyle()"
      :viewBox="canvas.svgViewBox()"
    >
      <slot />
    </svg>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";

const props = defineProps<{
  imgUrl: string;
  imageLoaded: boolean;
  cursor?: string;
  canvas?: ReturnType<typeof useAnnotationCanvas>;
}>();

const emit = defineEmits<{
  (e: "img-load", w: number, h: number): void;
  (e: "mousedown", ev: MouseEvent): void;
  (e: "wheel", ev: WheelEvent): void;
}>();

const wrap = ref<HTMLElement | null>(null);
const imgRef = ref<HTMLImageElement | null>(null);
const canvas = props.canvas ?? useAnnotationCanvas();

function onImgLoad(e: Event) {
  const el = e.target as HTMLImageElement;
  canvas.setImageSize(el.naturalWidth, el.naturalHeight);
  const r = wrap.value?.getBoundingClientRect();
  if (r) canvas.fitZoom(r.width, r.height);
  emit("img-load", el.naturalWidth, el.naturalHeight);
}

function onMousedown(e: MouseEvent) {
  emit("mousedown", e);
}

function onWheel(e: WheelEvent) {
  emit("wheel", e);
}

defineExpose({ canvas });
</script>

<style scoped>
.annotation-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}
.ann-img,
.ann-svg {
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
}
.ann-img {
  -webkit-user-drag: none;
  user-drag: none;
}
.ann-svg {
  pointer-events: all;
  user-select: none;
  -webkit-user-select: none;
}
</style>
