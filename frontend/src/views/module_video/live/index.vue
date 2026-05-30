<template>
  <div class="live-page">
    <div ref="toolbarRef" class="live-toolbar">
      <div class="toolbar-brand">
        <span class="brand-dot" />
        <span class="brand-text">实时预览</span>
      </div>

      <span class="toolbar-divider" />

      <div class="panel-toggles">
        <el-tooltip content="设备面板开关" placement="bottom">
          <span class="panel-switch-item">
            <el-icon><Icon icon="mdi:file-tree" /></el-icon>
            <el-switch v-model="showDevicePanel" size="small" />
          </span>
        </el-tooltip>
        <el-tooltip content="告警面板开关" placement="bottom">
          <span class="panel-switch-item">
            <el-icon><Bell /></el-icon>
            <el-switch v-model="showAlarmPanel" size="small" />
          </span>
        </el-tooltip>
      </div>

      <span class="toolbar-divider" />

      <div class="toolbar-group">
        <span class="toolbar-label">布局</span>
        <el-popover
          v-model:visible="showLayoutPopover"
          trigger="click"
          placement="bottom"
          :width="196"
          popper-class="layout-popover"
        >
          <template #reference>
            <button class="layout-btn layout-btn-current" v-html="currentLayoutSvg" />
          </template>
          <div class="layout-popover-grid">
            <button
              v-for="l in layouts"
              :key="l.value"
              class="layout-popover-item"
              :class="{ active: layoutType === l.value }"
              @click="
                layoutType = l.value;
                showLayoutPopover = false;
              "
              v-html="l.svg"
            />
          </div>
        </el-popover>
      </div>

      <div class="toolbar-group">
        <span class="toolbar-label">协议</span>
        <el-select v-model="globalProtocol" size="small" style="width: 100px">
          <el-option v-for="p in protocols" :key="p.value" :value="p.value" :label="p.label" />
        </el-select>
      </div>

      <div class="toolbar-group">
        <div class="scheme-split">
          <el-dropdown trigger="click" @command="handleLayoutSelect">
            <button class="scheme-split-select">
              <el-icon><Download /></el-icon>
              <span>{{ selectedLayoutName || '加载方案' }}</span>
              <el-icon class="scheme-arrow"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="ly in savedLayouts" :key="ly.id" :command="ly">
                  {{ ly.name }}
                  <span style="color: var(--el-text-color-placeholder); font-size: 11px">
                    ({{ ly.grid_type }}路)
                  </span>
                </el-dropdown-item>
                <el-dropdown-item v-if="!savedLayouts.length" disabled>暂无方案</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip content="保存当前布局" placement="bottom">
            <button class="scheme-split-save" :disabled="boundCount === 0" @click="openSaveLayout">
              <el-icon><Icon icon="mdi:content-save" /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>

      <span class="toolbar-divider" />

      <div class="toolbar-group">
        <el-tooltip content="自动轮巡切换摄像机画面" placement="bottom">
          <span class="panel-switch-item">
            <el-icon><Refresh /></el-icon>
            <el-switch v-model="tourMode" size="small" />
          </span>
        </el-tooltip>
        <el-input-number
          v-if="tourMode"
          v-model="tourInterval"
          :min="5"
          :max="300"
          :step="5"
          size="small"
          controls-position="right"
          style="width: 84px"
        >
          <template #suffix><span style="font-size: 11px; color: #999">秒</span></template>
        </el-input-number>
      </div>

      <div class="toolbar-right">
        <el-tooltip content="清空所有窗口" placement="bottom">
          <button class="layout-btn" :disabled="boundCount === 0" @click="handleClearAll">
            <el-icon><Delete /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="全屏" placement="bottom">
          <button class="layout-btn" @click="handleToggleFullscreen">
            <el-icon><FullScreen /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip v-if="isFullscreen" content="退出全屏" placement="bottom">
          <button class="layout-btn" @click="exitFullscreen">
            <el-icon><Close /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>

    <div class="live-main">
      <div v-show="showDevicePanel" class="live-device-panel">
        <div class="panel-header">
          <el-icon :size="14"><FolderOpened /></el-icon>
          <span>设备列表</span>
        </div>
        <div class="panel-body">
          <div class="tree-filter">
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
            :filter-node-method="filterDeviceNode"
            node-key="id"
            default-expand-all
            highlight-current
            class="device-tree"
            @node-click="onDeviceNodeClick"
          >
            <template #default="{ node, data }">
              <div
                v-if="data.type === 'camera'"
                class="tree-camera-node"
                draggable="true"
                @dragstart.stop="onDeviceDragStart(data.camera, $event)"
                @dragend="onDeviceDragEnd"
              >
                <span class="device-status-dot" :class="statusClass(data.camera.status)" />
                <span class="tree-camera-name">{{ data.camera.name }}</span>
                <el-button
                  v-if="isCameraBound(data.camera.id)"
                  text
                  size="small"
                  type="warning"
                  class="tree-camera-btn"
                  @click.stop="handleRemoveFromAllWindows(data.camera.id)"
                >
                  <el-icon><Close /></el-icon>
                </el-button>
                <el-button
                  v-else
                  text
                  size="small"
                  type="primary"
                  class="tree-camera-btn"
                  @click.stop="handleAddToAnyWindow(data.camera)"
                >
                  <el-icon><VideoCamera /></el-icon>
                </el-button>
              </div>
              <div v-else class="tree-group-node">
                <el-icon :size="14"><FolderOpened /></el-icon>
                <span>{{ node.label }}</span>
                <span class="tree-count">{{ data.cameraCount || 0 }}</span>
              </div>
            </template>
          </el-tree>
        </div>
      </div>

      <div ref="gridPanelRef" class="live-grid-panel">
        <MultiCameraGrid
          ref="gridRef"
          :layout="fullscreenWindow ? '1' : layoutType"
          :camera-bindings="displayBindings"
          :protocol="globalProtocol"
          :recording-windows="recordingWindows"
          @open-camera="handleOpenCamera"
          @remove-camera="handleRemoveCamera"
          @fullscreen="handleWindowFullscreen"
          @snapshot="handleSnapshot"
          @swap-camera="handleSwapCamera"
          @ptz="handlePtzToggle"
          @start-record="handleStartRecord"
          @stop-record="handleStopRecord"
          @go-playback="goToPlayback"
        />
        <Transition name="slide-up">
          <div v-if="showPtz && activeWindowId && !fullscreenWindow" class="ptz-panel">
            <div class="ptz-header">
              <el-icon :size="12"><Monitor /></el-icon>
              <span>云台控制</span>
              <el-tag size="small" effect="dark" class="ptz-window-tag">
                {{ activeWindowId }}
              </el-tag>
              <el-button text size="small" class="ptz-close" @click="activeWindowId = null">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <div class="ptz-body">
              <div class="ptz-dpad">
                <button class="ptz-btn ptz-up" title="上" @mousedown="handlePtz">
                  <el-icon><Top /></el-icon>
                </button>
                <button class="ptz-btn ptz-left" title="左" @mousedown="handlePtz">
                  <el-icon><Back /></el-icon>
                </button>
                <button class="ptz-btn ptz-center" disabled />
                <button class="ptz-btn ptz-right" title="右" @mousedown="handlePtz">
                  <el-icon><Right /></el-icon>
                </button>
                <button class="ptz-btn ptz-down" title="下" @mousedown="handlePtz">
                  <el-icon><Bottom /></el-icon>
                </button>
              </div>
              <div class="ptz-zoom">
                <button class="ptz-btn" title="变焦+">
                  <el-icon><ZoomIn /></el-icon>
                </button>
                <button class="ptz-btn" title="变焦-">
                  <el-icon><ZoomOut /></el-icon>
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <div v-show="showAlarmPanel" class="live-alarm-panel">
        <div class="panel-header">
          <el-icon :size="14"><Bell /></el-icon>
          <span>实时告警</span>
          <span v-if="alarmList.length" class="alarm-badge">{{ alarmList.length }}</span>
          <div class="panel-header-actions">
            <el-button text size="small" @click="handleClearAlarms">清空</el-button>
          </div>
        </div>
        <div class="panel-body">
          <div class="alarm-filters">
            <el-check-tag
              v-for="f in alarmFilters"
              :key="f.key"
              :class="`filter-${f.key}`"
              :checked="alarmActiveFilter === f.key"
              @click="alarmActiveFilter = f.key"
            >
              {{ f.label }}
            </el-check-tag>
          </div>
          <div class="alarm-list">
            <div
              v-for="alarm in filteredAlarms"
              :key="alarm.id"
              class="alarm-item"
              :class="severityClass(alarm.severity)"
              @click="handleAlarmClick(alarm)"
            >
              <div class="alarm-item-header">
                <span class="alarm-camera-name">{{ alarm.camera?.name || "未知" }}</span>
                <el-tag
                  :type="severityTag(alarm.severity)"
                  size="small"
                  effect="dark"
                  class="alarm-severity-tag"
                >
                  {{ alarm.severity }}
                </el-tag>
              </div>
              <div class="alarm-type-text">{{ alarm.alarm_type }}</div>
              <div class="alarm-item-footer">
                <span class="alarm-time">{{ formatTime(alarm.alarm_time) }}</span>
                <el-button
                  v-if="alarm.status === 'PENDING'"
                  text
                  size="small"
                  type="primary"
                  @click.stop="handleConfirmAlarm(alarm.id)"
                >
                  确认
                </el-button>
              </div>
            </div>
            <el-empty v-if="!filteredAlarms.length" :image-size="40" description="暂无告警" />
          </div>
        </div>
      </div>
    </div>

    <div class="live-statusbar">
      <div class="statusbar-left">
        <span class="status-item">
          设备总数:
          <strong>{{ cameras.length }}</strong>
        </span>
        <span class="status-divider" />
        <span class="status-item online">
          在线:
          <strong>{{ onlineCount }}</strong>
        </span>
        <span class="status-divider" />
        <span class="status-item offline">
          离线:
          <strong>{{ offlineCount }}</strong>
        </span>
        <span class="status-divider" />
        <span class="status-item">
          播放中:
          <strong>{{ boundCount }}</strong>
          路
        </span>
      </div>
      <div class="statusbar-center">
        <template v-if="tourMode">
          <span class="status-item">轮巡 {{ tourInterval }}秒</span>
          <div class="tour-progress">
            <div class="tour-progress-bar" :style="{ width: tourProgress + '%' }" />
          </div>
        </template>
      </div>
      <div class="statusbar-right">
        <span class="status-item">{{ currentTime }}</span>
      </div>
    </div>

    <!-- 保存布局对话框 -->
    <el-dialog
      v-model="showSaveLayout"
      title="保存布局方案"
      width="460px"
      append-to-body
      @close="saveMode = 'create'; layoutName = ''; selectedOverwriteId = null"
    >
      <el-form label-width="90px">
        <el-form-item label="操作方式">
          <el-radio-group v-model="saveMode">
            <el-radio value="create">创建新方案</el-radio>
            <el-radio value="overwrite">覆盖现有方案</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="saveMode === 'create'">
          <el-form-item
            label="方案名称"
            :error="layoutNameError"
          >
            <el-input
              v-model="layoutName"
              placeholder="例如：4路默认布局"
              maxlength="64"
              @input="validateLayoutName"
            />
          </el-form-item>
        </template>

        <template v-if="saveMode === 'overwrite'">
          <el-form-item label="选择方案">
            <el-select v-model="selectedOverwriteId" placeholder="选择要覆盖的方案" style="width: 100%">
              <el-option v-for="ly in savedLayouts" :key="ly.id" :value="ly.id" :label="`${ly.name} (${ly.grid_type}路)`" />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item label="当前布局">
          <span style="font-size: 13px; color: var(--el-text-color-regular)">
            {{ layoutType }}路 · {{ boundCount }} 个窗口
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSaveLayout = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!canSave"
          :loading="savingLayout"
          @click="saveLayout"
        >
          {{ saveMode === 'overwrite' ? '覆盖保存' : '创建保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { Icon } from "@iconify/vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  Bell,
  FolderOpened,
  Search,
  Close,
  Camera,
  FullScreen,
  VideoCamera,
  VideoPause,
  Microphone,
  Delete,
  Monitor,
  Top,
  Back,
  Right,
  Bottom,
  ZoomIn,
  ZoomOut,
  Download,
  ArrowDown,
  Refresh,
} from "@element-plus/icons-vue";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import { getPlayUrls } from "@/api/module_video/preview";
import { getRealtimeAlarms, confirmAlarm } from "@/api/module_video/alarm";
import { getLayoutList, createLayout, updateLayout } from "@/api/module_video/layout";
import { startRecord, stopRecord } from "@/api/module_video/record";
import MultiCameraGrid from "@/components/Video/MultiCameraGrid.vue";

const layouts = [
  {
    value: "1",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="15" height="15" rx="1.5" fill="currentColor"/></svg>',
  },
  {
    value: "4",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="8.5" y="0.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="0.5" y="8.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="8.5" y="8.5" width="7" height="7" rx="1" fill="currentColor"/></svg>',
  },
  {
    value: "6",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="10" height="10" rx="1" fill="currentColor"/><rect x="11.5" y="0.5" width="4" height="4.3" rx="0.8" fill="currentColor"/><rect x="11.5" y="5.8" width="4" height="4.3" rx="0.8" fill="currentColor"/><rect x="0.5" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/><rect x="5.8" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/><rect x="11.2" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/></svg>',
  },
  {
    value: "8",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="11.5" height="11.5" rx="1" fill="currentColor"/><rect x="12.8" y="0.5" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="12.8" y="4.8" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="12.8" y="9.2" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="4.8" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="9.2" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="12.8" y="12.8" width="2.8" height="2.8" rx="0.8" fill="currentColor"/></svg>',
  },
  {
    value: "9",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="0.5" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="0.5" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/></svg>',
  },
  {
    value: "13",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="4.5" width="7" height="7" rx="1.5" fill="currentColor"/><rect x="12.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/></svg>',
  },
  {
    value: "16",
    svg: '<svg width="16" height="16" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/></svg>',
  },
];
const showLayoutPopover = ref(false);
const currentLayoutSvg = computed(() => {
  const layout = layouts.find((l) => l.value === layoutType.value);
  return layout?.svg || layouts[0].svg;
});

const protocols = [
  { value: "flv", label: "FLV" },
  { value: "hls", label: "HLS" },
  { value: "webrtc", label: "WebRTC" },
] as const;

const globalProtocol = ref<"flv" | "hls" | "webrtc">("flv");

const cameras = ref<any[]>([]);
const groupList = ref<any[]>([]);
const layoutType = ref("4");
const cameraBindings = ref<Record<string, any>>({});
const fullscreenWindow = ref<string | null>(null);
const router = useRouter();
const route = useRoute();
const alarmList = ref<any[]>([]);
const deviceSearch = ref("");
const alarmActiveFilter = ref("all");
const draggingCameraId = ref<number | null>(null);
const deviceTreeRef = ref<any>(null);
const gridRef = ref<InstanceType<typeof MultiCameraGrid> | null>(null);
const gridPanelRef = ref<HTMLElement | null>(null);
const toolbarRef = ref<HTMLElement | null>(null);
const isFullscreen = ref(false);
const showPtz = ref(false);
const showDevicePanel = ref(true);
const showAlarmPanel = ref(true);
const recordingWindows = ref<Record<string, boolean>>({});
const nextWindowId = ref(1);

const tourMode = ref(false);
const tourInterval = ref(30);
const tourProgress = ref(0);
const savedLayouts = ref<any[]>([]);
const selectedLayoutId = ref<number | null>(null);
const showSaveLayout = ref(false);
const saveMode = ref<"create" | "overwrite">("create");
const selectedOverwriteId = ref<number | null>(null);
const layoutName = ref("");
const savingLayout = ref(false);
let tourTimer: ReturnType<typeof setInterval> | null = null;
let tourTickTimer: ReturnType<typeof setInterval> | null = null;
let alarmPollTimer: ReturnType<typeof setInterval> | null = null;
let timeTimer: ReturnType<typeof setInterval> | null = null;
const currentTime = ref("");
let unmounted = false;

const alarmFilters = [
  { key: "all", label: "全部" },
  { key: "CRITICAL", label: "紧急" },
  { key: "WARNING", label: "警告" },
  { key: "INFO", label: "一般" },
];

const selectedLayoutName = computed(() => {
  if (!selectedLayoutId.value) return '';
  const layout = savedLayouts.value.find((l: any) => l.id === selectedLayoutId.value);
  return layout ? layout.name : '';
});

const boundCount = computed(() => Object.keys(cameraBindings.value).length);

const layoutNameError = computed(() => {
  if (saveMode.value !== 'create' || !layoutName.value.trim()) return '';
  const exists = savedLayouts.value.some((l: any) => l.name === layoutName.value.trim() && l.id !== selectedOverwriteId.value);
  return exists ? '该名称已存在' : '';
});

const canSave = computed(() => {
  if (saveMode.value === 'create') return !!layoutName.value.trim() && !layoutNameError.value;
  return !!selectedOverwriteId.value;
});

function validateLayoutName() {
  // triggers layoutNameError computed reactivity
}

const onlineCount = computed(() => cameras.value.filter((c: any) => c.status === "ONLINE").length);
const offlineCount = computed(
  () => cameras.value.filter((c: any) => c.status === "OFFLINE").length
);
const activeWindowId = ref<string | null>(null);

// Build integrated device tree: groups as folders, cameras as leaf nodes
const deviceTreeData = computed(() => {
  const q = deviceSearch.value.toLowerCase();

  // Build lookup: group_id → cameras
  const camMap = new Map<number | undefined, any[]>();
  for (const c of cameras.value) {
    if (q && !c.name.toLowerCase().includes(q)) continue;
    const gid = c.group_id;
    if (!camMap.has(gid)) camMap.set(gid, []);
    camMap.get(gid)!.push(c);
  }

  // Recursively build tree nodes from group tree, attaching cameras
  function buildGroupTree(nodes: any[]): any[] {
    const result: any[] = [];
    for (const g of nodes) {
      const gCameras = camMap.get(g.id) || [];
      const children: any[] = [];
      if (g.children?.length) {
        children.push(...buildGroupTree(g.children));
      }
      for (const c of gCameras) {
        children.push({ id: `cam-${c.id}`, label: c.name, type: "camera", camera: c });
      }
      // Count cameras: direct + from all child groups
      let totalCount = gCameras.length;
      for (const child of children) {
        if (child.type === "group") totalCount += child.cameraCount || 0;
      }
      result.push({
        id: `group-${g.id}`,
        label: g.name,
        type: "group",
        cameraCount: totalCount,
        children,
      });
    }
    return result;
  }

  // Ungrouped cameras
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

const displayBindings = computed(() => {
  if (fullscreenWindow.value) {
    const cam = cameraBindings.value[fullscreenWindow.value];
    return { w1: cam || null };
  }
  return cameraBindings.value;
});

const filteredAlarms = computed(() => {
  if (alarmActiveFilter.value === "all") return alarmList.value;
  return alarmList.value.filter((a: any) => a.severity === alarmActiveFilter.value);
});

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

function isCameraBound(cameraId: number) {
  return Object.values(cameraBindings.value).some((c: any) => c?.id === cameraId);
}

function filterDeviceNode(value: string, data: any) {
  if (!value) return true;
  if (data.type === "camera") return data.label.toLowerCase().includes(value.toLowerCase());
  if (data.type === "group" || data.type === "root") {
    return data.children?.some((child: any) => filterDeviceNode(value, child));
  }
  return true;
}

function onDeviceNodeClick(data: any) {
  if (data.type === "camera") {
    handleAddToAnyWindow(data.camera);
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

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameras.value = res.data?.data?.items || [];
  } catch {
    /* noop */
  }
}

async function fetchAlarms() {
  try {
    const res = await getRealtimeAlarms();
    alarmList.value = (res.data?.data || []).slice(0, 100);
  } catch {
    /* noop */
  }
}

async function getOrCreatePlayUrl(camera: any): Promise<any> {
  if (camera.play_urls) return camera;
  try {
    const res = await getPlayUrls(camera.id);
    return { ...camera, play_urls: res.data?.data || res.data || {} };
  } catch {
    return camera;
  }
}

async function handleAddToAnyWindow(camera: any, targetWindowId?: string) {
  const existing = Object.entries(cameraBindings.value).find(
    ([, c]: [string, any]) => c?.id === camera.id
  );
  if (existing) {
    const [existingId] = existing;
    if (targetWindowId && existingId !== targetWindowId) {
      const newBindings = { ...cameraBindings.value };
      const targetCam = newBindings[targetWindowId] || null;
      delete newBindings[existingId];
      if (targetCam) {
        newBindings[targetWindowId] = await getOrCreatePlayUrl(camera);
        newBindings[existingId] = targetCam;
      } else {
        newBindings[targetWindowId] = await getOrCreatePlayUrl(camera);
      }
      cameraBindings.value = newBindings;
    } else if (!targetWindowId) {
      activeWindowId.value = existingId;
    }
    return;
  }
  const cam = await getOrCreatePlayUrl(camera);
  if (targetWindowId && cameraBindings.value[targetWindowId]) {
    cameraBindings.value = { ...cameraBindings.value, [targetWindowId]: cam };
  } else {
    const wid = targetWindowId || `w${nextWindowId.value++}`;
    cameraBindings.value = { ...cameraBindings.value, [wid]: cam };
  }
}

function handleOpenCamera(cameraId: number, targetWindowId?: string) {
  const camera = cameras.value.find((c: any) => c.id === cameraId);
  if (camera) handleAddToAnyWindow(camera, targetWindowId);
}

function handleRemoveCamera(windowId: string) {
  const newBindings = { ...cameraBindings.value };
  delete newBindings[windowId];
  cameraBindings.value = newBindings;
}

function handleRemoveFromAllWindows(cameraId: number) {
  const newBindings: Record<string, any> = {};
  for (const [id, cam] of Object.entries(cameraBindings.value)) {
    if ((cam as any)?.id !== cameraId) {
      newBindings[id] = cam;
    }
  }
  cameraBindings.value = newBindings;
}

function handleSwapCamera(fromId: string, toId: string) {
  const newBindings = { ...cameraBindings.value };
  const tmp = newBindings[fromId];
  newBindings[fromId] = newBindings[toId] || null;
  newBindings[toId] = tmp || null;
  cameraBindings.value = newBindings;
}

function handlePtzToggle(windowId: string) {
  activeWindowId.value = windowId;
  showPtz.value = !showPtz.value;
}

function handleClearAll() {
  cameraBindings.value = {};
  nextWindowId.value = 1;
  recordingWindows.value = {};
}

// ---- Layout save/load ----

function openSaveLayout() {
  layoutName.value = "";
  saveMode.value = "create";
  selectedOverwriteId.value = null;
  showSaveLayout.value = true;
}

async function saveLayout() {
  savingLayout.value = true;
  const windows: Record<string, number> = {};
  for (const [wid, cam] of Object.entries(cameraBindings.value)) {
    if (cam?.id) windows[wid] = cam.id;
  }
  const data = {
    name: saveMode.value === 'create' ? layoutName.value.trim() : '',
    grid_type: layoutType.value,
    layout_config: { windows, grid_type: layoutType.value },
  };
  try {
    if (saveMode.value === 'overwrite' && selectedOverwriteId.value) {
      const target = savedLayouts.value.find((l: any) => l.id === selectedOverwriteId.value);
      if (target) {
        data.name = target.name;
        await updateLayout(selectedOverwriteId.value, data);
      }
    } else {
      await createLayout(data);
    }
    showSaveLayout.value = false;
    fetchSavedLayouts();
  } catch {}
  savingLayout.value = false;
}

async function fetchSavedLayouts() {
  try {
    const res = await getLayoutList({ page_size: 50 });
    savedLayouts.value = res.data?.data?.items || [];
  } catch {
    savedLayouts.value = [];
  }
}

function handleLayoutSelect(layout: any) {
  if (!layout) return;
  selectedLayoutId.value = layout.id;
  applyLayout(layout);
}

async function applyLayout(layout: any) {
  const config = layout.layout_config;
  if (!config?.windows) return;
  handleClearAll();
  layoutType.value = config.grid_type || layout.grid_type || "4";
  await nextTick();
  const entries = Object.entries(config.windows) as [string, number][];
  entries.sort((a, b) => {
    const na = parseInt(a[0].replace(/\D/g, "")) || 0;
    const nb = parseInt(b[0].replace(/\D/g, "")) || 0;
    return na - nb;
  });
  for (const [wid, camId] of entries) {
    const cam = cameras.value.find((c: any) => c.id === camId);
    if (cam) handleAddToAnyWindow(cam, wid);
  }
}

function handleWindowFullscreen(windowId: string) {
  if (fullscreenWindow.value === windowId) {
    fullscreenWindow.value = null;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    }
  } else {
    fullscreenWindow.value = windowId;
    const el = gridPanelRef.value;
    if (el && !document.fullscreenElement) {
      el.requestFullscreen().catch(() => {});
    }
  }
}

function handleSnapshot(windowId?: string) {
  // Snapshot handled by MultiCameraGrid's built-in capture
  // Find the video in the active window
  const gridEl = gridPanelRef.value;
  if (!gridEl) return;
  const video = gridEl.querySelector("video");
  if (video && video.videoWidth > 0) {
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    const link = document.createElement("a");
    const name = windowId || "live";
    link.download = `snapshot_${name}_${Date.now()}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }
}

function handleToggleAudio() {
  // Audio toggle logic
}

function handleClearAlarms() {
  alarmList.value = [];
}

async function handleStartRecord(windowId: string, cameraId: number, streamId: string) {
  try {
    await startRecord(cameraId, streamId);
    recordingWindows.value = { ...recordingWindows.value, [windowId]: true };
  } catch {
    /* noop */
  }
}

async function handleStopRecord(windowId: string, streamId: string) {
  try {
    await stopRecord(streamId);
    const copy = { ...recordingWindows.value };
    delete copy[windowId];
    recordingWindows.value = copy;
    ElMessage.success({
      message: "录像已保存",
      duration: 4000,
    });
  } catch {
    /* noop */
  }
}

function goToPlayback(cameraId?: number) {
  const query = cameraId ? { camera_id: cameraId } : {};
  router.push({ path: "/video/playback", query });
}

function handleToggleFullscreen() {
  const el = gridPanelRef.value;
  if (!el) return;
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    el.requestFullscreen();
  }
}

function exitFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement;
  if (!document.fullscreenElement && fullscreenWindow.value) {
    fullscreenWindow.value = null;
  }
}

async function handleConfirmAlarm(id: number) {
  try {
    await confirmAlarm(id, "CONFIRMED");
    alarmList.value = alarmList.value.filter((a: any) => a.id !== id);
  } catch {
    /* noop */
  }
}

function handleAlarmClick(alarm: any) {
  // Switch to the camera that triggered the alarm
  if (alarm.camera_id) {
    const camera = cameras.value.find((c: any) => c.id === alarm.camera_id);
    if (camera) handleAddToAnyWindow(camera);
  }
}

function formatTime(t: string | undefined | null) {
  if (!t) return "";
  try {
    if (t.includes(" ")) {
      const parts = t.split(" ");
      return parts[1] || t;
    }
    return t;
  } catch {
    return t;
  }
}

function severityClass(severity: string) {
  switch ((severity || "").toUpperCase()) {
    case "CRITICAL":
      return "alarm-critical";
    case "WARNING":
      return "alarm-warning";
    default:
      return "alarm-info";
  }
}

function severityTag(severity: string) {
  switch ((severity || "").toUpperCase()) {
    case "CRITICAL":
      return "danger";
    case "WARNING":
      return "warning";
    default:
      return "info";
  }
}

function onDeviceDragStart(camera: any, event: DragEvent) {
  draggingCameraId.value = camera.id;
  event.dataTransfer?.setData("application/camera", JSON.stringify(camera));

  const ghost = document.createElement("div");
  ghost.textContent = camera.name || "摄像头";
  ghost.style.cssText =
    "display:flex;align-items:center;gap:6px;padding:4px 10px;font-size:13px;color:#fff;background:rgba(0,0,0,.75);border-radius:4px;white-space:nowrap";
  const icon = document.createElement("span");
  icon.innerHTML = "📷";
  icon.style.fontSize = "14px";
  ghost.prepend(icon);
  document.body.appendChild(ghost);
  event.dataTransfer?.setDragImage(ghost, 4, 4);
  setTimeout(() => ghost.remove(), 0);
}

function onDeviceDragEnd() {
  draggingCameraId.value = null;
}

function handlePtz() {
  // PTZ control would be sent to the backend/ZLM
}

function updateTime() {
  const now = new Date();
  currentTime.value = now.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

// Tour mode: cycle through cameras with progress indicator
watch(tourMode, (val) => {
  if (tourTimer) clearInterval(tourTimer);
  if (tourTickTimer) clearInterval(tourTickTimer);
  tourTimer = null;
  tourTickTimer = null;
  tourProgress.value = 0;
  if (val) {
    const intervalMs = tourInterval.value * 1000;
    tourTimer = setInterval(() => {
      tourProgress.value = 0;
      const online = cameras.value.filter((c: any) => c.status === "ONLINE");
      if (online.length === 0) return;
      const layoutCount = parseInt(layoutType.value);
      const currentIds = Object.values(cameraBindings.value).map((c: any) => c?.id);
      const nextBatch: any[] = [];
      for (const cam of online) {
        if (!currentIds.includes(cam.id)) {
          nextBatch.push(cam);
          if (nextBatch.length >= layoutCount) break;
        }
      }
      if (nextBatch.length === 0) {
        handleClearAll();
        return;
      }
      handleClearAll();
      nextWindowId.value = 1;
      nextBatch.forEach((cam: any) => handleAddToAnyWindow(cam));
    }, intervalMs);
    tourTickTimer = setInterval(() => {
      tourProgress.value = Math.min(100, tourProgress.value + (2000 / intervalMs) * 100);
    }, 2000);
  }
});

watch(layoutType, (nv, ov) => {
  console.log("[LivePage] layoutType changed", ov, "->", nv);
  const max = parseInt(layoutType.value);
  const entries = Object.entries(cameraBindings.value);
  if (entries.length > max) {
    const newBindings: Record<string, any> = {};
    entries.slice(0, max).forEach(([id, cam]) => {
      newBindings[id] = cam;
    });
    cameraBindings.value = newBindings;
  }
});

onMounted(() => {
  console.log("[LivePage] onMounted");
  fetchCameras();
  fetchGroups();
  fetchAlarms();
  fetchSavedLayouts();
  alarmPollTimer = setInterval(fetchAlarms, 5000);
  updateTime();
  timeTimer = setInterval(updateTime, 1000);
  document.addEventListener("fullscreenchange", onFullscreenChange);
  // Auto-load layout from query param (from layout management page)
  const layoutId = route.query.layout_id ? Number(route.query.layout_id) : null;
  if (layoutId) {
    console.log("[LivePage] auto-loading layout", layoutId);
    getLayoutList({ page_size: 50 })
      .then((res: any) => {
        if (unmounted) {
          console.log("[LivePage] getLayoutList resolved after unmount, skipping");
          return;
        }
        const items = res.data?.data?.items || [];
        const layout = items.find((i: any) => i.id === layoutId);
        if (layout) {
          console.log("[LivePage] found layout, creating watcher");
          selectedLayoutId.value = layout.id;
          const unwatch = watch(
            cameras,
            (cams) => {
              if (unmounted) {
                console.log("[LivePage] layout watcher fired after unmount");
                unwatch();
                return;
              }
              if (cams.length > 0) {
                console.log("[LivePage] applying layout via watcher");
                applyLayout(layout);
                unwatch();
              }
            },
            { immediate: true }
          );
        }
      })
      .catch((e: any) => {
        console.warn("[LivePage] getLayoutList failed", e);
      });
  }
});

let defaultLayoutApplied = false;

// Auto-load default layout when savedLayouts loads
watch(savedLayouts, (layouts) => {
  if (unmounted || defaultLayoutApplied) return;
  if (route.query.layout_id) return;
  const dl = layouts.find((l: any) => l.is_default);
  if (!dl) return;
  defaultLayoutApplied = true;
  selectedLayoutId.value = dl.id;
  const uw = watch(cameras, (cams) => {
    if (unmounted) { uw(); return; }
    if (cams.length > 0) {
      applyLayout(dl);
      uw();
    }
  }, { immediate: true });
});

onBeforeUnmount(() => {
  console.log("[LivePage] onBeforeUnmount");
  unmounted = true;
  if (alarmPollTimer) {
    clearInterval(alarmPollTimer);
    console.log("[LivePage] cleared alarmPollTimer");
  }
  if (tourTimer) {
    clearInterval(tourTimer);
  }
  if (tourTickTimer) {
    clearInterval(tourTickTimer);
  }
  if (timeTimer) {
    clearInterval(timeTimer);
  }
  document.removeEventListener("fullscreenchange", onFullscreenChange);
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
});
</script>

<style scoped>
.live-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  font-size: 13px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
}

/* ==================== Toolbar ==================== */
.live-toolbar {
  display: flex;
  flex-shrink: 0;
  flex-wrap: nowrap;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border-bottom: 1px solid var(--el-border-color-light);
}

.toolbar-divider {
  flex-shrink: 0;
  width: 1px;
  height: 20px;
  background: var(--el-border-color);
}

.toolbar-right {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  align-items: center;
  margin-left: auto;
}

.toolbar-group {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  align-items: center;
}

.toolbar-brand {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
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

.toolbar-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.layout-buttons {
  display: flex;
  gap: 2px;
}

.layout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  font-size: 16px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  transition: all 0.15s;
}
.layout-btn-current {
  width: 28px;
  height: 28px;
}
.layout-btn:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
.layout-btn:disabled:hover {
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-color: var(--el-border-color);
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

.panel-toggles {
  display: flex;
  gap: 6px;
  margin-right: 8px;
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

.more-btn {
  font-size: 18px;
  line-height: 1;
}

.layout-popover-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  padding: 2px;
}
.layout-popover-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 4px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  transition: all 0.15s;
}
.layout-popover-item:hover {
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color-hover);
}
.layout-popover-item.active {
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 10%, transparent);
  border-color: var(--el-color-primary);
}

.scheme-split {
  display: flex;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;
  transition: border-color 0.15s;
}
.scheme-split:hover {
  border-color: var(--el-border-color-hover);
}
.scheme-split-select {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-fill-color);
  border: none;
  border-right: 1px solid var(--el-border-color);
  white-space: nowrap;
  transition: background 0.15s;
}
.scheme-split-select:hover {
  background: var(--el-fill-color-light);
}
.scheme-arrow {
  font-size: 12px;
  margin-left: 2px;
}
.scheme-split-save {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  font-size: 15px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: none;
  transition: all 0.15s;
}
.scheme-split-save:hover:not(:disabled) {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.scheme-split-save:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}
.count-total::before {
  content: "共 ";
}
.count-total::after {
  content: " 台";
}
.count-total {
  color: var(--el-text-color-secondary);
}

.count-online::before {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  vertical-align: middle;
  content: "";
  background: var(--el-color-success);
  border-radius: 50%;
}
.count-online::after {
  content: " 在线";
}
.count-online {
  color: var(--el-color-success);
}

.count-offline::before {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  vertical-align: middle;
  content: "";
  background: var(--el-color-info);
  border-radius: 50%;
}
.count-offline::after {
  content: " 离线";
}
.count-offline {
  color: var(--el-color-info);
}

/* ==================== Main Layout ==================== */
.live-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ==================== Device Panel (Left) ==================== */
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

.panel-count {
  padding: 0 6px;
  margin-left: auto;
  font-size: 11px;
  line-height: 18px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color);
  border-radius: 8px;
}

.panel-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}

.panel-toggle {
  z-index: 5;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-light);
  transition: all 0.2s;
}
.panel-toggle:hover {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}

.panel-toggle-left {
  margin-right: -1px;
  border-left: none;
  border-radius: 0 3px 3px 0;
}
.panel-toggle-right {
  margin-left: -1px;
  border-right: none;
  border-radius: 3px 0 0 3px;
}

.live-device-panel.collapsed {
  width: 0;
  padding: 0;
  border-right-color: transparent;
}

.panel-header :deep(.el-button) {
  color: var(--el-text-color-secondary);
}
.panel-header :deep(.el-button:hover) {
  color: var(--el-text-color-primary);
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
  width: 100%;
  padding-right: 4px;
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

.device-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  flex-shrink: 0;
}
.tree-camera-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-online {
  background: var(--el-color-success);
  box-shadow: 0 0 4px color-mix(in srgb, var(--el-color-success) 40%, transparent);
}
.status-offline {
  background: var(--el-color-info);
}
.status-unknown {
  background: var(--el-color-warning);
}

/* ==================== Grid Panel (Center) ==================== */
.live-grid-panel {
  position: relative;
  flex: 1;
  overflow: hidden;
}

/* ==================== PTZ Panel ==================== */
.ptz-panel {
  position: absolute;
  bottom: 12px;
  left: 12px;
  z-index: 10;
  width: 180px;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.ptz-header {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 6px 8px;
  font-size: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.ptz-window-tag {
  margin-left: auto;
}

.ptz-close {
  width: 20px;
  height: 20px;
  padding: 0;
}

.ptz-body {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 8px;
}

.ptz-dpad {
  display: grid;
  grid-template-rows: 28px 28px 28px;
  grid-template-columns: 28px 28px 28px;
  gap: 2px;
}

.ptz-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  transition: all 0.1s;
}
.ptz-btn:hover {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
.ptz-btn:active {
  background: var(--el-color-primary-light-7);
}
.ptz-btn:disabled {
  cursor: default;
  opacity: 0.3;
}

.ptz-up {
  grid-row: 1;
  grid-column: 2;
}
.ptz-left {
  grid-row: 2;
  grid-column: 1;
}
.ptz-center {
  grid-row: 2;
  grid-column: 2;
}
.ptz-right {
  grid-row: 2;
  grid-column: 3;
}
.ptz-down {
  grid-row: 3;
  grid-column: 2;
}

.ptz-zoom {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease-out;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

/* ==================== Alarm Panel (Right) ==================== */
.live-alarm-panel {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 260px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border-left: 1px solid var(--el-border-color-light);
}

.panel-header-actions {
  display: flex;
  align-items: center;
  margin-left: auto;
}

.live-alarm-panel.collapsed {
  width: 0;
  padding: 0;
  border-left-color: transparent;
}

.alarm-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: var(--el-color-danger);
  border-radius: 9px;
}

.alarm-filters {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 8px;
}

.alarm-filters :deep(.el-check-tag) {
  padding: 2px 10px;
  font-size: 12px;
  border-radius: 4px;
}

.alarm-filters :deep(.filter-CRITICAL.checked) {
  color: var(--el-color-danger);
  background: color-mix(in srgb, var(--el-color-danger) 20%, transparent);
  border-color: var(--el-color-danger);
}

.alarm-filters :deep(.filter-WARNING.checked) {
  color: var(--el-color-warning);
  background: color-mix(in srgb, var(--el-color-warning) 20%, transparent);
  border-color: var(--el-color-warning);
}

.alarm-list {
  flex: 1;
  padding: 4px 6px;
  overflow-y: auto;
}

.alarm-list::-webkit-scrollbar {
  width: 6px;
}
.alarm-list::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 3px;
}
.alarm-list::-webkit-scrollbar-track {
  background: transparent;
}

.alarm-item {
  padding: 8px;
  margin: 3px 0;
  font-size: 12px;
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  border-left: 3px solid transparent;
  border-radius: 4px;
  transition: background 0.15s;
}

.alarm-item:hover {
  background: var(--el-fill-color);
}

.alarm-item.alarm-critical {
  border-left-color: var(--el-color-danger);
}

.alarm-item.alarm-warning {
  border-left-color: var(--el-color-warning);
}

.alarm-item.alarm-info {
  border-left-color: var(--el-color-info);
}

.alarm-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

.alarm-camera-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.alarm-severity-tag {
  flex-shrink: 0;
}

.alarm-type-text {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.alarm-item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.alarm-time {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

/* ==================== Status Bar (Bottom) ==================== */
.live-statusbar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 3px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-blank);
  border-top: 1px solid var(--el-border-color-light);
}

.statusbar-left,
.statusbar-center,
.statusbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}

.status-item strong {
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.status-item.online strong {
  color: var(--el-color-success);
}

.status-item.offline strong {
  color: var(--el-color-info);
}

.status-divider {
  width: 1px;
  height: 12px;
  background: var(--el-border-color);
}

.tour-progress {
  width: 80px;
  height: 4px;
  overflow: hidden;
  background: var(--el-fill-color);
  border-radius: 2px;
}
.tour-progress-bar {
  height: 100%;
  background: var(--el-color-primary);
  border-radius: 2px;
  transition: width 1s linear;
}

/* ==================== Fullscreen Mode ==================== */
.live-grid-panel:fullscreen {
  width: 100vw;
  height: 100vh;
  padding: 0;
  background: #000;
}
.live-grid-panel:fullscreen .multi-camera-grid {
  gap: 0;
  padding: 0;
  background: #000;
}
.live-grid-panel:fullscreen :deep(.window-watermark) {
  padding: 24px 12px 8px;
  font-size: 14px;
}
.live-grid-panel:fullscreen :deep(.window-actions) {
  top: 10px;
  right: 10px;
}
.live-grid-panel:fullscreen :deep(.action-btn) {
  width: 32px;
  height: 32px;
  font-size: 16px;
}
</style>
