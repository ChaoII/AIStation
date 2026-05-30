<template>
  <div class="big-screen">
    <div class="bs-header">
      <span class="bs-title">{{ layoutTitle }}</span>
      <div class="bs-controls">
        <el-select
          v-model="selectedLayoutId"
          placeholder="选择布局"
          size="small"
          clearable
          filterable
          style="width: 200px"
          @change="loadLayout"
        >
          <el-option v-for="l in layouts" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
        <el-button
          v-if="layoutPatrolInterval"
          size="small"
          :type="patrolRunning ? 'danger' : 'primary'"
          @click="togglePatrol"
        >
          {{ patrolRunning ? "停止轮巡" : "开始轮巡" }}
        </el-button>
        <el-button size="small" @click="exitFullscreen">退出全屏</el-button>
        <el-button size="small" @click="goBack">返回</el-button>
      </div>
    </div>
    <div v-loading="loading" class="bs-grid" :style="gridStyle">
      <div v-for="(camId, idx) in windowOrder" :key="idx" class="bs-window">
        <div v-if="camId && camerasMap[camId]" class="bs-player-wrap">
          <LivePlayer
            :ref="(el: any) => setPlayerRef(`w${idx + 1}`, el)"
            :stream="'rtmp://localhost/live/' + camerasMap[camId].push_token"
            :poster="camerasMap[camId].screenshot || ''"
            :name="camerasMap[camId].name"
          />
        </div>
        <div v-else class="bs-empty">
          <span class="bs-empty-text">{{ camId ? "摄像机离线" : "空窗口" }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getLayoutList, getLayoutDetail } from "@/api/module_video/layout";
import { getCameraList } from "@/api/module_video/camera";
import LivePlayer from "@/components/LivePlayer/index.vue";

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const layouts = ref<any[]>([]);
const selectedLayoutId = ref<number | null>(null);
const layoutTitle = ref("大屏展示");
const layoutGridType = ref("4");
const layoutWindows = ref<Record<string, number>>({});
const layoutPatrolInterval = ref(0);
const camerasMap = ref<Record<number, any>>({});
const playerRefs = ref<Record<string, any>>({});
const patrolRunning = ref(false);
let patrolTimer: ReturnType<typeof setInterval> | null = null;

function gridCols(type: string): number {
  const m: Record<string, number> = { "1": 1, "4": 2, "6": 3, "8": 4, "9": 3, "16": 4 };
  return m[type] || 2;
}

const windowCount = computed(() => Number(layoutGridType.value) || 4);
const windowOrder = computed(() => {
  const entries = Object.entries(layoutWindows.value) as [string, number][];
  entries.sort((a, b) => {
    const na = parseInt(a[0].replace(/\D/g, "")) || 0;
    const nb = parseInt(b[0].replace(/\D/g, "")) || 0;
    return na - nb;
  });
  return entries.map(([, v]) => v);
});

const gridStyle = computed(() => {
  const count = windowCount.value;
  const cols = gridCols(String(count));
  const is169 = count === 6 || count === 8;
  const rows = is169 ? 2 : Math.ceil(count / cols);
  return {
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    gridTemplateRows: `repeat(${rows}, 1fr)`,
  };
});

function setPlayerRef(key: string, el: any) {
  if (el) playerRefs.value[key] = el;
}

function exitFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
}

function goBack() {
  router.back();
}

function togglePatrol() {
  if (patrolRunning.value) {
    stopPatrol();
  } else {
    startPatrol();
  }
}

function startPatrol() {
  if (!layoutPatrolInterval.value || patrolRunning.value) return;
  patrolRunning.value = true;
  let current = 0;
  const windows = windowOrder.value;
  if (!windows.length) return;
  patrolTimer = setInterval(() => {
    const playerKeys = Object.keys(playerRefs.value);
    if (playerKeys.length > current) {
      const key = playerKeys[current];
      // Switch to next window's camera by cycling through cameras
      // This is simplified - real implementation would rotate
    }
    current = (current + 1) % playerKeys.length;
  }, layoutPatrolInterval.value * 1000);
}

function stopPatrol() {
  patrolRunning.value = false;
  if (patrolTimer) {
    clearInterval(patrolTimer);
    patrolTimer = null;
  }
}

async function loadLayout(layoutId?: number) {
  const id = layoutId || selectedLayoutId.value;
  if (!id) return;
  loading.value = true;
  try {
    const res = await getLayoutDetail(id);
    const layout = res.data?.data;
    if (!layout) return;
    layoutTitle.value = layout.name;
    layoutGridType.value = layout.grid_type || "4";
    layoutWindows.value = layout.layout_config?.windows || {};
    layoutPatrolInterval.value = layout.patrol_interval || 0;
    stopPatrol();
  } catch {}
  loading.value = false;
}

async function fetchLayouts() {
  try {
    const res = await getLayoutList({ page_size: 50 });
    layouts.value = res.data?.data?.items || [];
  } catch {
    layouts.value = [];
  }
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    const items = res.data?.data?.items || [];
    const map: Record<number, any> = {};
    for (const c of items) map[c.id] = c;
    camerasMap.value = map;
  } catch {}
}

onMounted(async () => {
  await fetchCameras();
  await fetchLayouts();
  const layoutId = route.query.layout_id ? Number(route.query.layout_id) : null;
  if (layoutId) {
    selectedLayoutId.value = layoutId;
    await loadLayout(layoutId);
  }
  setTimeout(() => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
  }, 500);
});

onBeforeUnmount(() => {
  stopPatrol();
  if (document.fullscreenElement) document.exitFullscreen();
});
</script>

<style scoped>
.big-screen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #000;
  color: #fff;
  display: flex;
  flex-direction: column;
}
.bs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: rgba(0, 0, 0, 0.7);
  flex-shrink: 0;
  z-index: 10;
}
.bs-title {
  font-size: 20px;
  font-weight: 600;
}
.bs-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.bs-grid {
  flex: 1;
  display: grid;
  gap: 2px;
  padding: 2px;
  overflow: hidden;
}
.bs-window {
  position: relative;
  background: #111;
  overflow: hidden;
}
.bs-player-wrap {
  width: 100%;
  height: 100%;
}
.bs-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
.bs-empty-text {
  font-size: 14px;
  color: #555;
}
</style>
