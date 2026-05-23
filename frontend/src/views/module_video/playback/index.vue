<template>
  <div class="app-container playback-page">
    <div class="playback-toolbar">
      <div class="toolbar-group">
        <span class="toolbar-label">摄像机</span>
        <el-select v-model="selectedCamera" placeholder="请选择摄像机" filterable clearable style="width:200px" @change="fetchRecordings">
          <el-option v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
      <div class="toolbar-group">
        <span class="toolbar-label">时间范围</span>
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width:380px"
        />
      </div>
      <el-button type="primary" icon="Search" :disabled="!selectedCamera" @click="fetchRecordings">搜索</el-button>
    </div>

    <div class="playback-main">
      <div class="playback-player">
        <video
          v-if="currentVideoUrl"
          ref="videoRef"
          :src="currentVideoUrl"
          controls
          class="player-video"
          autoplay
        ></video>
        <div v-else class="player-placeholder">
          <el-icon :size="48" color="#999"><VideoCamera /></el-icon>
          <p>选择摄像机和时间范围后搜索录像</p>
        </div>
      </div>

      <div class="playback-timeline">
        <div class="timeline-header">
          <div class="timeline-header-left">
            <el-icon><Timer /></el-icon>
            <span class="font-bold">录像时间轴</span>
            <el-tag v-if="recordings.length" size="small">{{ recordings.length }}段</el-tag>
          </div>
          <el-radio-group v-model="timelineHours" size="small">
            <el-radio-button :value="1">1小时</el-radio-button>
            <el-radio-button :value="2">2小时</el-radio-button>
            <el-radio-button :value="4">4小时</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="recordings.length > 0" class="timeline-body">
          <div class="timeline-ruler">
            <div v-for="i in timelineHours" :key="i" class="ruler-hour">
              <span class="ruler-hour-label">{{ String(i - 1).padStart(2, '0') }}:00</span>
            </div>
          </div>
          <div class="timeline-tracks">
            <div class="timeline-track">
              <div
                v-for="r in recordings"
                :key="r.id"
                class="track-segment"
                :class="r.record_type === 'ALARM' ? 'alarm' : 'continuous'"
                :style="segmentStyle(r)"
                @click="playRecording(r)"
              >
                {{ r.start_time?.substring(11, 19) }}-{{ r.end_time?.substring(11, 19) }}
              </div>
            </div>
          </div>
        </div>
        <div v-else class="timeline-empty">
          <el-empty :image-size="40" description="暂无录像数据" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, VideoCamera, Timer } from '@element-plus/icons-vue'
import { getCameraList } from '@/api/module_video/camera'

const cameras = ref<any[]>([])
const selectedCamera = ref<number | null>(null)
const dateRange = ref<[string, string]>(['', ''])
const timelineHours = ref(2)
const recordings = ref<any[]>([])
const currentVideoUrl = ref('')
const videoRef = ref<HTMLVideoElement>()

function segmentStyle(r: any) {
  if (!r.start_time || !r.end_time || !dateRange.value[0]) return {}
  const rangeStart = new Date(dateRange.value[0]).getTime()
  const rangeEnd = dateRange.value[1] ? new Date(dateRange.value[1]).getTime() : rangeStart + timelineHours.value * 3600000
  const recordStart = new Date(r.start_time).getTime()
  const recordEnd = new Date(r.end_time).getTime()
  const rangeDuration = rangeEnd - rangeStart
  if (rangeDuration <= 0) return { display: 'none' }
  const left = ((recordStart - rangeStart) / rangeDuration) * 100
  const width = ((recordEnd - recordStart) / rangeDuration) * 100
  return {
    left: `${Math.max(0, left)}%`,
    width: `${Math.min(width, 100 - Math.max(0, left))}%`,
  }
}

function playRecording(r: any) {
  currentVideoUrl.value = r.file_path || ''
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 1000 })
    cameras.value = res.data?.items || []
  } catch {}
}

async function fetchRecordings() {
  if (!selectedCamera.value) return
  recordings.value = []
}

fetchCameras()
</script>

<style scoped>
.playback-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  overflow: hidden;
}

.playback-toolbar {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  align-items: center;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.playback-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.playback-player {
  flex: 1;
  background: #0a0a0a;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  position: relative;
}

.player-video {
  max-width: 100%;
  max-height: 100%;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.player-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #666;
  font-size: 14px;
}

.playback-timeline {
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.timeline-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.timeline-body {
  padding: 8px 16px 16px;
  overflow-x: auto;
}

.timeline-ruler {
  display: flex;
  height: 24px;
  border-bottom: 1px solid var(--el-border-color-light);
  margin-bottom: 4px;
}

.ruler-hour {
  flex: 1;
  position: relative;
  border-left: 1px solid var(--el-border-color-light);
}

.ruler-hour:first-child {
  border-left: none;
}

.ruler-hour-label {
  position: absolute;
  top: 4px;
  left: 4px;
  font-size: 11px;
  color: #999;
}

.timeline-tracks {
  min-height: 40px;
  position: relative;
}

.timeline-track {
  height: 36px;
  position: relative;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  overflow: hidden;
}

.track-segment {
  position: absolute;
  height: 100%;
  border-radius: 4px;
  padding: 0 8px;
  font-size: 11px;
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: opacity 0.2s;
}

.track-segment:hover {
  opacity: 0.85;
}

.track-segment.continuous {
  background: rgba(64, 158, 255, 0.65);
}

.track-segment.alarm {
  background: rgba(245, 108, 108, 0.75);
}

.timeline-empty {
  padding: 16px;
  display: flex;
  justify-content: center;
}
</style>
