<template>
  <div class="app-container live-page">
    <div class="live-toolbar">
      <div class="toolbar-left">
        <span class="page-title">实时预览</span>
        <el-divider direction="vertical" />
        <el-radio-group v-model="layoutType" size="small">
          <el-radio-button v-for="l in currentLayouts" :key="l" :value="l">{{ l }}路</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-popover placement="bottom-start" trigger="click" width="260">
          <template #reference>
            <el-button size="small" :type="boundCount > 0 ? 'primary' : 'default'">
              <el-icon style="margin-right:4px"><Plus /></el-icon>
              绑定摄像机
              <el-tag v-if="boundCount > 0" size="small" round style="margin-left:4px">{{ boundCount }}</el-tag>
            </el-button>
          </template>
          <div class="camera-picker">
            <div class="picker-header">
              <span class="font-bold">在线摄像机</span>
              <el-tag size="small">{{ cameras.length }}台</el-tag>
            </div>
            <el-input v-model="cameraSearch" size="small" placeholder="搜索摄像机..." clearable style="margin:8px 0" />
            <div class="picker-list">
              <div
                v-for="c in filteredCameras"
                :key="c.id"
                class="picker-item"
                :class="{ bound: Object.values(cameraBindings).some((b: any) => b.id === c.id) }"
                @click="handleAddToGrid(c)"
              >
                <div class="picker-item-info">
                  <span class="picker-item-name">{{ c.name }}</span>
                  <span class="picker-item-location">{{ c.location || '未设置位置' }}</span>
                </div>
                <el-tag size="small" :type="c.status === 'ONLINE' ? 'success' : 'info'" effect="plain">
                  {{ c.status === 'ONLINE' ? '在线' : '离线' }}
                </el-tag>
              </div>
              <el-empty v-if="!filteredCameras.length" :image-size="60" description="没有可用的摄像机" />
            </div>
          </div>
        </el-popover>
        <el-button size="small" :disabled="boundCount === 0" @click="handleClearAll">清空</el-button>
        <el-tooltip content="全屏">
          <el-button size="small" icon="FullScreen" @click="handleToggleFullscreen" />
        </el-tooltip>
      </div>
    </div>

    <div class="live-main">
      <div class="live-grid-container">
        <MultiCameraGrid
          :layout="displayLayout"
          :camera-bindings="displayBindings"
          @open-camera="handleOpenCamera"
          @remove-camera="handleRemoveCamera"
        />
      </div>
      <div class="live-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-header">
          <div class="sidebar-header-left">
            <el-icon><Bell /></el-icon>
            <span class="font-bold">实时告警</span>
            <el-tag :type="alarmList.length > 0 ? 'danger' : 'info'" size="small" round>
              {{ alarmList.length }}
            </el-tag>
          </div>
          <el-button text size="small" @click="sidebarCollapsed = !sidebarCollapsed">
            <el-icon><Fold v-if="!sidebarCollapsed" /><Expand v-else /></el-icon>
          </el-button>
        </div>
        <div v-show="!sidebarCollapsed" class="sidebar-list">
          <template v-if="alarmList.length > 0">
            <div v-for="alarm in alarmList" :key="alarm.id" class="alarm-item" :class="severityClass(alarm.severity)">
              <div class="alarm-time">{{ alarm.alarm_time }}</div>
              <div class="alarm-type">{{ alarm.alarm_type }}</div>
              <div class="alarm-severity">
                <el-tag size="small" :type="severityTag(alarm.severity)" effect="dark">{{ alarm.severity }}</el-tag>
              </div>
            </div>
          </template>
          <el-empty v-else :image-size="50" description="暂无告警" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Plus, Bell, Fold, Expand } from '@element-plus/icons-vue'
import { getCameraList } from '@/api/module_video/camera'
import { getPlayUrls } from '@/api/module_video/preview'
import { getRealtimeAlarms } from '@/api/module_video/alarm'

const cameras = ref<any[]>([])
const layoutType = ref('4')
const cameraBindings = ref<Record<string, any>>({})
const currentLayouts = ['1', '4', '6', '8', '9', '16']
const fullscreenWindow = ref<string | null>(null)
const alarmList = ref<any[]>([])
const alarmTimer = ref<any>(null)
const cameraSearch = ref('')
const sidebarCollapsed = ref(false)
const loading = ref(false)
const nextWindowId = ref(1)

const boundCount = computed(() => Object.keys(cameraBindings.value).length)

const filteredCameras = computed(() => {
  const q = cameraSearch.value.toLowerCase()
  return cameras.value.filter((c: any) => !q || c.name.toLowerCase().includes(q) || (c.location || '').toLowerCase().includes(q))
})

const displayLayout = computed(() => fullscreenWindow.value ? '1' : layoutType.value)

const displayBindings = computed(() => {
  if (fullscreenWindow.value) {
    const cam = cameraBindings.value[fullscreenWindow.value]
    return { w1: cam || null }
  }
  return cameraBindings.value
})

async function fetchCameras() {
  loading.value = true
  try {
    const res = await getCameraList({ page_size: 1000 })
    cameras.value = (res.data?.items || []).filter((c: any) => c.stream_id)
  } finally {
    loading.value = false
  }
}

async function fetchAlarms() {
  try {
    const res = await getRealtimeAlarms()
    alarmList.value = (res.data || []).slice(0, 100)
  } catch {}
}

async function handleAddToGrid(camera: any) {
  const existing = Object.entries(cameraBindings.value).find(([_, c]: [string, any]) => c.id === camera.id)
  if (existing) return
  const wid = `w${nextWindowId.value++}`
  try {
    const res = await getPlayUrls(camera.id)
    camera = { ...camera, play_urls: res.data || {} }
  } catch {}
  cameraBindings.value = { ...cameraBindings.value, [wid]: camera }
}

function handleOpenCamera(id: number) {}

function handleRemoveCamera(windowId: string) {
  const newBindings = { ...cameraBindings.value }
  delete newBindings[windowId]
  cameraBindings.value = newBindings
}

function handleClearAll() {
  cameraBindings.value = {}
  nextWindowId.value = 1
}

function handleToggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function severityClass(severity: string) {
  switch ((severity || '').toUpperCase()) {
    case 'CRITICAL': return 'critical'
    case 'WARNING': return 'warning'
    default: return 'info'
  }
}

function severityTag(severity: string) {
  switch ((severity || '').toUpperCase()) {
    case 'CRITICAL': return 'danger'
    case 'WARNING': return 'warning'
    default: return 'info'
  }
}

onMounted(() => {
  fetchCameras()
  fetchAlarms()
  alarmTimer.value = setInterval(fetchAlarms, 5000)
})

onBeforeUnmount(() => {
  if (alarmTimer.value) clearInterval(alarmTimer.value)
})
</script>

<style scoped>
.live-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  overflow: hidden;
}

.live-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.live-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.live-grid-container {
  flex: 1;
  overflow: hidden;
}

.live-sidebar {
  width: 280px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.3s, opacity 0.3s;
  background: var(--el-bg-color);
}

.live-sidebar.collapsed {
  width: 44px;
}

.sidebar-header {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.sidebar-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.alarm-item {
  padding: 8px 10px;
  margin: 4px 0;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  transition: background 0.2s;
}

.alarm-item:hover {
  background: var(--el-fill-color-light);
}

.alarm-item.critical {
  border-left: 3px solid #f56c6c;
}

.alarm-item.warning {
  border-left: 3px solid #e6a23c;
}

.alarm-item.info {
  border-left: 3px solid #909399;
}

.alarm-time {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-bottom: 2px;
}

.alarm-type {
  font-weight: 500;
  margin-bottom: 2px;
}

.camera-picker {
  max-height: 360px;
  display: flex;
  flex-direction: column;
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}

.picker-list {
  flex: 1;
  overflow-y: auto;
  max-height: 260px;
}

.picker-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.2s;
  margin: 2px 0;
}

.picker-item:hover {
  background: var(--el-color-primary-light-9);
}

.picker-item.bound {
  opacity: 0.5;
  pointer-events: none;
}

.picker-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
  margin-right: 8px;
}

.picker-item-name {
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-item-location {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}
</style>
