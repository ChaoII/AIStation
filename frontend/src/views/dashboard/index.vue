<template>
  <div class="dashboard-page">
    <!-- ═══ 指标卡片 ═══ -->
    <el-card shadow="hover" class="dash-metrics-card">
      <el-row :gutter="8">
        <el-col v-for="c in cards" :key="c.label" :xs="24" :sm="12" :md="8" :lg="4">
          <div
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
        </el-col>
      </el-row>
    </el-card>

    <!-- ═══ 图表区（始终保持渲染，加载中仅显示轻量占位） ═══ -->
    <el-row :gutter="12">
      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-chart-header">
              <span class="dash-chart-title">{{ t("dashboard.chartAnnoStatus") }}</span>
              <span class="dash-chart-note">{{ t("dashboard.noteTaskCount", { n: stats.taskTotal }) }}</span>
            </div>
          </template>
          <div class="dash-chart-wrapper">
            <div v-if="!dataLoaded" class="dash-chart-placeholder" />
            <ECharts v-if="dataLoaded" :options="taskStatusPie" height="260" />
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-chart-header">
              <span class="dash-chart-title">{{ t("dashboard.chartTrainStatus") }}</span>
              <span class="dash-chart-note">{{ t("dashboard.noteTaskCount", { n: stats.trainTotal }) }}</span>
            </div>
          </template>
          <div class="dash-chart-wrapper">
            <div v-if="!dataLoaded" class="dash-chart-placeholder" />
            <ECharts v-if="dataLoaded" :options="trainStatusPie" height="260" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-chart-header">
              <span class="dash-chart-title">{{ t("dashboard.chartDatasetImages") }}</span>
              <span class="dash-chart-note">{{ t("dashboard.noteDatasetCount", { n: stats.datasetCount }) }}</span>
            </div>
          </template>
          <div class="dash-chart-wrapper">
            <div v-if="!dataLoaded" class="dash-chart-placeholder" />
            <ECharts v-if="dataLoaded" :options="datasetBar" height="220" />
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="12" :lg="12">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-chart-header">
              <span class="dash-chart-title">{{ t("dashboard.chartTaskType") }}</span>
              <span class="dash-chart-note">{{ t("dashboard.noteTypeCount", { n: stats.taskTypeTotal }) }}</span>
            </div>
          </template>
          <div class="dash-chart-wrapper">
            <div v-if="!dataLoaded" class="dash-chart-placeholder" />
            <ECharts v-if="dataLoaded" :options="taskTypeBar" height="220" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══ 底部最近动态 ═══ -->
    <el-row :gutter="10">
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-footer-head">
              <el-icon size="16"><Edit /></el-icon>
              {{ t("dashboard.recentAnno") }}
            </div>
          </template>
          <div class="dash-list">
            <div v-for="t in recentAnno" :key="t.id" class="dash-list-item">
              <span class="dash-list-name">{{ t.name }}</span>
              <el-tag :type="sTag(t.status)" size="small" effect="plain" class="dash-list-badge">
                {{ sLbl(t.status) }}
              </el-tag>
            </div>
            <div v-if="!recentAnno.length" class="dash-empty">{{ t("dashboard.empty") }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-footer-head">
              <el-icon size="16"><Aim /></el-icon>
              {{ t("dashboard.recentTrain") }}
            </div>
          </template>
          <div class="dash-list">
            <div v-for="t in recentTrain" :key="t.id" class="dash-list-item">
              <span class="dash-list-name">{{ t.name }}</span>
              <el-tag
                :type="trainTag(t.status)"
                size="small"
                effect="plain"
                class="dash-list-badge"
              >
                {{ trainLbl(t.status) }}
              </el-tag>
            </div>
            <div v-if="!recentTrain.length" class="dash-empty">{{ t("dashboard.empty") }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="8">
        <el-card shadow="hover">
          <template #header>
            <div class="dash-footer-head">
              <el-icon size="16"><WarningFilled /></el-icon>
              {{ t("dashboard.recentAlarm") }}
            </div>
          </template>
          <div class="dash-list">
            <div v-for="a in recentAlarm" :key="a.id" class="dash-list-item">
              <span class="dash-list-name">{{ a.alarm_type || t("dashboard.alarmDefault") }}</span>
              <span class="dash-list-meta">{{ fmt(a.created_time) }}</span>
            </div>
            <div v-if="!recentAlarm.length" class="dash-empty">{{ t("dashboard.emptyAlarm") }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { UserFilled, Folder, Edit, Aim, Camera, WarningFilled } from "@element-plus/icons-vue";
import ECharts from "@/components/ECharts/index.vue";
import { AnnotationAPI } from "@/api/module_annotation";
import { TrainAPI } from "@/api/module_train";
import { getCameraList } from "@/api/module_video/camera";
import { getAlarmRecordList } from "@/api/module_video/alarm";
import UserAPI from "@/api/module_system/user";
import OnlineAPI from "@/api/module_monitor/online";
import ServerAPI from "@/api/module_monitor/server";

const router = useRouter();
const { t } = useI18n();
const serverInfo = ref<any>({});
const dataLoaded = ref(false);

const stats = reactive({
  onlineUsers: 0,
  totalUsers: 0,
  datasetCount: 0,
  taskCount: 0,
  annotatedCount: 0,
  taskTotal: 0,
  taskTypeTotal: 0,
  taskPending: 0,
  taskInProgress: 0,
  taskCompleted: 0,
  trainTotal: 0,
  trainPending: 0,
  trainRunning: 0,
  trainSuccess: 0,
  trainFailed: 0,
  trainUltralytics: 0,
  trainPaddleX: 0,
  cameraTotal: 0,
  cameraOnline: 0,
  alarmCount: 0,
});
const taskTypeCount = reactive<Record<string, number>>({});
const datasetImageCounts = ref<{ name: string; count: number }[]>([]);
const recentAnno = ref<any[]>([]);
const recentTrain = ref<any[]>([]);
const recentAlarm = ref<any[]>([]);

const cards = computed(() => [
  {
    label: t("dashboard.cardDataset"),
    val: stats.datasetCount,
    icon: Folder,
    color: "#0984e3",
    bg: "#e8f4fd",
    extra: t("dashboard.extraAnnotated", { n: stats.annotatedCount }),
    route: "/annotation/dataset",
  },
  {
    label: t("dashboard.cardAnnoTask"),
    val: stats.taskTotal,
    icon: Edit,
    color: "#00b894",
    bg: "#e6faf5",
    extra: t("dashboard.extraCompleted", { n: stats.taskCompleted }),
    route: "/annotation/task",
  },
  {
    label: t("dashboard.cardTrainTask"),
    val: stats.trainTotal,
    icon: Aim,
    color: "#6c5ce7",
    bg: "#efeaff",
    extra: t("dashboard.extraTraining", { n: stats.trainRunning }),
    route: "/train/task",
  },
  {
    label: t("dashboard.cardCamera"),
    val: stats.cameraTotal,
    icon: Camera,
    color: "#fdcb6e",
    bg: "#fef9e7",
    extra: t("dashboard.extraOnline", { n: stats.cameraOnline }),
    route: "/video/camera",
  },
  {
    label: t("dashboard.cardAlarm"),
    val: stats.alarmCount,
    icon: WarningFilled,
    color: "#ff7675",
    bg: "#ffeeed",
    extra: t("dashboard.extraLast7Days"),
    route: "/video/alarm",
  },
  {
    label: t("dashboard.cardOnline"),
    val: stats.onlineUsers,
    icon: UserFilled,
    color: "#74b9ff",
    bg: "#eef6ff",
    extra: t("dashboard.extraTotalUsers", { n: stats.totalUsers }),
    route: "/system/user",
  },
]);

function typeLbl(type: string) {
  return (
    (
      {
        detection: t("dashboard.typeDetection"),
        rotated_detection: t("dashboard.typeRotated"),
        segmentation: t("dashboard.typeSegmentation"),
        keypoint: t("dashboard.typeKeypoint"),
        ocr: t("dashboard.typeOCR"),
        classification: t("dashboard.typeClassification"),
      } as any
    )[type] || type
  );
}
function sTag(s: string) {
  return ({ pending: "info", in_progress: "primary", completed: "success" } as any)[s] || "info";
}
function sLbl(s: string) {
  return (
    ({
      pending: t("dashboard.statusPending"),
      in_progress: t("dashboard.statusInProgress"),
      completed: t("dashboard.statusCompleted"),
    } as any)[s] || s
  );
}
function trainTag(s: string) {
  return (
    (
      {
        pending: "info",
        running: "warning",
        success: "success",
        failed: "danger",
        cancelled: "info",
      } as any
    )[s] || "info"
  );
}
function trainLbl(s: string) {
  return (
    (
      {
        pending: t("dashboard.statusPending"),
        running: t("dashboard.statusTraining"),
        success: t("dashboard.statusCompleted"),
        failed: t("dashboard.statusFailed"),
        cancelled: t("dashboard.statusCancelled"),
      } as any
    )[s] || s
  );
}
function fmt(t?: string) {
  if (!t) return "";
  const d = new Date(t);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const taskStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [
    {
      type: "pie" as const,
      radius: ["40%", "65%"],
      center: ["50%", "50%"],
      label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
      data: [
        { value: stats.taskPending || 1, name: t("dashboard.statusPending"), itemStyle: { color: "#cbd5e1" } },
        { value: stats.taskInProgress || 1, name: t("dashboard.statusInProgress"), itemStyle: { color: "#0984e3" } },
        { value: stats.taskCompleted || 1, name: t("dashboard.statusCompleted"), itemStyle: { color: "#00b894" } },
      ],
    },
  ],
}));

const trainStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [
    {
      type: "pie" as const,
      radius: ["40%", "65%"],
      center: ["50%", "50%"],
      label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
      data: [
        { value: stats.trainPending || 1, name: t("dashboard.statusPending"), itemStyle: { color: "#cbd5e1" } },
        { value: stats.trainRunning || 1, name: t("dashboard.statusTraining"), itemStyle: { color: "#0984e3" } },
        { value: stats.trainSuccess || 1, name: t("dashboard.statusCompleted"), itemStyle: { color: "#00b894" } },
        { value: stats.trainFailed || 1, name: t("dashboard.statusFailed"), itemStyle: { color: "#ff7675" } },
      ],
    },
  ],
}));

const datasetBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "6%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: {
    type: "category" as const,
    data: datasetImageCounts.value.map((d) => d.name),
    axisLabel: { rotate: 25, fontSize: 10, interval: 0 },
  },
  yAxis: { type: "value" as const, name: t("dashboard.axisImageCount") },
  series: [
    {
      type: "bar" as const,
      barWidth: "45%",
      itemStyle: { color: "#0984e3", borderRadius: [4, 4, 0, 0] },
      data: datasetImageCounts.value.map((d) => d.count),
    },
  ],
}));

const taskTypeBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "6%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: {
    type: "category" as const,
    data: Object.keys(taskTypeCount).length
      ? Object.keys(taskTypeCount).map((k) => typeLbl(k))
      : [t("dashboard.noData")],
    axisLabel: { rotate: 20, fontSize: 10 },
  },
  yAxis: { type: "value" as const, name: t("dashboard.axisTaskCount") },
  series: [
    {
      type: "bar" as const,
      barWidth: "45%",
      itemStyle: { color: "#00b894", borderRadius: [4, 4, 0, 0] },
      data: Object.keys(taskTypeCount).length ? Object.values(taskTypeCount) : [0],
    },
  ],
}));

onMounted(async () => {
  await new Promise((r) => setTimeout(r, 300));
  loadAllData();
});

async function loadAllData() {
  const [serverR, annoR, trainR, camR, alarmR, userR, onlineR] = await Promise.allSettled([
    ServerAPI.getServer(),
    AnnotationAPI.getOverview(),
    TrainAPI.getTaskList({ page_no: 1, page_size: 50 }),
    getCameraList({ page_no: 1, page_size: 50 }),
    getAlarmRecordList({ page_no: 1, page_size: 5 }),
    UserAPI.listUser({ page_no: 1, page_size: 1 }),
    OnlineAPI.listOnline({ page_no: 1, page_size: 1 }),
  ]);

  if (serverR.status === "fulfilled") serverInfo.value = serverR.value.data?.data || {};

  if (annoR.status === "fulfilled") {
    const d = annoR.value.data?.data;
    if (d) {
      stats.datasetCount = d.dataset_count || 0;
      stats.taskCount = d.task_count || 0;
      stats.annotatedCount = d.annotated_image_count || 0;
    }
  }

  if (trainR.status === "fulfilled") {
    const tasksData = trainR.value.data?.data || {};
    const tasks = tasksData.items || [];
    stats.trainTotal = tasksData.total ?? tasks.length;
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
    // 用后端聚合接口一次取全，避免拉 100 行列表（首页图表用）
    const ov = (await AnnotationAPI.getOverview()).data?.data || {};
    stats.taskTotal = ov.task_count || 0;
    const byStatus = ov.tasks_by_status || {};
    stats.taskPending = byStatus.pending || 0;
    stats.taskInProgress = byStatus.in_progress || byStatus.inprogress || 0;
    stats.taskCompleted = byStatus.completed || 0;
    stats.taskTypeTotal = Object.keys(ov.tasks_by_type || {}).length;
    // 同步任务类型分布（供类型图表）
    Object.keys(taskTypeCount).forEach((k) => delete taskTypeCount[k]);
    Object.entries(ov.tasks_by_type || {}).forEach(([k, v]) => {
      taskTypeCount[k] = Number(v) || 0;
    });
    datasetImageCounts.value = (ov.top_datasets || []).map((d: any) => ({
      name: d.name || `#${d.id}`,
      count: d.image_count || 0,
    }));
  } catch {
    // 忽略错误
  }

  try {
    const r = await AnnotationAPI.getTaskList({ page_no: 1, page_size: 5 });
    recentAnno.value = (r.data?.data?.items || []).slice().reverse();
  } catch {
    // 忽略错误
  }

  await nextTick();
  dataLoaded.value = true;
  await nextTick();
  window.dispatchEvent(new Event("resize"));
}
</script>
