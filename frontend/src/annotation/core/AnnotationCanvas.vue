<template>
  <div
    ref="wrap"
    class="annotation-canvas"
    :style="{ cursor }"
    @mousedown="onMousedown"
    @wheel.prevent="onWheel"
    @contextmenu.prevent
  >
    <img
      v-if="!isVideo && imgUrl"
      ref="imgRef"
      :src="imgUrl"
      class="ann-img"
      :style="canvas.svgStyle()"
      @load="onImgLoad"
      @error="onImgError"
    />
    <video
      v-if="isVideo && videoUrl"
      ref="videoRef"
      :src="videoUrl"
      class="ann-video"
      :style="canvas.svgStyle()"
      @loadedmetadata="onVideoLoaded"
      @seeked="$emit('video-seeked')"
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
import { computed, ref } from "vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";

const props = defineProps<{
  imgUrl: string;
  imageLoaded: boolean;
  videoUrl?: string;
  media?: "image" | "video";
  cursor?: string;
  canvas?: ReturnType<typeof useAnnotationCanvas>;
}>();

const emit = defineEmits<{
  (e: "img-load", w: number, h: number): void;
  (e: "img-error"): void;
  (e: "video-loaded", ev: Event): void;
  (e: "video-seeked"): void;
  (e: "mousedown", ev: MouseEvent): void;
  (e: "wheel", ev: WheelEvent): void;
}>();

const isVideo = computed(() => props.media === "video");
const wrap = ref<HTMLElement | null>(null);
const imgRef = ref<HTMLImageElement | null>(null);
const videoRef = ref<HTMLVideoElement | null>(null);
const canvas = props.canvas ?? useAnnotationCanvas();

function onImgLoad(e: Event) {
  const el = e.target as HTMLImageElement;
  emit("img-load", el.naturalWidth, el.naturalHeight);
}

function onImgError() {
  emit("img-error");
}

function onVideoLoaded(e: Event) {
  emit("video-loaded", e);
}

function onMousedown(e: MouseEvent) {
  emit("mousedown", e);
}

function onWheel(e: WheelEvent) {
  emit("wheel", e);
}

function getVideoEl(): HTMLVideoElement | null {
  return videoRef.value;
}

defineExpose({ canvas, getVideoEl });
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
.ann-video,
.ann-svg {
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
}
.ann-img,
.ann-video {
  -webkit-user-drag: none;
  user-drag: none;
  -webkit-touch-callout: none;
}
.ann-svg {
  pointer-events: all;
  user-select: none;
  -webkit-user-select: none;
}
</style>
