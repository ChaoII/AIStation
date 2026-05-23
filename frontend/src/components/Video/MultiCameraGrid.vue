<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  layout: string
  cameraBindings: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'openCamera', cameraId: number): void
  (e: 'removeCamera', windowId: string): void
}>()

const gridClass = computed(() => `grid-${props.layout}`)

const windows = computed(() => {
  const count = parseInt(props.layout) || 4
  return Array.from({ length: count }, (_, i) => ({
    id: `w${i + 1}`,
    camera: props.cameraBindings[`w${i + 1}`] || null,
  }))
})

function getStreamUrl(camera: any): string | undefined {
  return camera?.play_urls?.flv || camera?.play_urls?.hls || camera?.play_urls?.webrtc || camera?.stream_url
}

function getStreamType(url: string | undefined): 'webrtc' | 'flv' | 'hls' | undefined {
  if (!url) return undefined
  if (url.startsWith('webrtc')) return 'webrtc'
  if (url.endsWith('.flv')) return 'flv'
  if (url.endsWith('.m3u8')) return 'hls'
  return 'flv'
}
</script>

<template>
  <div class="multi-camera-grid" :class="gridClass">
    <div v-for="w in windows" :key="w.id" class="grid-window" @dblclick="w.camera && emit('openCamera', w.camera.id)">
      <div v-if="w.camera" class="window-content">
        <LivePlayer
          :stream-url="getStreamUrl(w.camera)"
          :stream-type="getStreamType(getStreamUrl(w.camera))"
          :poster="w.camera.poster"
          class="window-player"
        />
        <div class="window-label">{{ w.camera.name }}</div>
        <el-button class="window-close" size="small" circle text type="danger" icon="Close" @click.stop="emit('removeCamera', w.id)" />
      </div>
      <div v-else class="window-empty" @click="emit('openCamera', 0)">
        <el-icon :size="32"><Plus /></el-icon>
        <span>添加摄像机</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.multi-camera-grid {
  display: grid;
  gap: 2px;
  width: 100%;
  height: 100%;
  background: #1a1a1a;
  padding: 2px;
}

.grid-1 { grid-template-columns: 1fr; grid-template-rows: 1fr; }
.grid-4 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
.grid-6 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
.grid-8 { grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(2, 1fr); }
.grid-9 { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); }
.grid-16 { grid-template-columns: repeat(4, 1fr); grid-template-rows: repeat(4, 1fr); }

.grid-window {
  position: relative;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  min-height: 120px;
}

.window-content {
  width: 100%;
  height: 100%;
}

.window-player {
  width: 100%;
  height: 100%;
}

.window-label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 10px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
  color: #fff;
  font-size: 12px;
  z-index: 1;
}

.window-close {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.2s;
}

.grid-window:hover .window-close {
  opacity: 1;
}

.window-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #555;
  cursor: pointer;
  gap: 8px;
  transition: color 0.2s, background 0.2s;
}

.window-empty:hover {
  color: #409eff;
  background: rgba(64, 158, 255, 0.05);
}
</style>
