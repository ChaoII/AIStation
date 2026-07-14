<template>
  <div class="dashboard-page">
    <!-- ═══ 指标卡片 ═══ -->
    <el-card shadow="hover" class="dash-metrics-card">
      <div class="dash-metrics">
        <div
          v-for="c in cards"
          :key="c.label"
          class="dash-metric-card"
          :style="{
            '--dash-icon-bg': c.bg,
            '--dash-icon-color': c.color,
          }"
          @click="c.route && router.push(c.route)"
        >
          <div class="dash-metric-icon">
            <el-icon :size="20"><component :is="c.icon" /></el-icon>
          </div>
          <div class="dash-metric-body">
            <span class="dash-metric-value">{{ c.val }}</span>
            <span class="dash-metric-label">{{ c.label }}</span>
            <span class="dash-metric-extra">{{ c.extra }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ═══ 图表区（始终渲染，数据加载中显示骨架屏） ═══ -->
    <div class="dash-charts">
      <el-card shadow="hover" v-loading="!dataLoaded" element-loading-text="加载中...">
        <template #header>
          <div class="dash-chart-header">
            <span class="dash-chart-title">标注任务状态</span>
            <span class="dash-chart-note">{{ stats.taskTotal }} 个任务</span>
          </div>
        </template>
        <ECharts :options="taskStatusPie" height="280" />
      </el-card>
      <el-card shadow="hover" v-loading="!dataLoaded" element-loading-text="加载中...">
        <template #header>
          <div class="dash-chart-header">
            <span class="dash-chart-title">训练任务状态</span>
            <span class="dash-chart-note">{{ stats.trainTotal }} 个任务</span>
          </div>
        </template>
        <ECharts :options="trainStatusPie" height="280" />
      </el-card>
    </div>

    <div class="dash-charts">
      <el-card shadow="hover" v-loading="!dataLoaded" element-loading-text="加载中...">
        <template #header>
          <div class="dash-chart-header">
            <span class="dash-chart-title">各数据集图片数</span>
            <span class="dash-chart-note">{{ stats.datasetCount }} 个数据集</span>
          </div>
        </template>
        <ECharts :options="datasetBar" height="240" />
      </el-card>
      <el-card shadow="hover" v-loading="!dataLoaded" element-loading-text="加载中...">
        <template #header>
          <div class="dash-chart-header">
            <span class="dash-chart-title">标注任务类型分布</span>
            <span class="dash-chart-note">{{ stats.taskTypeTotal }} 种类型</span>
          </div>
        </template>
        <ECharts :options="taskTypeBar" height="240" />
      </el-card>
    </div>

    <!-- ═══ 底部最近动态 ═══ -->
    <div class="dash-footer">
      <el-card shadow="hover">
        <template #header>
          <div class="dash-footer-head">
            <el-icon size="16"><Edit /></el-icon> 最近标注任务
          </div>
        </template>
        <div class="dash-list">
          <div v-for="t in recentAnno" :key="t.id" class="dash-list-item">
            <span class="dash-list-name">{{ t.name }}</span>
            <el-tag :type="sTag(t.status)" size="small" effect="plain" class="dash-list-badge">
              {{ sLbl(t.status) }}
            </el-tag>
          </div>
          <div v-if="!recentAnno.length" class="dash-empty">暂无数据</div>
        </div>
      </el-card>
      <el-card shadow="hover">
        <template #header>
          <div class="dash-footer-head">
            <el-icon size="16"><Aim /></el-icon> 最近训练任务
          </div>
        </template>
        <div class="dash-list">
          <div v-for="t in recentTrain" :key="t.id" class="dash-list-item">
            <span class="dash-list-name">{{ t.name }}</span>
            <el-tag :type="trainTag(t.status)" size="small" effect="plain" class="dash-list-badge">
              {{ trainLbl(t.status) }}
            </el-tag>
          </div>
          <div v-if="!recentTrain.length" class="dash-empty">暂无数据</div>
        </div>
      </el-card>
      <el-card shadow="hover">
        <template #header>
          <div class="dash-footer-head">
            <el-icon size="16"><WarningFilled /></el-icon> 最近告警
          </div>
        </template>
        <div class="dash-list">
          <div v-for="a in recentAlarm" :key="a.id" class="dash-list-item">
            <span class="dash-list-name">{{ a.alarm_type || '告警' }}</span>
            <span class="dash-list-meta">{{ fmt(a.created_time) }}</span>
          </div>
          <div v-if="!recentAlarm.length" class="dash-empty">暂无告警</div>
        </div>
      </el-card>
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
const now = new Date();
const h = now.getHours();
const timefix = h < 6 ? "夜深了，" : h < 9 ? "早上好，" : h < 12 ? "上午好，" : h < 14 ? "中午好，" : h < 18 ? "下午好，" : "晚上好，";
const welcome = ["注意休息", "新的一天", "保持高效", "午休时间", "继续加油", "今天辛苦了"][Math.min(5, Math.floor(h / 4))];

const serverInfo = ref<any>({});
const dataLoaded = ref(false);

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

const taskStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["40%", "65%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.taskPending || 1, name: "待开始", itemStyle: { color: "#cbd5e1" } },
      { value: stats.taskInProgress || 1, name: "进行中", itemStyle: { color: "#0984e3" } },
      { value: stats.taskCompleted || 1, name: "已完成", itemStyle: { color: "#00b894" } },
    ],
  }],
}));

const trainStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["40%", "65%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.trainPending || 1, name: "待开始", itemStyle: { color: "#cbd5e1" } },
      { value: stats.trainRunning || 1, name: "训练中", itemStyle: { color: "#0984e3" } },
      { value: stats.trainSuccess || 1, name: "已完成", itemStyle: { color: "#00b894" } },
      { value: stats.trainFailed || 1, name: "失败", itemStyle: { color: "#ff7675" } },
    ],
  }],
}));

const datasetBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "6%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: datasetImageCounts.value.map(d => d.name), axisLabel: { rotate: 25, fontSize: 10, interval: 0 } },
  yAxis: { type: "value" as const, name: "图片数" },
  series: [{ type: "bar" as const, barWidth: "45%", itemStyle: { color: "#0984e3", borderRadius: [4, 4, 0, 0] }, data: datasetImageCounts.value.map(d => d.count) }],
}));

const taskTypeBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "6%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: Object.keys(taskTypeCount).length ? Object.keys(taskTypeCount).map(k => typeLbl(k)) : ["暂无"], axisLabel: { rotate: 20, fontSize: 10 } },
  yAxis: { type: "value" as const, name: "任务数" },
  series: [{ type: "bar" as const, barWidth: "45%", itemStyle: { color: "#00b894", borderRadius: [4, 4, 0, 0] }, data: Object.keys(taskTypeCount).length ? Object.values(taskTypeCount) : [0] }],
}));

onMounted(async () => {
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

  await nextTick();
  dataLoaded.value = true;
  await nextTick();
  window.dispatchEvent(new Event("resize"));
}
</script>
