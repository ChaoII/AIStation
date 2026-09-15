<!-- 边缘事件实时流：WS 实时追加 + 历史分页 + 详情抽屉（命中叶子高亮） -->
<template>
  <div class="app-container edge-event-page">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleFilterQuery"
      @reset-click="handleFilterReset"
    />

    <!-- 视图切换 + 实时控制条 -->
    <el-card class="edge-event-switch" shadow="never">
      <div class="edge-event-switch__bar">
        <el-radio-group v-model="activeView">
          <el-radio-button value="live">实时</el-radio-button>
          <el-radio-button value="history">历史</el-radio-button>
        </el-radio-group>

        <div v-if="activeView === 'live'" class="edge-event-switch__right">
          <el-tag :type="wsStatusTag" size="small">{{ wsStatusLabel }}</el-tag>
          <el-button size="small" @click="togglePause">{{ pauseLabel }}</el-button>
          <el-button size="small" @click="clearLive">清屏</el-button>
          <span class="edge-event-switch__count">
            展示 {{ filteredLiveRows.length }} / 缓存 {{ liveRows.length }}（上限 {{ LIVE_LIMIT }}）
          </span>
        </div>
        <div v-else class="edge-event-switch__count">按筛选条件查询历史事件</div>
      </div>
    </el-card>

    <!-- 实时视图：WS 追加，滚动上限 200 行 -->
    <el-card
      v-if="activeView === 'live'"
      class="data-table"
      shadow="never"
      :body-style="liveBodyStyle"
    >
      <div class="data-table__content">
        <el-table
          v-loading="false"
          row-key="id"
          :data="filteredLiveRows"
          height="100%"
          border
          stripe
          @row-click="handleRowClick"
        >
          <template #empty>
            <el-empty :image-size="80" description="等待实时事件推送…" />
          </template>
          <el-table-column label="时间" width="170">
            <template #default="scope">{{ formatTime(scope.row.ts) }}</template>
          </el-table-column>
          <el-table-column label="相机" min-width="130" show-overflow-tooltip>
            <template #default="scope">{{ cameraLabel(scope.row.camera_id) }}</template>
          </el-table-column>
          <el-table-column label="场景" min-width="130" show-overflow-tooltip>
            <template #default="scope">{{ sceneLabel(scope.row.algorithm_type) }}</template>
          </el-table-column>
          <el-table-column label="目标摘要" min-width="180" show-overflow-tooltip>
            <template #default="scope">{{ summaryText(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="延迟" width="100" align="center">
            <template #default="scope">
              {{ scope.row.latency_ms != null ? `${scope.row.latency_ms} ms` : "-" }}
            </template>
          </el-table-column>
          <el-table-column label="命中" width="90" align="center">
            <template #default="scope">
              <el-tag :type="scope.row.matched ? 'success' : 'info'" size="small" effect="dark">
                {{ scope.row.matched ? "命中" : "未命中" }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 历史视图：分页查询 -->
    <PageContent v-else ref="contentRef" :content-config="contentConfig">
      <template #table="{ data, loading }">
        <div class="data-table__content">
          <el-table
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @row-click="handleRowClick"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column label="时间" width="170">
              <template #default="scope">{{ formatTime(scope.row.ts) }}</template>
            </el-table-column>
            <el-table-column label="相机" min-width="130" show-overflow-tooltip>
              <template #default="scope">{{ cameraLabel(scope.row.camera_id) }}</template>
            </el-table-column>
            <el-table-column label="场景" min-width="130" show-overflow-tooltip>
              <template #default="scope">{{ sceneLabel(scope.row.algorithm_type) }}</template>
            </el-table-column>
            <el-table-column label="目标摘要" min-width="180" show-overflow-tooltip>
              <template #default="scope">{{ summaryText(scope.row) }}</template>
            </el-table-column>
            <el-table-column label="延迟" width="100" align="center">
              <template #default="scope">
                {{ scope.row.latency_ms != null ? `${scope.row.latency_ms} ms` : "-" }}
              </template>
            </el-table-column>
            <el-table-column label="命中" width="90" align="center">
              <template #default="scope">
                <el-tag :type="scope.row.matched ? 'success' : 'info'" size="small" effect="dark">
                  {{ scope.row.matched ? "命中" : "未命中" }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawer.visible" :title="drawerTitle" size="620px">
      <div v-if="drawer.detail" class="event-detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="事件时间" :span="2">
            {{ formatTime(drawer.detail.ts) }}
          </el-descriptions-item>
          <el-descriptions-item label="相机">
            {{ cameraLabel(drawer.detail.camera_id) }}
          </el-descriptions-item>
          <el-descriptions-item label="场景">
            {{ sceneLabel(drawer.detail.algorithm_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="任务ID">
            {{ drawer.detail.task_id ?? "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="边缘设备">
            {{ drawer.detail.edge_code || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="延迟">
            {{ drawer.detail.latency_ms != null ? `${drawer.detail.latency_ms} ms` : "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="命中">
            <el-tag :type="drawer.detail.matched ? 'success' : 'info'" size="small" effect="dark">
              {{ drawer.detail.matched ? "命中" : "未命中" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="命中规则">
            {{ drawer.detail.matched_rule_id ?? "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="快照引用">
            <el-link
              v-if="isHttpUrl(drawer.detail.snapshot_ref)"
              type="primary"
              :href="drawer.detail.snapshot_ref"
              target="_blank"
            >
              {{ drawer.detail.snapshot_ref }}
            </el-link>
            <span v-else>{{ drawer.detail.snapshot_ref || "无" }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 快照叠加查看器：src 为 http(s) 或受保护相对路径时组件内部鉴权取图；为空显示占位 -->
        <div class="event-detail__section">
          <SnapshotOverlayViewer
            :src="drawer.detail.snapshot_ref || null"
            :objects="drawer.detail.objects ?? drawer.detail.detections ?? []"
            height="360px"
          />
        </div>

        <div class="event-detail__section">
          <div class="event-detail__title">命中叶子</div>
          <div class="event-detail__leaves">
            <el-tag
              v-for="(leaf, index) in drawer.detail.matched_leaves || []"
              :key="index"
              :type="leafTagType(leaf)"
              size="small"
              effect="dark"
            >
              <span class="event-detail__leaf-path">{{ leaf.path || leaf.subject }}</span>
              <span v-if="leaf.negated" class="event-detail__leaf-neg">非</span>
              {{ leaf.detail || leaf.subject }}
            </el-tag>
            <span v-if="!(drawer.detail.matched_leaves || []).length" class="text-muted">
              {{ drawer.detail.matched ? "（无叶子明细）" : "未命中任何条件" }}
            </span>
          </div>
        </div>

        <div class="event-detail__section">
          <div class="event-detail__title">检测目标（{{ detectionRows.length }}）</div>
          <el-table :data="detectionRows" border stripe size="small" max-height="320px">
            <template #empty>
              <el-empty :image-size="60" description="无检测目标" />
            </template>
            <el-table-column prop="label" label="标签" width="110" show-overflow-tooltip />
            <el-table-column label="置信度" width="90" align="center">
              <template #default="scope">{{ fmtConfidence(scope.row.confidence) }}</template>
            </el-table-column>
            <el-table-column prop="track_id" label="track_id" width="90" align="center" />
            <el-table-column label="属性" min-width="180" show-overflow-tooltip>
              <template #default="scope">{{ formatAttributes(scope.row.attributes) }}</template>
            </el-table-column>
            <el-table-column prop="text" label="文本" min-width="120" show-overflow-tooltip />
          </el-table>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { Auth } from "@/utils/auth";
import { getCameraList } from "@/api/module_video/camera";
import { getSceneCatalog, type SceneDefinition } from "@/api/module_video/scene";
import {
  buildEdgeEventWsUrl,
  getEdgeEventDetail,
  getEdgeEventList,
  type EdgeEventDetail,
  type EdgeEventItem,
  type EdgeEventMatchedLeaf,
  type EdgeEventObject,
  type EdgeEventQuery,
} from "@/api/module_video/edge_event";
import { cachedOptions } from "@/composables/useOptions";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import SnapshotOverlayViewer from "@/components/SnapshotOverlayViewer/index.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";

defineOptions({ name: "EdgeEventStream" });

/** 实时缓存上限 */
const LIVE_LIMIT = 200;

const { searchRef, contentRef } = useCrudList();

const activeView = ref<"live" | "history">("live");

const cameraOptions = ref<any[]>([]);
const sceneOptions = ref<SceneDefinition[]>([]);

/** 已提交的筛选条件（查询/重置时更新；实时视图据此做客户端过滤） */
const activeFilters = ref<Record<string, any>>({});

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:edge",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "camera_id",
      label: "相机",
      type: "select",
      options: [],
      attrs: {
        placeholder: "请选择相机",
        clearable: true,
        filterable: true,
        style: { width: "180px" },
        onVisibleChange: (visible: boolean) => {
          if (visible) void ensureCameraOptions();
        },
      },
    },
    {
      prop: "algorithm_type",
      label: "场景",
      type: "select",
      options: [],
      attrs: {
        placeholder: "请选择场景",
        clearable: true,
        filterable: true,
        style: { width: "180px" },
        onVisibleChange: (visible: boolean) => {
          if (visible) void ensureSceneOptions();
        },
      },
    },
    {
      prop: "matched",
      label: "是否命中",
      type: "select",
      options: [
        { label: "命中", value: true },
        { label: "未命中", value: false },
      ],
      attrs: { placeholder: "请选择", clearable: true, style: { width: "140px" } },
    },
    {
      prop: "time_range",
      label: "时间范围",
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: "至",
        startPlaceholder: "开始时间",
        endPlaceholder: "结束时间",
        style: { width: "360px" },
      },
    },
    {
      prop: "keyword",
      label: "关键字",
      type: "input",
      attrs: { placeholder: "目标 label / 文本", clearable: true },
    },
  ],
});

const historyCols = reactive([
  { prop: "ts", label: "时间", show: true },
  { prop: "camera_id", label: "相机", show: true },
  { prop: "algorithm_type", label: "场景", show: true },
  { prop: "labels", label: "目标摘要", show: true },
  { prop: "latency_ms", label: "延迟", show: true },
  { prop: "matched", label: "命中", show: true },
]);

const contentConfig = reactive<IContentConfig<Record<string, any>>>({
  permPrefix: "module_video:edge",
  pk: "id",
  cols: historyCols as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 20, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  initialFetch: false,
  indexAction: async (params) => {
    const res = await getEdgeEventList(normalizeQuery(params));
    const data = res.data?.data ?? {};
    return { total: data.total ?? 0, list: data.items ?? [] };
  },
});

const drawer = reactive<{ visible: boolean; detail: EdgeEventDetail | null }>({
  visible: false,
  detail: null,
});

const drawerTitle = computed(() => {
  const eventId = drawer.detail?.event_id;
  return eventId ? `边缘事件详情 - ${eventId}` : "边缘事件详情";
});

/** 实时视图 */
const liveRows = ref<EdgeEventItem[]>([]);
const paused = ref(false);
const pendingCount = ref(0);
const pendingRows: EdgeEventItem[] = [];

const pauseLabel = computed(() => {
  if (!paused.value) return "暂停";
  return pendingCount.value ? `继续（${pendingCount.value}）` : "继续";
});

const wsStatus = ref<"closed" | "connecting" | "open">("closed");
const wsStatusLabel = computed(
  () => ({ closed: "未连接", connecting: "连接中", open: "已连接" })[wsStatus.value]
);
const wsStatusTag = computed(
  () =>
    ({ closed: "info", connecting: "warning", open: "success" })[wsStatus.value] as
      "info" | "warning" | "success"
);

let ws: WebSocket | null = null;
let closedByUs = false;
let retry = 0;
let reconnectTimer: number | null = null;

/** 实时行按已提交筛选条件过滤 */
const filteredLiveRows = computed(() => liveRows.value.filter(matchesFilters));

function normalizeQuery(raw: Record<string, any>): EdgeEventQuery {
  const query: EdgeEventQuery = {};
  if (raw.camera_id !== undefined && raw.camera_id !== null && raw.camera_id !== "") {
    query.camera_id = raw.camera_id;
  }
  if (raw.task_id !== undefined && raw.task_id !== null && raw.task_id !== "") {
    query.task_id = raw.task_id;
  }
  if (raw.algorithm_type) query.algorithm_type = raw.algorithm_type;
  if (raw.matched !== undefined && raw.matched !== null && raw.matched !== "") {
    query.matched = Boolean(raw.matched);
  }
  if (raw.keyword) query.keyword = String(raw.keyword).trim();
  const range = raw.time_range;
  if (Array.isArray(range) && range.length === 2 && range[0] && range[1]) {
    query.start_time = range[0];
    query.end_time = range[1];
  }
  if (raw.page_no) query.page_no = raw.page_no;
  if (raw.page_size) query.page_size = raw.page_size;
  return query;
}

function matchesFilters(row: EdgeEventItem): boolean {
  const f = activeFilters.value || {};
  if (f.camera_id != null && f.camera_id !== "" && row.camera_id !== f.camera_id) return false;
  if (f.algorithm_type && row.algorithm_type !== f.algorithm_type) return false;
  if (f.matched !== undefined && f.matched !== null && f.matched !== "") {
    if (Boolean(row.matched) !== Boolean(f.matched)) return false;
  }
  if (f.keyword) {
    const keyword = String(f.keyword).toLowerCase();
    const haystack = (row.labels || []).join(" ").toLowerCase();
    if (!haystack.includes(keyword)) return false;
  }
  if (
    Array.isArray(f.time_range) &&
    f.time_range.length === 2 &&
    f.time_range[0] &&
    f.time_range[1]
  ) {
    const t = row.ts ? new Date(row.ts).getTime() : NaN;
    const start = new Date(f.time_range[0]).getTime();
    const end = new Date(f.time_range[1]).getTime();
    if (!Number.isNaN(t) && !Number.isNaN(start) && t < start) return false;
    if (!Number.isNaN(t) && !Number.isNaN(end) && t > end) return false;
  }
  return true;
}

function handleFilterQuery(params: Record<string, any>) {
  activeFilters.value = { ...params };
  if (activeView.value === "history") {
    // 历史模式立即按新条件刷新第一页
    nextTick(() => contentRef.value?.fetchPageData(activeFilters.value, true));
  }
}

function handleFilterReset(params: Record<string, any>) {
  activeFilters.value = { ...params };
  if (activeView.value === "history") {
    nextTick(() => contentRef.value?.fetchPageData(activeFilters.value, true));
  }
}

function appendLive(row: EdgeEventItem) {
  liveRows.value = [row, ...liveRows.value].slice(0, LIVE_LIMIT);
}

function pushLive(row: EdgeEventItem) {
  if (paused.value) {
    if (pendingRows.length < LIVE_LIMIT) pendingRows.push(row);
    pendingCount.value = pendingRows.length;
    return;
  }
  appendLive(row);
}

function togglePause() {
  paused.value = !paused.value;
  if (!paused.value && pendingRows.length) {
    liveRows.value = [...pendingRows.reverse(), ...liveRows.value].slice(0, LIVE_LIMIT);
    pendingRows.length = 0;
    pendingCount.value = 0;
  }
}

function clearLive() {
  liveRows.value = [];
  pendingRows.length = 0;
  pendingCount.value = 0;
}

function connectWs() {
  const token = Auth.getAccessToken();
  if (!token) return;
  closedByUs = false;
  wsStatus.value = "connecting";
  try {
    ws = new WebSocket(buildEdgeEventWsUrl(token));
  } catch {
    wsStatus.value = "closed";
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    wsStatus.value = "open";
    retry = 0;
  };
  ws.onmessage = (event) => {
    let message: any;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message?.type === "event" && message.data) pushLive(message.data as EdgeEventItem);
  };
  ws.onclose = () => {
    wsStatus.value = "closed";
    if (!closedByUs) scheduleReconnect();
  };
  ws.onerror = () => {
    /* 交由 onclose 统一重连 */
  };
}

/** 指数退避重连（上限 30s） */
function scheduleReconnect() {
  if (reconnectTimer !== null) return;
  const delay = Math.min(1000 * 2 ** retry, 30000);
  retry += 1;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, delay);
}

function closeWs() {
  closedByUs = true;
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onopen = null;
    ws.onmessage = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.close();
    ws = null;
  }
  wsStatus.value = "closed";
}

async function handleRowClick(row: any) {
  drawer.detail = row as EdgeEventDetail;
  drawer.visible = true;
  if (row?.id == null) return;
  try {
    const res = await getEdgeEventDetail(row.id as number);
    if (res.data?.data) drawer.detail = res.data.data as EdgeEventDetail;
  } catch {
    /* 详情失败时保留列表摘要 */
  }
}

const detectionRows = computed<EdgeEventObject[]>(() => {
  const detail = drawer.detail;
  if (!detail) return [];
  const objects = detail.objects || [];
  return objects.length ? objects : detail.detections || [];
});

function leafTagType(leaf: EdgeEventMatchedLeaf): "success" | "danger" {
  return leaf.negated ? "danger" : "success";
}

function isHttpUrl(url?: string): boolean {
  return !!url && /^https?:\/\//i.test(url);
}

function fmtConfidence(value?: number): string {
  return value != null && typeof value === "number" ? value.toFixed(3) : "-";
}

function formatAttributes(attrs?: Record<string, unknown>): string {
  if (!attrs || typeof attrs !== "object") return "-";
  const parts = Object.entries(attrs).map(([key, value]) => {
    if (value === null || value === undefined) return `${key}=-`;
    if (typeof value === "object") return `${key}=${JSON.stringify(value)}`;
    return `${key}=${String(value)}`;
  });
  return parts.length ? parts.join("; ") : "-";
}

function formatTime(value?: string | number): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

const cameraNameMap = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {};
  for (const camera of cameraOptions.value) map[camera.id] = camera.name;
  return map;
});

const sceneNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const scene of sceneOptions.value) map[scene.code] = scene.name;
  return map;
});

function cameraLabel(cameraId?: number): string {
  if (cameraId === undefined || cameraId === null) return "-";
  return cameraNameMap.value[cameraId] || `#${cameraId}`;
}

function sceneLabel(code?: string): string {
  if (!code) return "-";
  return sceneNameMap.value[code] || code;
}

function summaryText(row: any): string {
  const labels = row.labels || [];
  const names = labels.length ? labels.join("、") : "目标";
  return `${names} × ${row.object_count ?? 0}`;
}

async function ensureCameraOptions() {
  if (cameraOptions.value.length) return;
  try {
    cameraOptions.value = await cachedOptions(
      "video:cameras:edge-event",
      async () => (await getCameraList({ page_size: 100 })).data?.data?.items || []
    );
    const item: any = (searchConfig.formItems || []).find((i: any) => i.prop === "camera_id");
    if (item) {
      item.options = cameraOptions.value.map((camera: any) => ({
        label: camera.name,
        value: camera.id,
      }));
    }
  } catch {
    /* 请求失败由全局拦截器提示 */
  }
}

async function ensureSceneOptions() {
  if (sceneOptions.value.length) return;
  try {
    sceneOptions.value = await cachedOptions("video:scenes:edge-event", async () => {
      const res = await getSceneCatalog();
      return (res.data?.data?.items ?? []) as SceneDefinition[];
    });
    const item: any = (searchConfig.formItems || []).find((i: any) => i.prop === "algorithm_type");
    if (item) {
      item.options = sceneOptions.value.map((scene) => ({ label: scene.name, value: scene.code }));
    }
  } catch {
    /* 请求失败由全局拦截器提示 */
  }
}

const liveBodyStyle = {
  display: "flex",
  flex: 1,
  flexDirection: "column" as const,
  minHeight: 0,
  overflow: "hidden",
  padding: "16px 20px",
};

watch(activeView, (view) => {
  if (view === "live") {
    connectWs();
  } else {
    closeWs();
    nextTick(() => contentRef.value?.fetchPageData(activeFilters.value, true));
  }
});

onMounted(() => {
  void ensureCameraOptions();
  void ensureSceneOptions();
  connectWs();
});

onBeforeUnmount(() => {
  closeWs();
});
</script>

<style scoped lang="scss">
.edge-event-switch {
  flex: 0 0 auto;
  margin-top: 16px;
}

.edge-event-switch__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.edge-event-switch__right {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.edge-event-switch__count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.event-detail__section {
  margin-top: 16px;
}

.event-detail__title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.event-detail__leaves {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.event-detail__leaf-path {
  margin-right: 4px;
  font-family: monospace;
  opacity: 0.85;
}

.event-detail__leaf-neg {
  margin-right: 4px;
  font-weight: 700;
}

.text-muted {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
