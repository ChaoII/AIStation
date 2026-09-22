<template>
  <div class="video-player-bar">
    <el-button
      class="vp-btn"
      size="small"
      :icon="DArrowLeft"
      :disabled="currentFrame <= 0"
      @click="$emit('prev')"
    />
    <el-button
      class="vp-btn"
      size="small"
      :icon="playing ? VideoPause : VideoPlay"
      @click="$emit('togglePlay')"
    />
    <el-button
      class="vp-btn"
      size="small"
      :icon="DArrowRight"
      :disabled="frameCount > 0 && currentFrame >= frameCount - 1"
      @click="$emit('next')"
    />
    <el-slider
      class="vp-slider"
      :model-value="currentTime"
      :min="0"
      :max="duration"
      :step="step"
      :show-tooltip="false"
      @change="onSeek"
    />
    <span class="vp-frame-text">{{ currentFrame }} / {{ frameCount }}</span>
    <div class="vp-zoom">
      <el-button
        class="vp-btn"
        size="small"
        :icon="ZoomOut"
        :disabled="zoom <= 0.1"
        @click="$emit('zoomOut')"
      />
      <el-button
        class="vp-btn"
        size="small"
        :icon="ZoomIn"
        :disabled="zoom >= 3"
        @click="$emit('zoomIn')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  VideoPlay,
  VideoPause,
  DArrowLeft,
  DArrowRight,
  ZoomIn,
  ZoomOut,
} from "@element-plus/icons-vue";

const props = withDefaults(
  defineProps<{
    currentFrame: number;
    frameCount: number;
    duration: number;
    currentTime: number;
    fps: number;
    playing: boolean;
    zoom?: number;
  }>(),
  { zoom: 1 }
);

const emit = defineEmits<{
  (e: "prev"): void;
  (e: "next"): void;
  (e: "seek", time: number): void;
  (e: "togglePlay"): void;
  (e: "zoomIn"): void;
  (e: "zoomOut"): void;
}>();

const step = computed(() => (props.fps > 0 ? 1 / props.fps : 0.01));

function onSeek(value: number | number[]) {
  const time = Array.isArray(value) ? value[0] : value;
  emit("seek", time);
}
</script>

<style scoped>
.video-player-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-light);
  background: #fff;
}
.vp-slider {
  flex: 1;
  margin: 0 8px;
}
.vp-frame-text {
  min-width: 48px;
  text-align: center;
  color: var(--el-text-color-regular);
}
.vp-zoom {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
