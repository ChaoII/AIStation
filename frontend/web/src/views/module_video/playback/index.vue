<template>
  <div class="pb-page">
    <header class="pb-topbar">
      <div class="topbar-brand">
        <span class="brand-dot" />
        <span class="brand-text">录像回放</span>
      </div>

      <span class="topbar-sep" />

      <div class="panel-toggles">
        <ElTooltip content="设备面板" placement="bottom">
          <span class="panel-switch-item">
            <ElIcon><Icon icon="mdi:file-tree" /></ElIcon>
            <ElSwitch v-model="devicePanelOpen" size="small" />
          </span>
        </ElTooltip>
        <ElTooltip content="片段面板" placement="bottom">
          <span class="panel-switch-item">
            <ElIcon><Icon icon="mdi:view-list" /></ElIcon>
            <ElSwitch v-model="segmentsPanelOpen" size="small" />
          </span>
        </ElTooltip>
      </div>

      <span class="topbar-sep" />

      <div class="topbar-center">
        <div class="search-group">
          <div class="field-row">
            <ElDatePicker v-model="searchDate" type="date" placeholder="选择日期" size="small" value-format="YYYY-MM-DD" class="field-date" />
            <ElTimePicker v-model="searchStartTime" placeholder="开始" size="small" value-format="HH:mm:ss" format="HH:mm" class="field-time" />
            <span class="time-sep">—</span>
            <ElTimePicker v-model="searchEndTime" placeholder="结束" size="small" value-format="HH:mm:ss" format="HH:mm" class="field-time" />
            <ElButton size="small" type="primary" :disabled="!selectedCamera" @click="handleSearch">
              <ElIcon><Search /></ElIcon>
              搜索
            </ElButton>
          </div>
        </div>
      </div>
    </header>

    <div class="pb-body">
      <aside v-show="devicePanelOpen" class="live-device-panel">
        <div class="panel-header">
          <ElIcon :size="14"><FolderOpened /></ElIcon>
          <span>设备列表</span>
        </div>
        <div class="tree-filter">
          <ElInput v-model="deviceSearch" size="small" placeholder="搜索设备..." clearable :prefix-icon="Search" />
        </div>
        <ElTree ref="deviceTreeRef" :data="deviceTreeData" :props="{ children: 'children', label: 'label' }" node-key="id" default-expand-all highlight-current class="device-tree" @node-click="onDeviceNodeClick">
          <template #default="{ data }">
            <div v-if="data.type === 'camera'" class="tree-camera-node" @dblclick="selectAndSearch(data.camera)">
              <span class="dot" :class="data.camera.status === 'ONLINE' ? 'dot-on' : 'dot-off'" />
              <span class="tree-camera-name">{{ data.camera.name }}</span>
            </div>
            <div v-else class="tree-camera-node" style="color:var(--el-text-color-secondary)">
              <ElIcon :size="14"><FolderOpened /></ElIcon>
              <span>{{ data.label }}</span>
              <span class="tree-count">{{ data.cameraCount || 0 }}</span>
            </div>
          </template>
        </ElTree>
      </aside>

      <div class="pb-content">
        <div class="pb-main">
          <div class="pb-player">
            <video v-if="currentVideoUrl && !useFlv" :key="currentVideoUrl" ref="videoRef" :src="currentVideoUrl" controls class="player-video" @loadedmetadata="onLoadedMetadata" @timeupdate="onTimeUpdate" @play="isPlaying = true" @pause="isPlaying = false" @ended="onVideoEnded" @error="onVideoError" />
            <div v-else-if="currentVideoUrl && useFlv" ref="flvContainerRef" class="player-flv-wrap">
              <video ref="flvVideoRef" autoplay playsinline muted controls class="player-video" />
            </div>
            <div v-else class="player-empty">
              <div class="empty-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                  <polygon points="23 7 16 12 23 17 23 7" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
              </div>
              <p class="empty-text">选择摄像机与时间后搜索录像</p>
            </div>
            <div v-if="loading" class="player-loading"><div class="spinner" /></div>
          </div>

          <div class="pb-timeline">
            <div class="tl-toolbar">
              <div class="tl-zoom-group">
                <button class="tl-nav-btn" title="向前移动" @click="shiftView(-0.5)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6" /></svg>
                </button>
                <button v-for="z in zoomLevels" :key="z.value" class="tl-zbtn" :class="{ active: currentZoom === z.value }" @click="handleZoom(z.value)">{{ z.label }}</button>
                <button class="tl-nav-btn" title="向后移动" @click="shiftView(0.5)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6" /></svg>
                </button>
              </div>
              <span class="tl-range-label">{{ formatTimeHMS(viewStartMs) }} — {{ formatTimeHMS(viewEndMs) }}</span>
            </div>

            <div ref="timelineRef" class="tl-track-area" @click="onTimelineClick">
              <div class="tl-ruler-row">
                <div v-for="tick in rulerTicks" :key="tick.key" class="tl-tick" :class="{ 'tl-tick-major': tick.isMajor }" :style="{ left: tick.pct + '%' }">
                  <span class="tl-tick-label">{{ tick.label }}</span>
                  <span class="tl-tick-line" />
                </div>
              </div>
              <div class="tl-segments-row">
                <div v-if="hasRecordings" class="tl-track-bg">
                  <div v-for="r in recordings" :key="r.id" class="tl-seg" :class="[r.record_type === 'ALARM' ? 'seg-alarm' : 'seg-normal', { 'seg-active': currentRecording?.id === r.id }]" :style="getSegmentStyle(r)" :title="`${formatDateTime(r.start_time)} — ${formatDateTime(r.end_time)}`" @click.stop="seekToRecording(r)" />
                </div>
                <div v-else-if="hasSearched" class="tl-empty-track">
                  <ElIcon :size="14"><InfoFilled /></ElIcon>
                  该时段无录像
                </div>
                <div v-else class="tl-empty-track">选择摄像机后搜索</div>
              </div>
              <div v-if="playheadPct >= 0 && playheadPct <= 100" class="tl-playhead" :style="{ left: playheadPct + '%' }">
                <span class="tl-playhead-line" />
                <span class="tl-playhead-dot" />
              </div>
            </div>
          </div>
        </div>

        <div v-show="segmentsPanelOpen" class="pb-segments">
          <div class="seg-list-header">录像片段 ({{ recordings.length }})</div>
          <div class="seg-list-body">
            <div v-for="(r, idx) in recordings" :key="r.id" class="seg-card" :class="{ active: currentRecording?.id === r.id }" @click="seekToRecording(r)">
              <div class="seg-card-thumb">
                <img v-if="thumbnailCache[r.id]" :src="thumbnailCache[r.id]" alt="" class="seg-thumb-img" loading="lazy" @error="onThumbError($event)" />
                <div v-else class="seg-thumb-placeholder">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="2" width="20" height="20" rx="2" /><polygon points="10 8 16 12 10 16 10 8" /></svg>
                </div>
              </div>
              <div class="seg-card-info">
                <div class="seg-card-time">{{ formatDateTime(r.start_time) }} — {{ formatDateTime(r.end_time) }}</div>
                <div v-if="r.duration" class="seg-card-dur">{{ formatDuration(r.duration) }}</div>
              </div>
              <span class="seg-card-idx">{{ idx + 1 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { Search, FolderOpened, InfoFilled } from "@element-plus/icons-vue";
import { Icon } from "@iconify/vue";
import { VideoAPI } from "@/api/module_video";

defineOptions({ name: "VideoPlayback", inheritAttrs: false });

const cameras = ref<any[]>([]);
const groupList = ref<any[]>([]);
const selectedCamera = ref<number | null>(null);
const devicePanelOpen = ref(true);
const segmentsPanelOpen = ref(true);
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
const currentTime = ref(0);

const videoRef = ref<HTMLVideoElement | null>(null);
const flvContainerRef = ref<HTMLDivElement | null>(null);
const flvVideoRef = ref<HTMLVideoElement | null>(null);
const timelineRef = ref<HTMLElement | null>(null);

let mpegtsPlayer: any = null;
let pendingSeekSec: number | null = null;
const thumbnailCache = ref<Record<number, string>>({});

const currentZoom = ref(4);
const viewStartMs = ref(0);

const zoomLevels = [
  { value: 24, label: "24h" },
  { value: 4, label: "4h" },
  { value: 1, label: "1h" },
  { value: 0.5, label: "30m" },
];

const viewDurationMs = computed(() => currentZoom.value * 3600000);
const viewEndMs = computed(() => viewStartMs.value + viewDurationMs.value);

function getSearchStartMs(): number {
  if (!searchDate.value) {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0).getTime();
  }
  return new Date(`${searchDate.value} ${searchStartTime.value || "00:00:00"}`).getTime();
}

const playbackTimeMs = computed(() => {
  if (!currentRecording.value) return null;
  const segStartMs = new Date(currentRecording.value.start_time).getTime();
  return segStartMs + currentTime.value * 1000;
});

const playheadPct = computed(() => {
  const t = playbackTimeMs.value;
  if (t === null) return -1;
  const vDur = viewDurationMs.value;
  if (vDur <= 0) return -1;
  const pct = ((t - viewStartMs.value) / vDur) * 100;
  return Math.max(0, Math.min(100, pct));
});

const hasRecordings = computed(() => recordings.value.length > 0);

const rulerTicks = computed(() => {
  const ticks: { key: string; pct: number; label: string; isMajor: boolean }[] = [];
  const vStart = viewStartMs.value;
  const vDur = viewDurationMs.value;
  if (vDur <= 0) return ticks;

  let intervalMs: number;
  if (currentZoom.value >= 24) intervalMs = 2 * 3600000;
  else if (currentZoom.value >= 4) intervalMs = 3600000;
  else if (currentZoom.value >= 1) intervalMs = 15 * 60000;
  else intervalMs = 5 * 60000;

  const firstTick = Math.ceil(vStart / intervalMs) * intervalMs;
  for (let t = firstTick; t < vStart + vDur; t += intervalMs) {
    if (t < vStart) continue;
    const d = new Date(t);
    const h = String(d.getHours()).padStart(2, "0");
    const m = String(d.getMinutes()).padStart(2, "0");
    const label = `${h}:${m}`;
    const pct = ((t - vStart) / vDur) * 100;
    const isMajor = d.getMinutes() === 0;
    ticks.push({ key: `${t}`, pct, label, isMajor });
  }
  return ticks;
});

function formatTimeHMS(ms: number): string {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

function formatDateTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((v) => String(v).padStart(2, "0")).join(":");
}

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return "";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) return `${h}时${m}分${s}秒`;
  if (m > 0) return `${m}分${s}秒`;
  return `${s}秒`;
}

function getSegmentStyle(r: any) {
  const vStart = viewStartMs.value;
  const vDur = viewDurationMs.value;
  if (vDur <= 0) return { display: "none" };
  const rs = new Date(r.start_time).getTime();
  const re = new Date(r.end_time).getTime();
  if (re <= vStart || rs >= vStart + vDur) return { display: "none" };
  const leftPct = ((rs - vStart) / vDur) * 100;
  const rightPct = ((re - vStart) / vDur) * 100;
  const visibleLeft = Math.max(0, leftPct);
  const visibleRight = Math.min(100, rightPct);
  const width = visibleRight - visibleLeft;
  return { left: `${visibleLeft}%`, width: `${Math.max(0.3, width)}%` };
}

function handleZoom(zoom: number) {
  const centerMs = playbackTimeMs.value || viewStartMs.value + viewDurationMs.value / 2;
  currentZoom.value = zoom;
  viewStartMs.value = centerMs - (zoom * 3600000) / 2;
}

function shiftView(factor: number) {
  viewStartMs.value += factor * viewDurationMs.value;
}

function onTimelineClick(e: MouseEvent) {
  const el = timelineRef.value;
  if (!el || !hasRecordings.value) return;
  const rect = el.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const pct = x / rect.width;
  const targetMs = viewStartMs.value + pct * viewDurationMs.value;

  const seg = recordings.value.find((r: any) => {
    const rs = new Date(r.start_time).getTime();
    const re = new Date(r.end_time).getTime();
    return targetMs >= rs && targetMs <= re;
  });

  if (seg) {
    const offsetSec = (targetMs - new Date(seg.start_time).getTime()) / 1000;
    seekToRecording(seg, Math.max(0, offsetSec));
  }
}

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
      for (const c of gc) children.push({ id: `cam-${c.id}`, label: c.name, type: "camera", camera: c });
      return { id: `group-${g.id}`, label: g.name, type: "group", cameraCount: gc.length, children };
    });
  }
  const ungrouped = (camMap.get(undefined) || []).map((c: any) => ({ id: `cam-${c.id}`, label: c.name, type: "camera", camera: c }));
  const treeChildren = buildGroupTree(groupList.value);
  if (ungrouped.length) {
    treeChildren.push({ id: "ungrouped", label: "未分组", type: "group", cameraCount: ungrouped.length, children: ungrouped });
  }
  return [{ id: "root", label: "所有设备", type: "root", cameraCount: cameras.value.length, children: treeChildren }];
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
    } catch { /* ignore */ }
    mpegtsPlayer = null;
  }
}

function getVideoEl(): HTMLVideoElement | null {
  return useFlv.value ? flvVideoRef.value : videoRef.value;
}

async function seekToRecording(rec: any, offsetSec: number = 0) {
  if (currentRecording.value?.id === rec.id && currentVideoUrl.value) {
    const video = getVideoEl();
    if (video && video.readyState >= 1) {
      video.currentTime = Math.min(offsetSec, video.duration || 0);
      video.play();
      return;
    }
  }

  currentRecording.value = rec;
  loading.value = true;
  useFlv.value = false;
  destroyMpegtsPlayer();
  pendingSeekSec = offsetSec;

  try {
    const res = await VideoAPI.getRecordFilePlayUrl(rec.id);
    const playUrl = res.data?.data?.play_url || rec.file_path;
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
    currentVideoUrl.value = `/record/live/${rec.stream_id}/${rec.file_path}`;
    useFlv.value = false;
  }
  loading.value = false;
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
    if (pendingSeekSec !== null && pendingSeekSec > 0) {
      video.currentTime = Math.min(pendingSeekSec, video.duration || 0);
      pendingSeekSec = null;
    }
  }
}

function onVideoEnded() {
  isPlaying.value = false;
  const idx = recordings.value.findIndex((r: any) => r.id === currentRecording.value?.id);
  if (idx >= 0 && idx < recordings.value.length - 1) {
    seekToRecording(recordings.value[idx + 1]);
  }
}

function onVideoError() {
  loading.value = false;
  isPlaying.value = false;
}

function onThumbError(e: Event) {
  const img = e.target as HTMLImageElement;
  if (img) img.style.display = "none";
}

function loadThumbnails() {
  for (const r of recordings.value) {
    if (!thumbnailCache.value[r.id]) {
      VideoAPI.getRecordFileThumbnail(r.id)
        .then((res: any) => {
          const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: "image/jpeg" });
          thumbnailCache.value[r.id] = URL.createObjectURL(blob);
        })
        .catch(() => {});
    }
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

  const startMs = getSearchStartMs();
  viewStartMs.value = startMs;

  try {
    const allItems: any[] = [];
    let pageNo = 1;
    const pageSize = 100;
    while (true) {
      const res = await VideoAPI.listRecordFile({
        page_no: pageNo,
        page_size: pageSize,
        camera_id: selectedCamera.value,
        start_time: `${searchDate.value} ${searchStartTime.value || "00:00:00"}`,
        end_time: `${searchDate.value} ${searchEndTime.value || "23:59:59"}`,
      });
      const page = res.data?.data;
      const items = page?.items || [];
      allItems.push(...items);
      if (!page?.has_next || items.length < pageSize) break;
      pageNo++;
    }
    allItems.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
    recordings.value = allItems;
    loadThumbnails();
    if (recordings.value.length > 0) {
      await seekToRecording(recordings.value[0]);
      const firstStartMs = new Date(recordings.value[0].start_time).getTime();
      viewStartMs.value = Math.max(startMs, firstStartMs - viewDurationMs.value * 0.1);
    }
  } catch {
    recordings.value = [];
  }
  loading.value = false;
}

watch(
  () => playbackTimeMs.value,
  (t) => {
    if (t === null || !isPlaying.value) return;
    const pct = (t - viewStartMs.value) / viewDurationMs.value;
    if (pct > 0.88) {
      viewStartMs.value = t - viewDurationMs.value * 0.35;
    } else if (pct < 0) {
      viewStartMs.value = t - viewDurationMs.value * 0.1;
    }
  }
);

onMounted(() => {
  const now = new Date();
  searchDate.value = now.toISOString().slice(0, 10);
  viewStartMs.value = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0).getTime();
  VideoAPI.listCamera({ page_size: 100 })
    .then((r) => { cameras.value = r.data?.data?.items || []; })
    .catch(() => {});
  VideoAPI.listCameraGroup()
    .then((r) => { groupList.value = r.data?.data || []; })
    .catch(() => {});
});

onBeforeUnmount(() => {
  destroyMpegtsPlayer();
  for (const url of Object.values(thumbnailCache.value)) {
    URL.revokeObjectURL(url);
  }
});
</script>

<style scoped>
.pb-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 13px;
}

.pb-topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  height: 48px;
  padding: 0 16px;
  background: var(--el-bg-color);
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
  letter-spacing: 0.5px;
}

.topbar-sep {
  width: 1px;
  height: 20px;
  background: var(--el-border-color);
  flex-shrink: 0;
}

.panel-toggles {
  display: flex;
  gap: 6px;
}
.panel-switch-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  font-size: 15px;
  color: var(--el-text-color-secondary);
  border-radius: 6px;
  transition: background 0.15s;
}
.panel-switch-item:hover {
  background: var(--el-fill-color);
}

.topbar-center {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  padding-right: 12px;
}

.search-group {
  display: flex;
  align-items: center;
}
.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.field-date {
  width: 140px;
}
.field-time {
  width: 96px;
}
.time-sep {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  font-weight: 500;
}

.pb-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.live-device-panel {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 220px;
  overflow: hidden;
  background: var(--el-bg-color);
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
  border-bottom: 1px solid var(--el-border-color-light);
}
.tree-filter {
  flex-shrink: 0;
  padding: 6px 8px;
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
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-radius: 8px;
}
.dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-on {
  background: var(--el-color-success);
}
.dot-off {
  background: var(--el-text-color-placeholder);
}

.pb-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.pb-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.pb-player {
  position: relative;
  flex: 1;
  min-height: 0;
  background: #000;
}
.player-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.player-flv-wrap {
  width: 100%;
  height: 100%;
}
.player-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  color: #666;
}
.empty-text {
  margin: 0;
  font-size: 13px;
}
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
  width: 28px;
  height: 28px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-top-color: var(--el-color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.pb-timeline {
  flex-shrink: 0;
  height: 120px;
  padding: 8px 16px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}
.tl-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.tl-zoom-group {
  display: flex;
  gap: 4px;
  align-items: center;
}
.tl-nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.tl-nav-btn:hover {
  color: var(--el-color-primary);
}
.tl-zbtn {
  padding: 2px 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.tl-zbtn.active {
  color: #fff;
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}
.tl-range-label {
  font-family: "SF Mono", "Cascadia Code", monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tl-track-area {
  position: relative;
  height: 60px;
}
.tl-ruler-row {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 24px;
}
.tl-tick {
  position: absolute;
  top: 0;
  height: 24px;
  transform: translateX(-50%);
}
.tl-tick-label {
  position: absolute;
  top: 2px;
  left: 50%;
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  transform: translateX(-50%);
  white-space: nowrap;
}
.tl-tick-line {
  position: absolute;
  bottom: 0;
  left: 50%;
  width: 1px;
  height: 6px;
  background: var(--el-border-color);
  transform: translateX(-50%);
}
.tl-tick-major .tl-tick-line {
  height: 10px;
  background: var(--el-text-color-secondary);
}
.tl-segments-row {
  position: absolute;
  top: 28px;
  right: 0;
  left: 0;
  height: 24px;
}
.tl-track-bg {
  position: absolute;
  top: 2px;
  right: 0;
  bottom: 2px;
  left: 0;
  background: var(--el-fill-color);
  border-radius: 4px;
}
.tl-seg {
  position: absolute;
  top: 2px;
  bottom: 2px;
  cursor: pointer;
  border-radius: 3px;
}
.seg-normal {
  background: var(--el-color-primary);
  opacity: 0.75;
}
.seg-alarm {
  background: var(--el-color-danger);
  opacity: 0.85;
}
.seg-active {
  outline: 2px solid var(--el-color-warning);
  opacity: 1;
}
.tl-empty-track {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.tl-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 3;
  width: 0;
}
.tl-playhead-line {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 2px;
  background: var(--el-color-warning);
  box-shadow: 0 0 4px var(--el-color-warning);
}
.tl-playhead-dot {
  position: absolute;
  top: 0;
  left: 50%;
  width: 8px;
  height: 8px;
  background: var(--el-color-warning);
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.pb-segments {
  flex-shrink: 0;
  height: 200px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--el-border-color-light);
}
.seg-list-header {
  flex-shrink: 0;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-light);
}
.seg-list-body {
  flex: 1;
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  overflow-x: auto;
}
.seg-card {
  position: relative;
  flex-shrink: 0;
  width: 200px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.15s;
}
.seg-card:hover {
  border-color: var(--el-color-primary);
}
.seg-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 6px color-mix(in srgb, var(--el-color-primary) 25%, transparent);
}
.seg-card-thumb {
  height: 90px;
  background: #000;
}
.seg-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.seg-thumb-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #fff;
}
.seg-card-info {
  padding: 6px 8px;
}
.seg-card-time {
  font-size: 11px;
  color: var(--el-text-color-regular);
}
.seg-card-dur {
  margin-top: 2px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.seg-card-idx {
  position: absolute;
  top: 4px;
  left: 4px;
  min-width: 16px;
  padding: 0 4px;
  font-size: 10px;
  color: #fff;
  text-align: center;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 3px;
}
</style>
