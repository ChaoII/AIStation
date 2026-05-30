<template>
  <div class="pb-page">
    <!-- ====== Top Bar ====== -->
    <header class="pb-topbar">
      <div class="topbar-brand">
        <span class="brand-dot" />
        <span class="brand-text">录像回放</span>
      </div>

      <span class="topbar-sep" />

      <el-tooltip :content="devicePanelOpen ? '隐藏设备面板' : '显示设备面板'" placement="bottom">
        <button
          class="layout-btn"
          :class="{ active: devicePanelOpen }"
          @click="devicePanelOpen = !devicePanelOpen"
        >
          <el-icon><FolderOpened /></el-icon>
        </button>
      </el-tooltip>

      <div class="topbar-center">
        <div class="search-group">
          <div class="field-row">
            <el-date-picker
              v-model="searchDate"
              type="date"
              placeholder="选择日期"
              size="small"
              value-format="YYYY-MM-DD"
              class="field-date"
            />
            <el-time-picker
              v-model="searchStartTime"
              placeholder="开始"
              size="small"
              value-format="HH:mm:ss"
              format="HH:mm"
              class="field-time"
            />
            <span class="time-sep">—</span>
            <el-time-picker
              v-model="searchEndTime"
              placeholder="结束"
              size="small"
              value-format="HH:mm:ss"
              format="HH:mm"
              class="field-time"
            />
            <el-button
              size="small"
              type="primary"
              :disabled="!selectedCamera"
              @click="handleSearch"
            >
              <el-icon><Search /></el-icon>
              搜索
            </el-button>
          </div>
        </div>
      </div>

      <div class="topbar-right">
        <span v-if="recordings.length" class="rec-count-badge">{{ recordings.length }} 段</span>
      </div>
    </header>

    <!-- ====== Main Area ====== -->
    <div class="pb-body">
      <!-- Sidebar -->
      <aside v-show="devicePanelOpen" class="live-device-panel">
        <div class="panel-header">
          <el-icon :size="14"><FolderOpened /></el-icon>
          <span>设备列表</span>
        </div>
        <div class="tree-filter">
          <el-input
            v-model="deviceSearch"
            size="small"
            placeholder="搜索设备..."
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
              <span class="dot" :class="data.camera.status === 'ONLINE' ? 'dot-on' : 'dot-off'" />
              <span class="tree-camera-name">{{ data.camera.name }}</span>
            </div>
            <div v-else class="tree-camera-node" style="color: var(--el-text-color-secondary)">
              <el-icon :size="14"><FolderOpened /></el-icon>
              <span>{{ data.label }}</span>
              <span class="tree-count">{{ data.cameraCount || 0 }}</span>
            </div>
          </template>
        </el-tree>
      </aside>

      <!-- Main Content -->
      <div class="pb-content">
        <!-- Player -->
        <div class="pb-player">
          <video
            v-if="currentVideoUrl && !useFlv"
            ref="videoRef"
            autoplay
            playsinline
            class="player-video"
            @timeupdate="onTimeUpdate"
            @loadedmetadata="onLoadedMetadata"
            @ended="onVideoEnded"
            @error="onVideoError"
          />
          <div v-else-if="currentVideoUrl && useFlv" ref="flvContainerRef" class="player-flv-wrap">
            <video ref="flvVideoRef" autoplay playsinline muted class="player-video" />
          </div>

          <!-- Placeholder -->
          <div v-else class="player-empty">
            <div class="empty-icon">
              <svg
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                opacity="0.4"
              >
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <p class="empty-text">选择摄像机与时间后搜索录像</p>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="player-loading"><div class="spinner" /></div>

          <!-- Info bar -->
          <div v-if="currentRecording" class="player-info">
            <span class="info-cam">
              {{ currentRecording.camera_name || `#${currentRecording.camera_id}` }}
            </span>
            <span class="info-sep" />
            <span class="info-time">
              {{ formatDateTime(currentRecording.start_time) }} —
              {{ formatDateTime(currentRecording.end_time) }}
            </span>
            <span v-if="currentRecording.record_type === 'ALARM'" class="info-alarm">告警录制</span>
          </div>

          <!-- Controls overlay -->
          <div v-if="currentRecording" class="player-ctrl" @click.stop>
            <div class="ctrl-bg" />
            <div class="ctrl-inner">
              <div class="ctrl-group ctrl-left">
                <button
                  class="ctrl-btn"
                  title="上一段"
                  :disabled="!currentRecording"
                  @click="seekPrev"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="19 20 9 12 19 4" />
                    <line x1="5" y1="4" x2="5" y2="20" />
                  </svg>
                </button>
                <button
                  class="ctrl-btn"
                  title="后退30s"
                  :disabled="!currentRecording"
                  @click="stepBackward"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="1 4 1 10 7 10" />
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                </button>
                <button
                  class="ctrl-btn ctrl-play"
                  :disabled="!currentRecording"
                  @click="togglePlay"
                >
                  <svg
                    v-if="!isPlaying"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  >
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="4" width="4" height="16" />
                    <rect x="14" y="4" width="4" height="16" />
                  </svg>
                </button>
                <button
                  class="ctrl-btn"
                  title="前进30s"
                  :disabled="!currentRecording"
                  @click="stepForward"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="23 4 23 10 17 10" />
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                  </svg>
                </button>
                <button
                  class="ctrl-btn"
                  title="下一段"
                  :disabled="!currentRecording"
                  @click="seekNext"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="5 4 15 12 5 20" />
                    <line x1="19" y1="4" x2="19" y2="20" />
                  </svg>
                </button>
              </div>

              <div class="ctrl-group ctrl-center">
                <span class="ctrl-time">{{ currentTimeStr }}</span>
                <span class="ctrl-time-sep">/</span>
                <span class="ctrl-time ctrl-dur">{{ durationStr }}</span>
              </div>

              <div class="ctrl-group ctrl-right">
                <div class="ctrl-speed">
                  <select
                    v-model="playbackSpeed"
                    :disabled="!currentRecording"
                    class="speed-select"
                  >
                    <option v-for="s in speeds" :key="s" :value="s">{{ s }}x</option>
                  </select>
                </div>
                <div class="ctrl-vol">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
                  </svg>
                  <input
                    v-model.number="volume"
                    type="range"
                    min="0"
                    max="100"
                    class="vol-slider"
                  />
                </div>
                <button
                  class="ctrl-btn"
                  title="全屏"
                  :disabled="!currentRecording"
                  @click="toggleFullscreen"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="15 3 21 3 21 9" />
                    <polyline points="9 21 3 21 3 15" />
                    <line x1="21" y1="3" x2="14" y2="10" />
                    <line x1="3" y1="21" x2="10" y2="14" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Timeline -->
        <div class="pb-timeline">
          <div class="tl-bar">
            <div class="tl-zoom">
              <button
                v-for="z in zoomLevels"
                :key="z.value"
                class="tl-zbtn"
                :class="{ active: timelineZoom === z.value }"
                @click="timelineZoom = z.value"
              >
                {{ z.label }}
              </button>
            </div>
            <div class="tl-range">
              {{ searchStartTime || "00:00" }} — {{ searchEndTime || "24:00" }}
            </div>
          </div>

          <div ref="timelineRef" class="tl-track-wrap" @click="onTimelineClick">
            <div class="tl-ruler">
              <div
                v-for="(h, i) in rulerHours"
                :key="i"
                class="tl-ruler-cell"
                :style="{ width: rulerCellWidth + 'px' }"
              >
                <span class="tl-ruler-label">{{ formatHour(h) }}</span>
              </div>
            </div>

            <div class="tl-body">
              <div v-if="hasRecordings" class="tl-track">
                <div
                  v-for="r in recordings"
                  :key="r.id"
                  class="tl-seg"
                  :class="[
                    r.record_type === 'ALARM' ? 'seg-alarm' : 'seg-ok',
                    { 'seg-active': currentRecording?.id === r.id },
                  ]"
                  :style="getSegmentStyle(r)"
                  :title="`${formatDateTime(r.start_time)} — ${formatDateTime(r.end_time)}`"
                  @click.stop="seekTo(r)"
                />
              </div>
              <div v-else-if="hasSearched" class="tl-empty">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                该时段无录像
              </div>
              <div v-else class="tl-empty tl-empty-idle">选择摄像机后搜索</div>
            </div>

            <div
              v-if="currentRecording"
              class="tl-playhead"
              :style="{ left: playheadPercent + '%' }"
            >
              <div class="tl-ph-line" />
              <div class="tl-ph-dot" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { Search, FolderOpened } from "@element-plus/icons-vue";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import { getRecordFileList, getRecordFilePlayUrl } from "@/api/module_video/record";

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
const hasSearched = ref(false);
const loading = ref(false);
const currentRecording = ref<any>(null);
const currentVideoUrl = ref("");
const useFlv = ref(false);
const isPlaying = ref(false);
const playbackSpeed = ref(1);
const volume = ref(80);
const currentTime = ref(0);
const duration = ref(0);
const timelineZoom = ref(1);

const videoRef = ref<HTMLVideoElement | null>(null);
const flvContainerRef = ref<HTMLDivElement | null>(null);
const flvVideoRef = ref<HTMLVideoElement | null>(null);
const timelineRef = ref<HTMLElement | null>(null);

let mpegtsPlayer: any = null;

const speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 4, 8];
const zoomLevels = [
  { value: 0.5, label: "4h" },
  { value: 1, label: "2h" },
  { value: 2, label: "1h" },
  { value: 4, label: "30m" },
];

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
  const z = timelineZoom.value;
  return z <= 0.5 ? 120 : z <= 1 ? 200 : z <= 2 ? 300 : 440;
});

const hasRecordings = computed(() => recordings.value.length > 0);

const playheadPercent = computed(() => {
  if (duration.value <= 0 || !currentRecording.value) return 0;
  return duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0;
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

function formatDateTime(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((v) => String(v).padStart(2, "0"))
    .join(":");
}

function getSearchStartMs(): number {
  if (!searchDate.value) return Date.now() - 7200000;
  return new Date(`${searchDate.value} ${searchStartTime.value || "00:00:00"}`).getTime();
}

function getSearchEndMs(): number {
  if (!searchDate.value) return Date.now();
  return new Date(`${searchDate.value} ${searchEndTime.value || "23:59:59"}`).getTime();
}

function getSegmentStyle(r: any) {
  const rangeStart = getSearchStartMs();
  const rangeEnd = getSearchEndMs();
  const rangeDuration = rangeEnd - rangeStart;
  if (rangeDuration <= 0) return { display: "none" };
  const rs = new Date(r.start_time).getTime();
  const re = new Date(r.end_time).getTime();
  const left = ((rs - rangeStart) / rangeDuration) * 100;
  const width = ((re - rs) / rangeDuration) * 100;
  return {
    left: `${Math.max(0, Math.min(100, left))}%`,
    width: `${Math.max(0.5, Math.min(width, 100 - Math.max(0, left)))}%`,
  };
}

// Device tree data
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
    return nodes.map((g: any) => {
      const gc = camMap.get(g.id) || [];
      const children: any[] = [];
      if (g.children?.length) children.push(...buildGroupTree(g.children));
      for (const c of gc) {
        children.push({ id: `cam-${c.id}`, label: c.name, type: "camera", camera: c });
      }
      return {
        id: `group-${g.id}`,
        label: g.name,
        type: "group",
        cameraCount: gc.length,
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
  if (data.type === "camera") selectAndSearch(data.camera);
}

function selectAndSearch(camera: any) {
  selectedCamera.value = camera.id;
  handleSearch();
}

function destroyMpegtsPlayer() {
  if (mpegtsPlayer) {
    try {
      mpegtsPlayer.destroy();
    } catch {}
    mpegtsPlayer = null;
  }
}

function getVideoEl(): HTMLVideoElement | null {
  return useFlv.value ? flvVideoRef.value : videoRef.value;
}

function togglePlay() {
  const video = getVideoEl();
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
  const video = getVideoEl();
  if (video) video.currentTime = Math.min(video.duration, video.currentTime + 30);
}

function stepBackward() {
  const video = getVideoEl();
  if (video) video.currentTime = Math.max(0, video.currentTime - 30);
}

function seekPrev() {
  const idx = recordings.value.findIndex((r: any) => r.id === currentRecording.value?.id);
  if (idx > 0) seekTo(recordings.value[idx - 1]);
}

function seekNext() {
  const idx = recordings.value.findIndex((r: any) => r.id === currentRecording.value?.id);
  if (idx >= 0 && idx < recordings.value.length - 1) seekTo(recordings.value[idx + 1]);
}

async function seekTo(r: any) {
  currentRecording.value = r;
  loading.value = true;
  useFlv.value = false;
  destroyMpegtsPlayer();
  try {
    const res = await getRecordFilePlayUrl(r.id);
    const playUrl = res.data?.data?.play_url || r.file_path;
    const isFlv = playUrl.endsWith(".flv") || playUrl.includes(".live.flv");
    if (isFlv) {
      useFlv.value = true;
      currentVideoUrl.value = playUrl;
      await nextTick();
      await initMpegtsPlayer(playUrl);
    } else {
      useFlv.value = false;
      currentVideoUrl.value = playUrl;
    }
  } catch {
    currentVideoUrl.value = r.file_path;
    useFlv.value = false;
  }
  loading.value = false;
  isPlaying.value = true;
}

async function initMpegtsPlayer(url: string) {
  destroyMpegtsPlayer();
  const video = flvVideoRef.value;
  if (!video) return;
  try {
    const mod = await import("mpegts.js");
    const mpegts = (mod as any).default || mod;
    if (mpegts.isSupported()) {
      mpegtsPlayer = mpegts.createPlayer(
        { type: "flv", url, isLive: false },
        { enableWorker: false, stashInitialSize: 16, enableStashBuffer: false }
      );
      mpegtsPlayer.attachMediaElement(video);
      mpegtsPlayer.load();
      mpegtsPlayer.play();
      mpegtsPlayer.on(mpegts.Events.ERROR, (e: any) => console.error("mpegts error:", e));
    }
  } catch (e) {
    console.error("mpegts load failed:", e);
  }
}

function onTimeUpdate() {
  const video = getVideoEl();
  if (video) currentTime.value = video.currentTime;
}

function onLoadedMetadata() {
  const video = getVideoEl();
  if (video) {
    duration.value = video.duration;
    video.playbackRate = playbackSpeed.value;
    video.play();
    isPlaying.value = true;
  }
}

function onVideoEnded() {
  isPlaying.value = false;
  seekNext();
}
function onVideoError() {
  loading.value = false;
  isPlaying.value = false;
}

function onTimelineClick(e: MouseEvent) {
  const rect = timelineRef.value?.getBoundingClientRect();
  if (!rect || !currentRecording.value) return;
  const x = e.clientX - rect.left;
  const video = getVideoEl();
  if (video) video.currentTime = (x / rect.width) * video.duration;
}

function toggleFullscreen() {
  const el = flvContainerRef.value || videoRef.value?.parentElement;
  if (!el) return;
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    el.requestFullscreen();
  }
}

async function handleSearch() {
  if (!selectedCamera.value || !searchDate.value) return;
  loading.value = true;
  hasSearched.value = true;
  destroyMpegtsPlayer();
  currentVideoUrl.value = "";
  currentRecording.value = null;
  isPlaying.value = false;
  try {
    const res = await getRecordFileList({
      page_size: 100,
      camera_id: selectedCamera.value,
      start_time: `${searchDate.value} ${searchStartTime.value || "00:00:00"}`,
      end_time: `${searchDate.value} ${searchEndTime.value || "23:59:59"}`,
    });
    recordings.value = res.data?.data?.items || [];
    if (recordings.value.length > 0) await seekTo(recordings.value[0]);
  } catch {
    recordings.value = [];
  }
  loading.value = false;
}

watch(playbackSpeed, (val) => {
  const v = getVideoEl();
  if (v) v.playbackRate = val;
});
watch(volume, (val) => {
  const v = getVideoEl();
  if (v) v.volume = val / 100;
});

onMounted(() => {
  const now = new Date();
  searchDate.value = now.toISOString().slice(0, 10);
  getCameraList({ page_size: 100 })
    .then((r) => {
      cameras.value = r.data?.data?.items || [];
    })
    .catch(() => {});
  getCameraGroupList()
    .then((r) => {
      groupList.value = r.data?.data || [];
    })
    .catch(() => {});
});

onBeforeUnmount(() => {
  destroyMpegtsPlayer();
});
</script>

<style scoped>
/* ================================================================
   PLAYBACK PAGE — System Theme
   ================================================================ */

.pb-page {
  --pb-accent: var(--el-color-primary);
  --pb-accent2: var(--el-color-primary-light-3);
  --pb-red: var(--el-color-danger);
  --pb-font: "SF Mono", "Cascadia Code", "JetBrains Mono", ui-monospace, monospace;

  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 13px;
}

/* ================================================================
   TOPBAR
   ================================================================ */
.pb-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  height: 48px;
  padding: 0 16px;
  background: var(--el-fill-color-blank);
  border-bottom: 1px solid var(--el-border-color-light);
  z-index: 10;
}

.topbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.brand-dot {
  width: 8px;
  height: 8px;
  background: var(--el-color-success);
  border-radius: 50%;
  box-shadow: 0 0 6px color-mix(in srgb, var(--el-color-success) 50%, transparent);
}
.brand-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  letter-spacing: 0.5px;
}

.topbar-sep {
  width: 1px;
  height: 20px;
  background: var(--el-border-color);
  flex-shrink: 0;
}

.layout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  transition: all 0.15s;
}
.layout-btn:hover {
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color-hover);
}
.layout-btn.active {
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 10%, transparent);
  border-color: var(--el-color-primary);
}

.topbar-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.search-group {
  display: flex;
  align-items: center;
}
.field-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.field-row :deep(.el-input__wrapper) {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 4px;
}
.field-row :deep(.el-input__inner) {
  color: var(--el-text-color-primary) !important;
  font-size: 12px;
  height: 28px;
}
.field-date {
  width: 130px;
}
.field-time {
  width: 90px;
}
.time-sep {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  margin: 0 2px;
}

.topbar-right {
  flex-shrink: 0;
}
.rec-count-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
  font-family: var(--pb-font);
  color: var(--pb-accent);
  background: color-mix(in srgb, var(--pb-accent) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--pb-accent) 25%, transparent);
  border-radius: 4px;
}

.pb-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  color: var(--pb-text2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.pb-icon-btn:hover {
  color: var(--pb-text);
  background: var(--pb-border);
  border-color: var(--pb-border2);
}

.pb-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--pb-border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--pb-surface);
  color: var(--pb-text2);
}
.pb-btn:hover {
  border-color: var(--pb-border2);
  color: var(--pb-text);
  background: var(--pb-border);
}
.pb-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.pb-btn-primary {
  background: var(--pb-accent2);
  border-color: var(--pb-accent2);
  color: #fff;
}
.pb-btn-primary:hover {
  background: var(--pb-accent);
  border-color: var(--pb-accent);
  color: #fff;
}
.pb-btn-primary:disabled {
  background: color-mix(in srgb, var(--pb-accent2) 40%, transparent);
  border-color: transparent;
}

/* ================================================================
   BODY
   ================================================================ */
.pb-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ================================================================
   SIDEBAR — matches live preview
   ================================================================ */
.live-device-panel {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 220px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border-right: 1px solid var(--el-border-color-light);
}
.panel-header {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: center;
  min-height: 36px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-light);
}
.tree-filter {
  flex-shrink: 0;
  padding: 6px 8px;
}
.tree-filter :deep(.el-input__wrapper) {
  background: var(--el-fill-color);
  box-shadow: 0 0 0 1px var(--el-border-color) inset;
}
.tree-filter :deep(.el-input__inner) {
  font-size: 12px;
  color: var(--el-text-color-primary);
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
}
.device-tree :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color);
}
.tree-camera-node {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding-right: 4px;
}
.tree-camera-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-on {
  background: var(--el-color-success);
  box-shadow: 0 0 6px color-mix(in srgb, var(--el-color-success) 50%, transparent);
}
.dot-off {
  background: var(--el-text-color-placeholder);
}

/* ================================================================
   MAIN CONTENT
   ================================================================ */
.pb-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  padding: 0 2px;
}

/* ================================================================
   PLAYER
   ================================================================ */
.pb-player {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 240px;
  background: #000;
}

.player-video {
  display: block;
  flex: 1;
  width: 100%;
  object-fit: contain;
  background: #000;
}
.player-flv-wrap {
  display: flex;
  flex: 1;
  width: 100%;
  background: #000;
}

/* Placeholder */
.player-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 12px;
}
.empty-icon svg {
  color: var(--pb-text3);
}
.empty-text {
  margin: 0;
  font-size: 13px;
  color: var(--pb-text3);
  letter-spacing: 0.3px;
}

/* Loading */
.player-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  z-index: 5;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(255, 255, 255, 0.15);
  border-top-color: var(--pb-accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Info bar */
.player-info {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 14px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), transparent);
  pointer-events: none;
}
.info-cam {
  font-weight: 600;
  color: #fff;
}
.info-sep {
  width: 1px;
  height: 12px;
  background: rgba(255, 255, 255, 0.15);
}
.info-time {
  font-family: var(--pb-font);
  font-size: 11px;
}
.info-alarm {
  padding: 1px 7px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  background: var(--pb-red);
  border-radius: 3px;
}

/* Controls overlay */
.player-ctrl {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 4;
}
.ctrl-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    rgba(0, 0, 0, 0.8) 0%,
    rgba(0, 0, 0, 0.3) 60%,
    transparent 100%
  );
  pointer-events: none;
}
.ctrl-inner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 52px;
  padding: 0 16px;
}

.ctrl-group {
  display: flex;
  align-items: center;
  gap: 2px;
}
.ctrl-left {
  flex-shrink: 0;
}
.ctrl-center {
  flex: 1;
  justify-content: center;
  gap: 6px;
}
.ctrl-right {
  flex-shrink: 0;
  gap: 8px;
}

.ctrl-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  color: rgba(255, 255, 255, 0.65);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s;
}
.ctrl-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}
.ctrl-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
.ctrl-btn:disabled:hover {
  background: transparent;
  color: rgba(255, 255, 255, 0.3);
}

.ctrl-play {
  width: 36px;
  height: 36px;
  color: #fff;
  background: var(--pb-accent2);
  border-radius: 50%;
}
.ctrl-play:hover {
  background: var(--pb-accent);
}

.ctrl-time {
  font-family: var(--pb-font);
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
  letter-spacing: 0.5px;
}
.ctrl-dur {
  color: rgba(255, 255, 255, 0.4);
}
.ctrl-time-sep {
  color: rgba(255, 255, 255, 0.2);
  font-size: 12px;
}

.speed-select {
  height: 26px;
  padding: 0 6px;
  font-size: 11px;
  font-family: var(--pb-font);
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  outline: none;
  cursor: pointer;
  appearance: none;
}
.speed-select:hover {
  background: rgba(255, 255, 255, 0.12);
}
.speed-select option {
  background: #222;
  color: #eee;
}

.ctrl-vol {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.5);
}
.vol-slider {
  width: 52px;
  height: 3px;
  appearance: none;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.vol-slider::-webkit-slider-thumb {
  appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  border: none;
  cursor: pointer;
}
.vol-slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  border: none;
  cursor: pointer;
}

/* ================================================================
   TIMELINE
   ================================================================ */
.pb-timeline {
  flex-shrink: 0;
  background: var(--pb-surface);
  border-top: 1px solid var(--pb-border);
}

.tl-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 38px;
  padding: 0 14px;
  border-bottom: 1px solid var(--pb-border);
}

.tl-zoom {
  display: flex;
  gap: 3px;
}
.tl-zbtn {
  padding: 2px 10px;
  font-size: 11px;
  font-family: var(--pb-font);
  color: var(--pb-text3);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 3px;
  transition: all 0.12s;
}
.tl-zbtn:hover {
  color: var(--pb-text);
  border-color: var(--pb-border2);
}
.tl-zbtn.active {
  color: var(--pb-accent);
  background: color-mix(in srgb, var(--pb-accent) 10%, transparent);
  border-color: color-mix(in srgb, var(--pb-accent) 30%, transparent);
}

.tl-range {
  font-family: var(--pb-font);
  font-size: 11px;
  color: var(--pb-text3);
}

.tl-track-wrap {
  position: relative;
  padding: 6px 14px 22px;
  overflow-x: auto;
  cursor: pointer;
  user-select: none;
}
.tl-track-wrap::-webkit-scrollbar {
  height: 4px;
}
.tl-track-wrap::-webkit-scrollbar-thumb {
  background: var(--pb-border2);
  border-radius: 2px;
}

.tl-ruler {
  display: flex;
  height: 24px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--pb-border);
}
.tl-ruler-cell {
  position: relative;
  flex-shrink: 0;
  border-left: 1px solid var(--pb-border2);
}
.tl-ruler-label {
  position: absolute;
  top: 4px;
  left: 4px;
  font-family: var(--pb-font);
  font-size: 10px;
  color: var(--pb-text3);
}

.tl-body {
  position: relative;
  min-height: 32px;
}

.tl-track {
  position: relative;
  height: 28px;
  background: var(--pb-bg);
  border: 1px solid var(--pb-border);
  border-radius: 4px;
  overflow: hidden;
}

.tl-seg {
  position: absolute;
  top: 2px;
  bottom: 2px;
  min-width: 3px;
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.12s;
}
.tl-seg:hover {
  opacity: 0.85;
  z-index: 2;
  filter: brightness(1.2);
}
.tl-seg.seg-ok {
  background: var(--pb-accent);
  opacity: 0.6;
}
.tl-seg.seg-alarm {
  background: var(--pb-red);
  opacity: 0.7;
}
.tl-seg.seg-active {
  opacity: 1;
  box-shadow: 0 0 0 1.5px #fff;
  z-index: 3;
}

.tl-empty {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  height: 28px;
  font-size: 11px;
  color: var(--pb-text3);
  background: var(--pb-bg);
  border: 1px solid var(--pb-border);
  border-radius: 4px;
}
.tl-empty-idle {
  color: var(--pb-text3);
  opacity: 0.5;
}

/* Playhead */
.tl-playhead {
  position: absolute;
  top: 6px;
  bottom: 22px;
  z-index: 4;
  pointer-events: none;
  transition: left 0.25s ease;
}
.tl-ph-dot {
  position: absolute;
  top: 26px;
  left: 50%;
  width: 10px;
  height: 10px;
  background: var(--pb-red);
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transform: translateX(-50%);
}
.tl-ph-line {
  position: absolute;
  top: 34px;
  bottom: 0;
  left: 50%;
  width: 2px;
  background: var(--pb-red);
  transform: translateX(-50%);
}
</style>
