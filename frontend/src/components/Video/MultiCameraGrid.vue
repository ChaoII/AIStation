<template>
  <div class="multi-camera-grid" :class="gridClass">
    <div
      v-for="w in windows"
      :key="w.id"
      class="grid-window"
      :class="{
        'drag-over': dragOverWindow === w.id,
        'has-camera': !!w.camera,
        'is-active': activeWindow === w.id,
      }"
      :draggable="!!w.camera"
      @dragover.prevent="onDragOver(w.id)"
      @dragleave="onDragLeave(w.id)"
      @drop="onDrop(w.id, $event)"
      @dragstart="onWindowDragStart(w.id, $event)"
      @click="activeWindow = w.id"
      @contextmenu.prevent="onContextMenu($event, w)"
    >
      <template v-if="w.camera">
        <div class="window-player">
          <LivePlayer
            :ref="(el) => setPlayerRef(w.id, el)"
            :stream-id="w.camera.stream_id || w.camera.id"
            :stream-type="props.protocol"
            :poster="w.camera.poster"
            class="player-inner"
            @load="onPlayerLoad(w.id)"
            @error="onPlayerError(w.id)"
          />
        </div>
        <div class="window-watermark">
          <span v-if="props.recordingWindows?.[w.id]" class="rec-label">● REC</span>
          {{ w.camera.name }}
        </div>
        <div class="window-actions">
          <el-tooltip content="全屏" placement="top">
            <button class="action-btn" @click.stop="emit('fullscreen', w.id)">
              <el-icon><FullScreen /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="截图" placement="top">
            <button class="action-btn" @click.stop="handleSnapshot(w)">
              <el-icon><Camera /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip :content="w.muted ? '取消静音' : '静音'" placement="top">
            <button class="action-btn" @click.stop="toggleMute(w.id)">
              <el-icon>
                <Microphone v-if="!w.muted" />
                <MuteNotification v-else />
              </el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="云台控制" placement="top">
            <button class="action-btn" @click.stop="emit('ptz', w.id)">
              <el-icon><Monitor /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip :content="props.recordingWindows?.[w.id] ? '停止录像' : '开始录像'" placement="top">
            <button
              class="action-btn"
              :class="{ recording: props.recordingWindows?.[w.id] }"
              @click.stop="toggleRecord(w)"
            >
              <el-icon><VideoCamera /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="查看回放" placement="top">
            <button class="action-btn" @click.stop="emit('goPlayback', w.camera.id)">
              <el-icon><Clock /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="停止" placement="top">
            <button class="action-btn" @click.stop="emit('removeCamera', w.id)">
              <el-icon><Icon icon="mdi:stop" /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </template>
      <div v-else class="window-empty drop-zone" :class="{ 'drag-hover': dragOverWindow === w.id }">
        <el-icon :size="36" class="empty-camera-icon"><VideoCamera /></el-icon>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div v-if="contextMenu.camera" class="context-title">{{ contextMenu.camera.name }}</div>
        <div class="context-item" @click="contextAction('fullscreen')">
          <el-icon><FullScreen /></el-icon>
          最大化
        </div>
        <div class="context-item" @click="contextAction('snapshot')">
          <el-icon><Camera /></el-icon>
          截图
        </div>
        <div class="context-item" @click="contextAction('mute')">
          <el-icon><Microphone /></el-icon>
          {{ contextMenu.muted ? "取消静音" : "静音" }}
        </div>
        <div class="context-item" :class="{ 'recording-text': contextMenu.recording }" @click="contextAction(contextMenu.recording ? 'stopRecord' : 'record')">
          {{ contextMenu.recording ? "⏹ 停止录像" : "⏺ 开始录像" }}
        </div>
        <div class="context-divider" />
        <div class="context-item danger" @click="contextAction('close')">
          <el-icon><Close /></el-icon>
          关闭
        </div>
        <div class="context-item" @click="contextAction('playback')">
          <el-icon><VideoPlay /></el-icon>
          查看回放
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted, onBeforeUnmount } from "vue";
import {
  FullScreen,
  Camera,
  Close,
  VideoCamera,
  Clock,
  Microphone,
  MuteNotification,
} from "@element-plus/icons-vue";
import LivePlayer from "./LivePlayer.vue";
import { Icon } from "@iconify/vue";

interface WindowState {
  id: string;
  camera: any;
  loading: boolean;
  error: boolean;
  muted: boolean;
  playerRef: any;
}

const props = defineProps<{
  layout: string;
  cameraBindings: Record<string, any>;
  protocol: "flv" | "hls" | "webrtc";
  recordingWindows?: Record<string, boolean>;
}>();

const emit = defineEmits<{
  (e: "openCamera", cameraId: number, targetWindowId?: string): void;
  (e: "removeCamera", windowId: string): void;
  (e: "fullscreen", windowId: string): void;
  (e: "snapshot", windowId: string): void;
  (e: "swapCamera", fromId: string, toId: string): void;
  (e: "toggleMute", windowId: string): void;
  (e: "ptz", windowId: string): void;
  (e: "startRecord", windowId: string, cameraId: number, streamId: string): void;
  (e: "stopRecord", windowId: string, streamId: string): void;
  (e: "goPlayback", cameraId: number): void;
}>();

const activeWindow = ref<string | null>(null);
const dragOverWindow = ref<string | null>(null);
const windowStates = ref<Record<string, WindowState>>({});
const playerRefs = ref<Record<string, any>>({});

const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  windowId: "",
  camera: null as any,
  muted: false,
  recording: false,
});

const gridClass = computed(() => `grid-${props.layout}`);

const windows = computed(() => {
  const count = parseInt(props.layout) || 4;
  return Array.from({ length: count }, (_, i) => {
    const id = `w${i + 1}`;
    const camera = props.cameraBindings[id] || null;
    const state = windowStates.value[id] || {
      id,
      camera,
      loading: false,
      error: false,
      muted: false,
      playerRef: null,
    };
    if (camera?.id !== state.camera?.id) {
      state.camera = camera;
      state.loading = !!camera;
      state.error = false;
      state.muted = false;
    }
    windowStates.value[id] = state;
    return state;
  });
});

function setPlayerRef(windowId: string, el: any) {
  playerRefs.value[windowId] = el;
}

function onPlayerLoad(windowId: string) {
  const s = windowStates.value[windowId];
  if (s) {
    s.loading = false;
    s.error = false;
  }
}

function onPlayerError(windowId: string) {
  const s = windowStates.value[windowId];
  if (s) {
    s.loading = false;
    s.error = true;
  }
}

function toggleMute(windowId: string) {
  const s = windowStates.value[windowId];
  if (s) {
    s.muted = !s.muted;
    emit("toggleMute", windowId);
  }
}

function handleSnapshot(w: WindowState) {
  const player = playerRefs.value[w.id];
  if (player) {
    try {
      const video =
        player.$el?.querySelector("video") || player.$el?.parentElement?.querySelector("video");
      if (video && video.videoWidth > 0) {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d")!.drawImage(video, 0, 0);
        const link = document.createElement("a");
        link.download = `snapshot_${w.camera.name}_${Date.now()}.png`;
        link.href = canvas.toDataURL("image/png");
        link.click();
      }
    } catch {
      /* noop */
    }
  }
  emit("snapshot", w.id);
}

function onContextMenu(e: MouseEvent, w: WindowState) {
  contextMenu.visible = true;
  contextMenu.x = e.clientX;
  contextMenu.y = e.clientY;
  contextMenu.windowId = w.id;
  contextMenu.camera = w.camera;
  contextMenu.muted = w.muted;
  contextMenu.recording = !!props.recordingWindows?.[w.id];
}

function contextAction(action: string) {
  const wid = contextMenu.windowId;
  const state = windowStates.value[wid];
  contextMenu.visible = false;
  switch (action) {
    case "fullscreen":
      emit("fullscreen", wid);
      break;
    case "snapshot":
      handleSnapshot(windows.value.find((w: any) => w.id === wid) as any);
      break;
    case "mute":
      toggleMute(wid);
      break;
    case "record":
      if (state?.camera) {
        emit("startRecord", wid, state.camera.id, state.camera.stream_id || `camera_${state.camera.id}`);
      }
      break;
    case "stopRecord":
      if (state?.camera) {
        emit("stopRecord", wid, state.camera.stream_id || `camera_${state.camera.id}`);
      }
      break;
    case "close":
      emit("removeCamera", wid);
      break;
    case "playback":
      if (state?.camera) {
        emit("goPlayback", state.camera.id);
      }
      break;
  }
}

function toggleRecord(w: WindowState) {
  if (!w.camera) return;
  const sid = w.camera.stream_id || `camera_${w.camera.id}`;
  if (props.recordingWindows?.[w.id]) {
    emit("stopRecord", w.id, sid);
  } else {
    emit("startRecord", w.id, w.camera.id, sid);
  }
}

function onDragOver(windowId: string) {
  dragOverWindow.value = windowId;
}
function onDragLeave(windowId: string) {
  if (dragOverWindow.value === windowId) dragOverWindow.value = null;
}

function onDrop(windowId: string, e: DragEvent) {
  dragOverWindow.value = null;
  const raw = e.dataTransfer?.getData("application/camera");
  const sourceWindow = e.dataTransfer?.getData("application/window-id");
  if (raw) {
    try {
      const camera = JSON.parse(raw);
      emit("openCamera", camera.id, windowId);
    } catch {
      /* ignore */
    }
  } else if (sourceWindow) {
    emit("swapCamera", sourceWindow, windowId);
  }
}

function onWindowDragStart(windowId: string, e: DragEvent) {
  e.dataTransfer?.setData("application/window-id", windowId);

  const cam = props.cameraBindings[windowId];
  if (!cam || !e.dataTransfer) return;

  const ghost = document.createElement("div");
  ghost.textContent = cam.name || windowId;
  ghost.style.cssText =
    "display:flex;align-items:center;gap:6px;padding:4px 10px;font-size:13px;color:#fff;background:rgba(0,0,0,.75);border-radius:4px;white-space:nowrap";
  const icon = document.createElement("span");
  icon.innerHTML = "📷";
  icon.style.fontSize = "14px";
  ghost.prepend(icon);
  document.body.appendChild(ghost);
  e.dataTransfer.setDragImage(ghost, 4, 4);
  setTimeout(() => ghost.remove(), 0);
}

function closeContext() {
  contextMenu.visible = false;
}

onMounted(() => {
  document.addEventListener("click", closeContext);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", closeContext);
});
</script>

<style scoped>
.multi-camera-grid {
  display: grid;
  gap: 2px;
  width: 100%;
  height: 100%;
  padding: 2px;
  background: var(--el-fill-color);
}
.grid-1 {
  grid-template-rows: 1fr;
  grid-template-columns: 1fr;
}
.grid-4 {
  grid-template-rows: 1fr 1fr;
  grid-template-columns: 1fr 1fr;
}
.grid-6 {
  grid-template-rows: repeat(3, 1fr);
  grid-template-columns: repeat(3, 1fr);
}
.grid-6 .grid-window:nth-child(1) {
  grid-row: 1 / 3;
  grid-column: 1 / 3;
}
.grid-8 {
  grid-template-rows: repeat(4, 1fr);
  grid-template-columns: repeat(4, 1fr);
}
.grid-8 .grid-window:nth-child(1) {
  grid-row: 1 / 4;
  grid-column: 1 / 4;
}
.grid-9 {
  grid-template-rows: repeat(3, 1fr);
  grid-template-columns: repeat(3, 1fr);
}
.grid-16 {
  grid-template-rows: repeat(4, 1fr);
  grid-template-columns: repeat(4, 1fr);
}
.grid-13 {
  grid-template-rows: repeat(4, 1fr);
  grid-template-columns: repeat(4, 1fr);
}
.grid-13 .grid-window:nth-child(6) {
  grid-row: 2 / 4;
  grid-column: 2 / 4;
}

.grid-window {
  position: relative;
  min-height: 60px;
  overflow: hidden;
  cursor: pointer;
  background: #000;
  border: 1px solid transparent;
  border-radius: 2px;
  transition: box-shadow 0.2s;
}
.grid-window.has-camera {
  min-height: 60px;
}
.grid-window.is-active {
  z-index: 1;
  border-color: var(--el-color-primary);
  box-shadow: 0 0 6px color-mix(in srgb, var(--el-color-primary) 25%, transparent);
}
.grid-window.drag-over {
  border-color: var(--el-color-primary);
  box-shadow: inset 0 0 20px color-mix(in srgb, var(--el-color-primary) 30%, transparent);
}

.window-player {
  width: 100%;
  height: 100%;
}
.player-inner {
  width: 100%;
  height: 100%;
}

.window-watermark {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 1;
  padding: 6px 8px 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  pointer-events: none;
  background: linear-gradient(rgba(0, 0, 0, 0.85), transparent);
}

.window-actions {
  position: absolute;
  bottom: 6px;
  left: 50%;
  z-index: 3;
  display: flex;
  gap: 3px;
  transform: translateX(-50%);
  opacity: 0;
  transition: opacity 0.2s;
}
.grid-window:hover .window-actions {
  opacity: 1;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  font-size: 13px;
  color: #fff;
  cursor: pointer;
  background: rgba(0, 0, 0, 0.6);
  border: none;
  border-radius: 50%;
  transition: background 0.15s;
}
.action-btn:hover {
  background: rgba(0, 0, 0, 0.85);
}
.action-btn.danger {
  color: var(--el-color-danger);
}
.action-btn.danger:hover {
  color: var(--el-color-danger);
  background: rgba(244, 67, 54, 0.15);
}
.action-btn.recording {
  color: var(--el-color-danger);
}
.rec-label {
  display: inline;
  margin-right: 4px;
  font-size: 11px;
  font-weight: 700;
  color: var(--el-color-danger);
  animation: rec-blink 1.5s ease-in-out infinite;
}
@keyframes rec-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

.window-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  user-select: none;
  transition: all 0.2s;
}
.empty-camera-icon {
  color: #333;
  transition: color 0.2s;
}
.window-empty.drag-hover .empty-camera-icon {
  color: var(--el-color-primary);
}
</style>

<style>
.context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 140px;
  padding: 4px 0;
  font-size: 13px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}
.context-title {
  max-width: 200px;
  padding: 6px 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.context-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  transition: background 0.1s;
}
.context-item:hover {
  background: var(--el-fill-color);
}
.context-item.danger {
  color: var(--el-color-danger);
}
.context-item.recording-text {
  color: var(--el-color-danger);
  font-weight: 600;
}
.context-divider {
  height: 1px;
  margin: 4px 0;
  background: var(--el-border-color-lighter);
}
</style>
