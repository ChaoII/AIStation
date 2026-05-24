<template>
  <div class="app-container playback-page">
    <div class="playback-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="devicePanelOpen = !devicePanelOpen">
          <el-icon>
            <Fold v-if="devicePanelOpen" />
            <Expand v-else />
          </el-icon>
        </el-button>
        <el-select
          v-model="selectedCamera"
          placeholder="选择摄像机"
          filterable
          clearable
          style="width: 180px"
          size="small"
        >
          <el-option v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </div>
      <div class="toolbar-center">
        <el-date-picker
          v-model="searchDate"
          type="date"
          placeholder="选择日期"
          size="small"
          style="width: 140px"
          value-format="YYYY-MM-DD"
        />
        <el-time-picker
          v-model="searchStartTime"
          placeholder="开始"
          size="small"
          style="width: 110px"
          value-format="HH:mm:ss"
          format="HH:mm"
        />
        <span class="time-sep">-</span>
        <el-time-picker
          v-model="searchEndTime"
          placeholder="结束"
          size="small"
          style="width: 110px"
          value-format="HH:mm:ss"
          format="HH:mm"
        />
        <el-button size="small" type="primary" :disabled="!selectedCamera" @click="handleSearch">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="recordings.length" size="small" effect="plain">
          {{ recordings.length }} 段录像
        </el-tag>
      </div>
    </div>

    <div class="playback-main">
      <div v-show="devicePanelOpen" class="playback-device-panel">
        <div class="panel-header">
          <el-icon :size="14"><FolderOpened /></el-icon>
          <span>设备列表</span>
        </div>
        <div class="panel-search">
          <el-input
            v-model="deviceSearch"
            size="small"
            placeholder="搜索..."
            clearable
            :prefix-icon="Search"
          />
        </div>
        <el-tree
          ref="deviceTreeRef"
          :data="deviceTreeData"
          :props="{ children: 'children', label: 'label' }"
          node-key="id"
          default-expand-all
          highlight-current
          class="device-tree"
          @node-click="onDeviceNodeClick"
        >
          <template #default="{ data }">
            <div
              v-if="data.type === 'camera'"
              class="tree-camera-node"
              @dblclick="selectAndSearch(data.camera)"
            >
              <span class="device-status-dot" :class="statusClass(data.camera.status)" />
              <span class="tree-camera-name">{{ data.camera.name }}</span>
            </div>
            <div v-else class="tree-group-node">
              <el-icon :size="14"><FolderOpened /></el-icon>
              <span>{{ data.label }}</span>
              <span class="tree-count">{{ data.cameraCount || 0 }}</span>
            </div>
          </template>
        </el-tree>
      </div>

      <div class="playback-content">
        <div class="playback-player">
          <video
            v-if="currentVideoUrl"
            ref="videoRef"
            :src="currentVideoUrl"
            class="player-video"
            autoplay
            @timeupdate="onTimeUpdate"
            @loadedmetadata="onLoadedMetadata"
            @ended="onVideoEnded"
          />
          <div v-else class="player-placeholder">
            <el-icon :size="48" color="#555"><VideoCamera /></el-icon>
            <p>选择摄像机与日期后搜索录像</p>
          </div>
          <div class="player-controls">
            <div class="controls-left">
              <el-button-group>
                <el-tooltip content="上一段">
                  <el-button size="small" :disabled="!currentVideoUrl" @click="seekPrev">
                    <el-icon><DArrowLeft /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-tooltip content="快退">
                  <el-button size="small" :disabled="!currentVideoUrl" @click="stepBackward">
                    <el-icon><Back /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-button
                  size="small"
                  type="primary"
                  :disabled="!currentVideoUrl"
                  @click="togglePlay"
                >
                  <el-icon>
                    <VideoPlay v-if="!isPlaying" />
                    <VideoPause v-else />
                  </el-icon>
                </el-button>
                <el-tooltip content="快进">
                  <el-button size="small" :disabled="!currentVideoUrl" @click="stepForward">
                    <el-icon><Right /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-tooltip content="下一段">
                  <el-button size="small" :disabled="!currentVideoUrl" @click="seekNext">
                    <el-icon><DArrowRight /></el-icon>
                  </el-button>
                </el-tooltip>
              </el-button-group>
            </div>
            <div class="controls-center">
              <span class="time-display">{{ currentTimeStr }} / {{ durationStr }}</span>
            </div>
            <div class="controls-right">
              <el-select
                v-model="playbackSpeed"
                size="small"
                style="width: 80px"
                :disabled="!currentVideoUrl"
              >
                <el-option v-for="s in speeds" :key="s" :label="`${s}x`" :value="s" />
              </el-select>
              <div class="volume-control">
                <el-icon :size="14"><VideoCamera /></el-icon>
                <el-slider v-model="volume" size="small" :max="100" :min="0" style="width: 60px" />
              </div>
            </div>
          </div>
        </div>

        <div class="playback-timeline">
          <div class="timeline-controls">
            <div class="timeline-scale">
              <button
                v-for="z in zoomLevels"
                :key="z.value"
                class="scale-btn"
                :class="{ active: timelineZoom === z.value }"
                @click="timelineZoom = z.value"
              >
                {{ z.label }}
              </button>
            </div>
            <div class="timeline-info">
              <span v-if="currentRecording" class="recording-info">
                {{ currentRecording.start_time }} - {{ currentRecording.end_time }}
              </span>
            </div>
          </div>
          <div ref="timelineRef" class="timeline-canvas" @click="onTimelineClick">
            <div class="timeline-ruler">
              <div
                v-for="(h, i) in rulerHours"
                :key="i"
                class="ruler-cell"
                :style="{ width: rulerCellWidth + 'px' }"
              >
                <span class="ruler-label">{{ formatHour(h) }}</span>
                <div class="ruler-tick" />
              </div>
            </div>
            <div class="timeline-track-area">
              <div v-if="hasRecordings" class="timeline-track">
                <div
                  v-for="r in recordings"
                  :key="r.id"
                  class="track-segment"
                  :class="r.record_type === 'ALARM' ? 'alarm' : 'continuous'"
                  :style="getSegmentStyle(r)"
                  @click.stop="seekTo(r)"
                />
              </div>
              <div v-else class="timeline-empty-msg">暂无录像</div>
            </div>
            <div
              v-if="currentVideoUrl"
              class="timeline-playhead"
              :style="{ left: playheadPercent + '%' }"
            >
              <div class="playhead-line" />
              <div class="playhead-head" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue";
import {
  Search,
  Fold,
  Expand,
  FolderOpened,
  VideoCamera,
  DArrowLeft,
  DArrowRight,
  Back,
  Right,
  VideoPlay,
  VideoPause,
} from "@element-plus/icons-vue";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import { getRecordFileList } from "@/api/module_video/record";

const cameras = ref<any[]>([]);
const groupList = ref<any[]>([]);
const selectedCamera = ref<number | null>(null);
const devicePanelOpen = ref(true);
const deviceSearch = ref("");
const deviceTreeRef = ref<any>(null);

const searchDate = ref("");
const searchStartTime = ref("00:00:00");
const searchEndTime = ref("23:59:59");
const recordings = ref<any[]>([]);
const currentVideoUrl = ref("");
const currentRecording = ref<any>(null);
const isPlaying = ref(false);
const playbackSpeed = ref(1);
const volume = ref(80);
const currentTime = ref(0);
const duration = ref(0);
const timelineZoom = ref(1);

const videoRef = ref<HTMLVideoElement | null>(null);
const timelineRef = ref<HTMLElement | null>(null);

const speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 4, 8];
const zoomLevels = [
  { value: 0.5, label: "4h" },
  { value: 1, label: "2h" },
  { value: 2, label: "1h" },
  { value: 4, label: "30m" },
];

function statusClass(status: string) {
  switch (status) {
    case "ONLINE":
      return "status-online";
    case "OFFLINE":
      return "status-offline";
    default:
      return "status-unknown";
  }
}

const currentTimeStr = computed(() => formatSeconds(currentTime.value));
const durationStr = computed(() => formatSeconds(duration.value));

const rulerHours = computed(() => {
  const count = Math.ceil(visibleHours.value);
  return Array.from({ length: count }, (_, i) => i);
});

const visibleHours = computed(() => {
  switch (timelineZoom.value) {
    case 0.5:
      return 4;
    case 1:
      return 2;
    case 2:
      return 1;
    case 4:
      return 0.5;
    default:
      return 2;
  }
});

const rulerCellWidth = computed(() => {
  const zoom = timelineZoom.value;
  // Each hour gets more pixels as zoom increases
  return zoom <= 0.5 ? 100 : zoom <= 1 ? 160 : zoom <= 2 ? 240 : 320;
});

const hasRecordings = computed(() => recordings.value.length > 0);

const playheadPercent = computed(() => {
  if (duration.value <= 0 || !currentRecording.value) return 0;
  const elapsed = currentTime.value * 1000;
  const total = duration.value * 1000;
  return total > 0 ? (elapsed / total) * 100 : 0;
});

function formatHour(h: number) {
  return `${String(h).padStart(2, "0")}:00`;
}

function formatSeconds(s: number) {
  if (!s || isNaN(s)) return "00:00:00";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function getSearchStartMs(): number {
  if (!searchDate.value) return Date.now() - 7200000;
  const startTime = searchStartTime.value || "00:00:00";
  return new Date(`${searchDate.value} ${startTime}`).getTime();
}

function getSearchEndMs(): number {
  if (!searchDate.value) return Date.now();
  const endTime = searchEndTime.value || "23:59:59";
  return new Date(`${searchDate.value} ${endTime}`).getTime();
}

function getSegmentStyle(r: any) {
  const rangeStart = getSearchStartMs();
  const rangeEnd = getSearchEndMs();
  const rangeDuration = rangeEnd - rangeStart;
  if (rangeDuration <= 0) return { display: "none" };

  const recordStart = new Date(r.start_time).getTime();
  const recordEnd = new Date(r.end_time).getTime();
  const left = ((recordStart - rangeStart) / rangeDuration) * 100;
  const width = ((recordEnd - recordStart) / rangeDuration) * 100;
  return {
    left: `${Math.max(0, Math.min(100, left))}%`,
    width: `${Math.max(0.5, Math.min(width, 100 - Math.max(0, left)))}%`,
  };
}

// Device tree
const deviceTreeData = computed(() => {
  const q = deviceSearch.value.toLowerCase();
  const camMap = new Map<number | undefined, any[]>();
  for (const c of cameras.value) {
    if (q && !c.name.toLowerCase().includes(q)) continue;
    const gid = c.group_id;
    if (!camMap.has(gid)) camMap.set(gid, []);
    camMap.get(gid)!.push(c);
  }

  function buildGroupTree(nodes: any[]): any[] {
    return nodes.map((g) => {
      const gCameras = camMap.get(g.id) || [];
      const children: any[] = [];
      if (g.children?.length) children.push(...buildGroupTree(g.children));
      for (const c of gCameras) {
        children.push({ id: `cam-${c.id}`, label: c.name, type: "camera", camera: c });
      }
      return {
        id: `group-${g.id}`,
        label: g.name,
        type: "group",
        cameraCount: gCameras.length,
        children,
      };
    });
  }

  const ungrouped = (camMap.get(undefined) || []).map((c: any) => ({
    id: `cam-${c.id}`,
    label: c.name,
    type: "camera",
    camera: c,
  }));
  const treeChildren = buildGroupTree(groupList.value);
  if (ungrouped.length) {
    treeChildren.push({
      id: "ungrouped",
      label: "未分组",
      type: "group",
      cameraCount: ungrouped.length,
      children: ungrouped,
    });
  }
  return [
    {
      id: "root",
      label: "所有设备",
      type: "root",
      cameraCount: cameras.value.length,
      children: treeChildren,
    },
  ];
});

function onDeviceNodeClick(data: any) {
  if (data.type === "camera") {
    selectAndSearch(data.camera);
  }
}

function selectAndSearch(camera: any) {
  selectedCamera.value = camera.id;
  handleSearch();
}

// Playback controls
function togglePlay() {
  const video = videoRef.value;
  if (!video) return;
  if (video.paused) {
    video.play();
    isPlaying.value = true;
  } else {
    video.pause();
    isPlaying.value = false;
  }
}

function stepForward() {
  const video = videoRef.value;
  if (video) video.currentTime = Math.min(video.duration, video.currentTime + 30);
}

function stepBackward() {
  const video = videoRef.value;
  if (video) video.currentTime = Math.max(0, video.currentTime - 30);
}

function seekPrev() {
  // Jump to previous recording segment
  const idx = recordings.value.findIndex((r: any) => r.id === currentRecording.value?.id);
  if (idx > 0) seekTo(recordings.value[idx - 1]);
}

function seekNext() {
  const idx = recordings.value.findIndex((r: any) => r.id === currentRecording.value?.id);
  if (idx >= 0 && idx < recordings.value.length - 1) seekTo(recordings.value[idx + 1]);
}

function seekTo(r: any) {
  currentRecording.value = r;
  currentVideoUrl.value = r.file_path || r.stream_url || "";
  isPlaying.value = true;
  nextTick(() => {
    const video = videoRef.value;
    if (video) {
      video.playbackRate = playbackSpeed.value;
      video.play();
    }
  });
}

function onTimeUpdate() {
  const video = videoRef.value;
  if (video) currentTime.value = video.currentTime;
}

function onLoadedMetadata() {
  const video = videoRef.value;
  if (video) {
    duration.value = video.duration;
    video.playbackRate = playbackSpeed.value;
    video.play();
    isPlaying.value = true;
  }
}

function onVideoEnded() {
  isPlaying.value = false;
  // Auto-play next segment
  seekNext();
}

function onTimelineClick(e: MouseEvent) {
  const rect = timelineRef.value?.getBoundingClientRect();
  if (!rect) return;
  const x = e.clientX - rect.left;
  const pct = x / rect.width;
  // Seek within current recording
  const video = videoRef.value;
  if (video && currentRecording.value) {
    video.currentTime = pct * video.duration;
  }
}

// Data fetching
async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameras.value = res.data?.data?.items || [];
  } catch {
    /* noop */
  }
}

async function fetchGroups() {
  try {
    const res = await getCameraGroupList();
    groupList.value = res.data?.data || [];
  } catch {
    /* noop */
  }
}

async function handleSearch() {
  if (!selectedCamera.value || !searchDate.value) return;
  const startTime = `${searchDate.value} ${searchStartTime.value || "00:00:00"}`;
  const endTime = `${searchDate.value} ${searchEndTime.value || "23:59:59"}`;
  const params: any = {
    page_size: 100,
    camera_id: selectedCamera.value,
    start_time: startTime,
    end_time: endTime,
  };
  try {
    const res = await getRecordFileList(params);
    recordings.value = res.data?.data?.items || [];
    if (recordings.value.length > 0) {
      seekTo(recordings.value[0]);
    } else {
      currentVideoUrl.value = "";
      currentRecording.value = null;
    }
  } catch {
    recordings.value = [];
  }
}

// Watch speed change
watch(playbackSpeed, (val) => {
  const video = videoRef.value;
  if (video) video.playbackRate = val;
});

watch(volume, (val) => {
  const video = videoRef.value;
  if (video) video.volume = val / 100;
});

onMounted(() => {
  fetchCameras();
  fetchGroups();
  // Default: today
  const now = new Date();
  searchDate.value = now.toISOString().slice(0, 10);
});
</script>

<style scoped>
.playback-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  overflow: hidden;
}

/* ==================== Toolbar ==================== */
.playback-toolbar {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.toolbar-center {
  flex: 1;
  justify-content: center;
}

.time-sep {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
}

/* ==================== Main Layout ==================== */
.playback-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ==================== Device Panel ==================== */
.playback-device-panel {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 200px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border-right: 1px solid var(--el-border-color-light);
}

.panel-header {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: center;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid var(--el-border-color-light);
}

.panel-search {
  flex-shrink: 0;
  padding: 6px 8px;
}
.panel-search :deep(.el-input__wrapper) {
  background: var(--el-fill-color);
  box-shadow: 0 0 0 1px var(--el-border-color) inset;
}

.device-tree {
  flex: 1;
  overflow-y: auto;
  background: transparent;
}
.device-tree::-webkit-scrollbar {
  width: 4px;
}
.device-tree::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 2px;
}
.device-tree::-webkit-scrollbar-track {
  background: transparent;
}
.device-tree :deep(.el-tree-node__content) {
  height: 28px;
  padding: 0 6px;
}
.device-tree :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color);
}

.tree-camera-node {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  font-size: 13px;
  cursor: pointer;
}
.tree-camera-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-group-node {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  font-size: 13px;
}
.device-status-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-online {
  background: var(--el-color-success);
}
.status-offline {
  background: var(--el-color-info);
}
.status-unknown {
  background: var(--el-color-warning);
}
.tree-count {
  padding: 0 6px;
  margin-left: auto;
  font-size: 11px;
  line-height: 18px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color);
  border-radius: 8px;
}

/* ==================== Playback Content ==================== */
.playback-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}

/* ==================== Player ==================== */
.playback-player {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 200px;
  background: #000;
}

.player-video {
  display: block;
  flex: 1;
  width: 100%;
  object-fit: contain;
}

.player-placeholder {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #555;
}

.player-controls {
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  background: rgba(20, 20, 20, 0.95);
}

.controls-left,
.controls-center,
.controls-right {
  display: flex;
  gap: 6px;
  align-items: center;
}

.controls-left :deep(.el-button) {
  --el-button-bg-color: transparent;
  --el-button-border-color: transparent;
  --el-button-text-color: #ccc;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.1);
  --el-button-hover-border-color: transparent;
  --el-button-active-bg-color: rgba(255, 255, 255, 0.15);
}

.controls-left :deep(.el-button--primary) {
  --el-button-bg-color: var(--el-color-primary);
  --el-button-text-color: #fff;
}

.time-display {
  font-family: "SF Mono", "Cascadia Code", monospace;
  font-size: 13px;
  color: #ccc;
  letter-spacing: 0.5px;
}

.controls-right :deep(.el-select) {
  --el-select-bg-color: rgba(255, 255, 255, 0.08);
  --el-select-border-color-hover: rgba(255, 255, 255, 0.2);
  --el-select-input-color: #ccc;
}

.volume-control {
  display: flex;
  gap: 6px;
  align-items: center;
  color: #999;
}

.volume-control :deep(.el-slider__runway) {
  height: 3px;
  background: rgba(255, 255, 255, 0.15);
}
.volume-control :deep(.el-slider__bar) {
  height: 3px;
  background: #409eff;
}
.volume-control :deep(.el-slider__button) {
  width: 10px;
  height: 10px;
  border-color: #409eff;
}

/* ==================== Timeline ==================== */
.playback-timeline {
  flex-shrink: 0;
  background: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-light);
}

.timeline-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.timeline-scale {
  display: flex;
  gap: 4px;
}

.scale-btn {
  padding: 2px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 3px;
  transition: all 0.15s;
}
.scale-btn:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
.scale-btn.active {
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 10%, transparent);
  border-color: var(--el-color-primary);
}

.timeline-info {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.recording-info {
  font-family: "SF Mono", "Cascadia Code", monospace;
  font-size: 12px;
}

.timeline-canvas {
  position: relative;
  padding: 4px 16px 20px;
  overflow-x: auto;
  cursor: pointer;
  user-select: none;
}

.timeline-ruler {
  display: flex;
  height: 24px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.ruler-cell {
  position: relative;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color-lighter);
}

.ruler-label {
  position: absolute;
  top: 4px;
  left: 4px;
  font-family: "SF Mono", "Cascadia Code", monospace;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.ruler-tick {
  position: absolute;
  bottom: 0;
  left: 30%;
  width: 1px;
  height: 6px;
  background: var(--el-border-color-lighter);
}

.timeline-track-area {
  position: relative;
  min-height: 36px;
}

.timeline-track {
  position: relative;
  height: 32px;
  overflow: hidden;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.track-segment {
  position: absolute;
  min-width: 2px;
  height: 100%;
  cursor: pointer;
  border-radius: 3px;
  transition: opacity 0.15s;
}
.track-segment:hover {
  opacity: 0.8;
}
.track-segment.continuous {
  background: rgba(64, 158, 255, 0.55);
}
.track-segment.alarm {
  background: rgba(245, 108, 108, 0.65);
}

.timeline-empty-msg {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.timeline-playhead {
  position: absolute;
  top: 4px;
  bottom: 20px;
  z-index: 2;
  pointer-events: none;
  transition: left 0.3s;
}

.playhead-line {
  position: absolute;
  top: 24px;
  bottom: 0;
  left: 50%;
  width: 2px;
  background: #f56c6c;
  transform: translateX(-50%);
}

.playhead-head {
  position: absolute;
  top: 22px;
  left: 50%;
  width: 10px;
  height: 10px;
  background: #f56c6c;
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transform: translateX(-50%);
}
</style>
