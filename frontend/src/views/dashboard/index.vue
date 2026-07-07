<template>
  <div class="db">
    <!-- ═══ Pulse Bar — signature element ═══ -->
    <div class="pulse-bar">
      <div class="pulse-item" v-for="p in pulses" :key="p.label">
        <span class="pulse-dot" :style="{ background: p.color }" />
        <span class="pulse-label">{{ p.label }}</span>
        <span class="pulse-value" :style="{ color: p.color }">{{ p.text }}</span>
        <span v-if="p.pct != null" class="pulse-track">
          <span class="pulse-fill" :style="{ width: p.pct + '%', background: p.color }" />
        </span>
      </div>
      <div class="pulse-greeting">
        <span class="pulse-user">{{ timefix }}{{ userStore.basicInfo.name }}</span>
        <span class="pulse-sub">{{ welcome }}</span>
      </div>
    </div>

    <!-- ═══ Metric Cards ═══ -->
    <div class="mc-grid">
      <div v-for="c in cards" :key="c.label" class="mc-card" @click="c.route && router.push(c.route)">
        <div class="mc-icon" :style="{ background: c.bg }">
          <el-icon :size="18" :color="c.color"><component :is="c.icon" /></el-icon>
        </div>
        <div class="mc-body">
          <span class="mc-val">{{ c.val }}</span>
          <span class="mc-lbl">{{ c.label }}</span>
        </div>
        <span class="mc-extra">{{ c.extra }}</span>
      </div>
    </div>

    <!-- ═══ Chart Row 1: 4 pies ═══ -->
    <div class="chart-row">
      <div class="chart-card">
        <div class="chart-hd"><span>标注任务类型</span><span class="chart-note">{{ stats.taskTypeTotal }} 个任务</span></div>
        <ECharts :options="taskTypePie" height="180" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>标注任务状态</span><span class="chart-note">{{ stats.taskTotal }} 个任务</span></div>
        <ECharts :options="taskStatusPie" height="180" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>训练任务状态</span><span class="chart-note">{{ stats.trainTotal }} 个任务</span></div>
        <ECharts :options="trainStatusPie" height="180" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>训练框架</span><span class="chart-note">{{ stats.trainTotal }} 个任务</span></div>
        <ECharts :options="trainFrameworkPie" height="180" />
      </div>
    </div>

    <!-- ═══ Chart Row 2: bars ═══ -->
    <div class="chart-row chart-row--wide">
      <div class="chart-card">
        <div class="chart-hd"><span>各数据集图片数</span><span class="chart-note">{{ stats.datasetCount }} 个数据集</span></div>
        <ECharts :options="datasetBar" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>各类型标注任务数</span><span class="chart-note">{{ stats.taskTypeTotal }} 个任务</span></div>
        <ECharts :options="taskTypeBar" height="200" />
      </div>
    </div>

    <!-- ═══ Bottom: 3-column footer ═══ -->
    <div class="ft-grid">
      <div class="ft-card">
        <div class="ft-hd"><el-icon size="13"><Edit /></el-icon> 最近标注任务</div>
        <div class="ft-list">
          <div v-for="t in recentAnno" :key="t.id" class="ft-row">
            <span class="ft-name">{{ t.name }}</span>
            <span class="ft-type">{{ typeLbl(t.task_type) }}</span>
            <el-tag :type="sTag(t.status)" size="small" effect="plain" class="ft-tag">{{ sLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentAnno.length" class="ft-empty">暂无数据</div>
        </div>
      </div>
      <div class="ft-card">
        <div class="ft-hd"><el-icon size="13"><Aim /></el-icon> 最近训练任务</div>
        <div class="ft-list">
          <div v-for="t in recentTrain" :key="t.id" class="ft-row">
            <span class="ft-name">{{ t.name }}</span>
            <el-tag :type="trainTag(t.status)" size="small" effect="plain" class="ft-tag">{{ trainLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentTrain.length" class="ft-empty">暂无数据</div>
        </div>
      </div>
      <div class="ft-card">
        <div class="ft-hd"><el-icon size="13"><WarningFilled /></el-icon> 最近告警</div>
        <div class="ft-list">
          <div v-for="a in recentAlarm" :key="a.id" class="ft-row">
            <span class="ft-name">{{ a.alarm_type || '告警' }}</span>
            <span class="ft-time">{{ fmt(a.created_time) }}</span>
          </div>
          <div v-if="!recentAlarm.length" class="ft-empty">暂无告警</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { UserFilled, Folder, Edit, Aim, Camera, WarningFilled } from "@element-plus/icons-vue";
import { useUserStoreHook } from "@/store";
import ECharts from "@/components/ECharts/index.vue";
import { AnnotationAPI } from "@/api/module_annotation";
import { TrainAPI } from "@/api/module_train";
import { getCameraList } from "@/api/module_video/camera";
import { getAlarmRecordList } from "@/api/module_video/alarm";
import UserAPI from "@/api/module_system/user";
import OnlineAPI from "@/api/module_monitor/online";
import ServerAPI from "@/api/module_monitor/server";

const router = useRouter();
const userStore = useUserStoreHook();
const now = new Date(); const h = now.getHours();
const timefix = h < 6 ? "夜深了，" : h < 9 ? "早上好，" : h < 12 ? "上午好，" : h < 14 ? "中午好，" : h < 18 ? "下午好，" : "晚上好，";
const welcome = ["注意休息","新的一天","保持高效","午休时间","继续加油","今天辛苦了"][Math.min(5, Math.floor(h / 4))];

const serverInfo = ref<any>({});

const stats = reactive({
  onlineUsers: 0, totalUsers: 0,
  datasetCount: 0, taskCount: 0, annotatedCount: 0, taskTotal: 0, taskTypeTotal: 0,
  taskPending: 0, taskInProgress: 0, taskCompleted: 0,
  trainTotal: 0, trainPending: 0, trainRunning: 0, trainSuccess: 0, trainFailed: 0,
  trainUltralytics: 0, trainPaddleX: 0,
  cameraTotal: 0, cameraOnline: 0, alarmCount: 0,
});
const taskTypeCount = reactive<Record<string, number>>({});
const datasetImageCounts = ref<{ name: string; count: number }[]>([]);
const recentAnno = ref<any[]>([]);
const recentTrain = ref<any[]>([]);
const recentAlarm = ref<any[]>([]);

const PULSE_COLORS = ["#00b894", "#6c5ce7", "#fdcb6e", "#74b9ff", "#ff7675", "#a29bfe"];

const pulses = computed(() => [
  { label: "CPU", text: (serverInfo.value?.cpu?.used ?? "—") + "%", pct: serverInfo.value?.cpu?.used ?? null, color: PULSE_COLORS[0] },
  { label: "内存", text: (serverInfo.value?.mem?.usage ?? "—") + "%", pct: serverInfo.value?.mem?.usage ?? null, color: PULSE_COLORS[1] },
  { label: "磁盘", text: serverInfo.value?.disks?.[0] ? (serverInfo.value.disks[0].usage ?? serverInfo.value.disks[0].usage_percent ?? "—") + "%" : "—", pct: serverInfo.value?.disks?.[0]?.usage ?? serverInfo.value?.disks?.[0]?.usage_percent ?? null, color: PULSE_COLORS[2] },
  { label: "用户", text: String(stats.onlineUsers), pct: stats.totalUsers ? Math.round(stats.onlineUsers / stats.totalUsers * 100) : 0, color: PULSE_COLORS[3] },
  { label: "任务", text: String(stats.trainRunning), pct: stats.trainTotal ? Math.round(stats.trainRunning / stats.trainTotal * 100) : 0, color: PULSE_COLORS[4] },
  { label: "告警", text: String(stats.alarmCount), pct: null, color: PULSE_COLORS[5] },
]);

const cards = computed(() => [
  { label: "数据集", val: stats.datasetCount, icon: Folder, color: "#0984e3", bg: "#e8f4fd", extra: `${stats.annotatedCount} 张已标注`, route: "/annotation/dataset" },
  { label: "标注任务", val: stats.taskTotal, icon: Edit, color: "#00b894", bg: "#e6faf5", extra: `${stats.taskCompleted} 已完成`, route: "/annotation/task" },
  { label: "训练任务", val: stats.trainTotal, icon: Aim, color: "#6c5ce7", bg: "#efeaff", extra: `${stats.trainRunning} 训练中`, route: "/train/task" },
  { label: "摄像头", val: stats.cameraTotal, icon: Camera, color: "#fdcb6e", bg: "#fef9e7", extra: `${stats.cameraOnline} 在线`, route: "/video/camera" },
  { label: "告警记录", val: stats.alarmCount, icon: WarningFilled, color: "#ff7675", bg: "#ffeeed", extra: "最近 7 天", route: "/video/alarm" },
  { label: "在线用户", val: stats.onlineUsers, icon: UserFilled, color: "#74b9ff", bg: "#eef6ff", extra: `共 ${stats.totalUsers} 用户`, route: "/system/user" },
]);

function typeLbl(t: string) { return ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" } as any)[t] || t; }
function sTag(s: string) { return ({ pending: "info", in_progress: "primary", completed: "success" } as any)[s] || "info"; }
function sLbl(s: string) { return ({ pending: "待开始", in_progress: "进行中", completed: "已完成" } as any)[s] || s; }
function trainTag(s: string) { return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info"; }
function trainLbl(s: string) { return ({ pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s; }
function fmt(t?: string) { if (!t) return ""; const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }

const taskTypePie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: Object.entries(taskTypeCount).map(([k, v]) => ({
      name: typeLbl(k), value: v,
      itemStyle: { color: ({ detection: "#0984e3", rotated_detection: "#00b894", segmentation: "#fdcb6e", keypoint: "#ff7675", ocr: "#6c5ce7", classification: "#74b9ff" } as any)[k] || "#95a5a6" },
    })).concat(stats.taskTypeTotal === 0 ? [{ name: "暂无", value: 1, itemStyle: { color: "#dfe6e9" } }] : []),
  }],
}));

const taskStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.taskPending || 1, name: "待开始", itemStyle: { color: "#b2bec3" } },
      { value: stats.taskInProgress || 1, name: "进行中", itemStyle: { color: "#0984e3" } },
      { value: stats.taskCompleted || 1, name: "已完成", itemStyle: { color: "#00b894" } },
    ],
  }],
}));

const trainStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.trainPending || 1, name: "待开始", itemStyle: { color: "#b2bec3" } },
      { value: stats.trainRunning || 1, name: "训练中", itemStyle: { color: "#0984e3" } },
      { value: stats.trainSuccess || 1, name: "已完成", itemStyle: { color: "#00b894" } },
      { value: stats.trainFailed || 1, name: "失败", itemStyle: { color: "#ff7675" } },
    ],
  }],
}));

const trainFrameworkPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.trainUltralytics || 1, name: "Ultralytics", itemStyle: { color: "#0984e3" } },
      { value: stats.trainPaddleX || 1, name: "PaddleX", itemStyle: { color: "#00b894" } },
    ],
  }],
}));

const datasetBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "8%", right: "4%", bottom: "12%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: datasetImageCounts.value.map(d => d.name), axisLabel: { rotate: 30, fontSize: 10, interval: 0 } },
  yAxis: { type: "value" as const, name: "图片数" },
  series: [{ type: "bar" as const, barWidth: "50%", itemStyle: { color: "#0984e3", borderRadius: [4, 4, 0, 0] }, data: datasetImageCounts.value.map(d => d.count) }],
}));

const taskTypeBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "8%", right: "4%", bottom: "12%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: Object.keys(taskTypeCount).length ? Object.keys(taskTypeCount).map(k => typeLbl(k)) : ["暂无"], axisLabel: { rotate: 20, fontSize: 10 } },
  yAxis: { type: "value" as const, name: "任务数" },
  series: [{ type: "bar" as const, barWidth: "50%", itemStyle: { color: "#00b894", borderRadius: [4, 4, 0, 0] }, data: Object.keys(taskTypeCount).length ? Object.values(taskTypeCount) : [0] }],
}));

onMounted(async () => {
  // Wait for ECharts to initialize first
  await new Promise(r => setTimeout(r, 300));
  loadAllData();
});

async function loadAllData() {
  const [serverR, annoR, trainR, camR, alarmR, userR, onlineR] = await Promise.allSettled([
    ServerAPI.getServer(),
    AnnotationAPI.getOverview(),
    TrainAPI.getTaskList(),
    getCameraList({ page_no: 1, page_size: 100 }),
    getAlarmRecordList({ page_no: 1, page_size: 5 }),
    UserAPI.listUser({ page_no: 1, page_size: 1 }),
    OnlineAPI.listOnline({ page_no: 1, page_size: 1 }),
  ]);

  if (serverR.status === "fulfilled") serverInfo.value = serverR.value.data?.data || {};

  if (annoR.status === "fulfilled") {
    const d = annoR.value.data?.data;
    if (d) { stats.datasetCount = d.dataset_count || 0; stats.taskCount = d.task_count || 0; stats.annotatedCount = d.annotated_image_count || 0; }
  }

  if (trainR.status === "fulfilled") {
    const tasks = trainR.value.data?.data || [];
    stats.trainTotal = tasks.length;
    for (const t of tasks) {
      if (t.status === "pending") stats.trainPending++;
      else if (t.status === "running") stats.trainRunning++;
      else if (t.status === "success") stats.trainSuccess++;
      else if (t.status === "failed") stats.trainFailed++;
      if (t.framework === "ultralytics") stats.trainUltralytics++;
      else if (t.framework === "paddlex") stats.trainPaddleX++;
    }
    recentTrain.value = tasks.slice(0, 5).reverse();
  }

  if (camR.status === "fulfilled") {
    const items = camR.value.data?.data?.items || [];
    stats.cameraTotal = camR.value.data?.data?.total || items.length;
    stats.cameraOnline = items.filter((c: any) => c.reachable === true).length;
  }

  if (alarmR.status === "fulfilled") {
    const items = alarmR.value.data?.data?.items || [];
    stats.alarmCount = alarmR.value.data?.data?.total || 0;
    recentAlarm.value = items.slice(0, 5);
  }

  if (userR.status === "fulfilled") stats.totalUsers = userR.value.data?.data?.total || 0;
  if (onlineR.status === "fulfilled") stats.onlineUsers = onlineR.value.data?.data?.total || 0;

  try {
    const r = await AnnotationAPI.getTaskList({ page_no: 1, page_size: 100 });
    const tasks = r.data?.data?.items || [];
    stats.taskTotal = tasks.length;
    for (const t of tasks) {
      if (t.status === "pending") stats.taskPending++;
      else if (t.status === "in_progress") stats.taskInProgress++;
      else if (t.status === "completed") stats.taskCompleted++;
      const tt = t.task_type || "detection";
      taskTypeCount[tt] = (taskTypeCount[tt] || 0) + 1;
    }
    stats.taskTypeTotal = Object.keys(taskTypeCount).length;
    recentAnno.value = tasks.slice(0, 5).reverse();
  } catch {}

  try {
    const r = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
    const items = r.data?.data?.items || [];
    datasetImageCounts.value = items.map((d: any) => ({ name: d.name || `#${d.id}`, count: d.image_count || d.annotated_count || 0 }));
  } catch {}
  // Force ECharts to re-render after all data loads
  await nextTick();
  document.querySelectorAll(".chart-card canvas").forEach((c: any) => c?.parentElement?.__vue__?.resize?.());
  window.dispatchEvent(new Event("resize"));
}
</script>

<style scoped>
.db { padding: 12px 20px; background: #f1f5f9; min-height: 100vh; }

/* ── Pulse Bar ── */
.pulse-bar {
  display: flex; align-items: center; gap: 20px;
  background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0; border-radius: 14px;
  padding: 16px 24px; margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.pulse-item { display: flex; align-items: center; gap: 6px; min-width: 0; }
.pulse-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 0 2px rgba(0,0,0,.04); }
.pulse-label { font-size: 10px; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; white-space: nowrap; }
.pulse-value { font-size: 15px; font-weight: 800; font-variant-numeric: tabular-nums; min-width: 36px; }
.pulse-track { width: 52px; height: 4px; background: #e2e8f0; border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.pulse-fill { height: 100%; border-radius: 2px; transition: width .8s cubic-bezier(.4,0,.2,1); }
.pulse-greeting { margin-left: auto; text-align: right; flex-shrink: 0; border-left: 1px solid #e2e8f0; padding-left: 20px; }
.pulse-user { font-size: 13px; font-weight: 700; color: #1e293b; display: block; letter-spacing: -.01em; }
.pulse-sub { font-size: 11px; color: #94a3b8; margin-top: 1px; }

/* ── Metric Cards ── */
.mc-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }
.mc-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 16px 14px; display: flex; align-items: center; gap: 12px;
  cursor: pointer; transition: all .2s ease; position: relative; overflow: hidden;
}
.mc-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: transparent; transition: background .2s ease;
}
.mc-card:hover { box-shadow: 0 6px 16px rgba(0,0,0,.07); transform: translateY(-2px); border-color: #cbd5e1; }
.mc-card:hover::before { background: var(--el-color-primary-light-3); }
.mc-icon { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.mc-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.mc-val { font-size: 20px; font-weight: 800; line-height: 1.15; color: #0f172a; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.mc-lbl { font-size: 10px; color: #94a3b8; margin-top: 2px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }
.mc-extra { font-size: 10px; color: #cbd5e1; white-space: nowrap; }

/* ── Chart Row ── */
.chart-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.chart-row--wide { grid-template-columns: repeat(2, 1fr); }
.chart-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;
  transition: all .2s ease;
}
.chart-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.05); }
.chart-hd { font-size: 12px; font-weight: 700; color: #1e293b; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; }
.chart-note { font-size: 10px; font-weight: 400; color: #94a3b8; }

/* ── Footer ── */
.ft-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.ft-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; }
.ft-hd { font-size: 12px; font-weight: 700; color: #1e293b; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.ft-list { max-height: 220px; overflow-y: auto; }
.ft-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f1f5f9; }
.ft-row:last-child { border-bottom: none; }
.ft-name { font-size: 12px; color: #1e293b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; font-weight: 500; }
.ft-type { font-size: 10px; color: #94a3b8; white-space: nowrap; }
.ft-tag { flex-shrink: 0; }
.ft-time { font-size: 11px; color: #94a3b8; white-space: nowrap; }
.ft-empty { text-align: center; padding: 20px 0; color: #94a3b8; font-size: 12px; }
</style>
