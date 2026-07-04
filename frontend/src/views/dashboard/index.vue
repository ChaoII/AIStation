<template>
  <div class="db">
    <div class="db-banner">
      <div class="banner-left">
        <div class="avatar"><img v-if="userStore.basicInfo.avatar" :src="userStore.basicInfo.avatar + '?imageView2/1/w/80/h/80'" /><el-icon v-else :size="28"><UserFilled /></el-icon></div>
        <div>
          <div class="banner-greeting">{{ timefix }}{{ userStore.basicInfo.name }}，{{ welcome }}</div>
          <div class="banner-sub">{{ subText }}</div>
        </div>
      </div>
      <div class="banner-chips">
        <div class="chip"><span class="chip-dot" style="background:#67c23a" />{{ stats.onlineUsers }} 在线</div>
        <div class="chip"><span class="chip-dot" style="background:#409eff" />{{ stats.totalUsers }} 用户</div>
        <div class="chip"><span class="chip-dot" style="background:#e6a23c" />{{ stats.cameraOnline }}/{{ stats.cameraTotal }} 摄像头</div>
        <div class="chip"><span class="chip-dot" style="background:#f56c6c" />{{ stats.alarmCount }} 告警</div>
      </div>
    </div>

    <!-- 指标卡片 -->
    <div class="db-cards">
      <div v-for="c in cards" :key="c.label" class="db-card" @click="c.route && router.push(c.route)">
        <div class="card-icon" :style="{ background: c.bg }"><el-icon :size="20" :color="c.color"><component :is="c.icon" /></el-icon></div>
        <div class="card-body"><div class="card-val">{{ c.val }}</div><div class="card-lbl">{{ c.label }}</div></div>
        <div class="card-extra">{{ c.extra }}</div>
      </div>
    </div>

    <!-- 第一行图表：4个环形图 -->
    <div class="db-charts">
      <div class="chart-card">
        <div class="chart-hd"><span>标注任务类型</span><span class="chart-note">{{ stats.taskTypeTotal }} 个任务</span></div>
        <ECharts :options="taskTypePie" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>标注任务状态</span><span class="chart-note">{{ stats.taskTotal }} 个任务</span></div>
        <ECharts :options="taskStatusPie" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>训练任务状态</span><span class="chart-note">{{ stats.trainTotal }} 个任务</span></div>
        <ECharts :options="trainStatusPie" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd"><span>训练框架</span><span class="chart-note">{{ stats.trainTotal }} 个任务</span></div>
        <ECharts :options="trainFrameworkPie" height="200" />
      </div>
    </div>

    <!-- 第二行图表：3个柱状图 -->
    <div class="db-charts">
      <div class="chart-card chart-card-wide">
        <div class="chart-hd"><span>各数据集图片数</span><span class="chart-note">{{ stats.datasetCount }} 个数据集</span></div>
        <ECharts :options="datasetBar" height="220" />
      </div>
      <div class="chart-card chart-card-wide">
        <div class="chart-hd"><span>各类型标注任务数</span><span class="chart-note">{{ stats.taskTypeTotal }} 个任务</span></div>
        <ECharts :options="taskTypeBar" height="220" />
      </div>
      <div class="chart-card chart-card-wide">
        <div class="chart-hd"><span>摄像头在线状态</span><span class="chart-note">{{ stats.cameraTotal }} 个摄像头</span></div>
        <ECharts :options="camPie" height="220" />
      </div>
    </div>

    <!-- 底部三列 -->
    <div class="db-footer">
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><Edit /></el-icon> 最近标注任务</div>
        <div class="footer-list">
          <div v-for="t in recentAnno" :key="t.id" class="footer-row">
            <span class="row-name">{{ t.name }}</span>
            <span class="row-type">{{ typeLbl(t.task_type) }}</span>
            <el-tag :type="sTag(t.status)" size="small" effect="plain">{{ sLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentAnno.length" class="footer-empty">暂无数据</div>
        </div>
      </div>
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><Aim /></el-icon> 最近训练任务</div>
        <div class="footer-list">
          <div v-for="t in recentTrain" :key="t.id" class="footer-row">
            <span class="row-name">{{ t.name }}</span>
            <el-tag :type="trainTag(t.status)" size="small" effect="plain">{{ trainLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentTrain.length" class="footer-empty">暂无数据</div>
        </div>
      </div>
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><WarningFilled /></el-icon> 最近告警</div>
        <div class="footer-list">
          <div v-for="a in recentAlarm" :key="a.id" class="footer-row">
            <span class="row-name">{{ a.alarm_type || '告警' }}</span>
            <span class="row-time">{{ fmt(a.created_time) }}</span>
          </div>
          <div v-if="!recentAlarm.length" class="footer-empty">暂无告警</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { UserFilled, Folder, Edit, Aim, Camera, WarningFilled, DataBoard, SetUp } from "@element-plus/icons-vue";
import { useUserStoreHook } from "@/store";
import ECharts from "@/components/ECharts/index.vue";
import { AnnotationAPI } from "@/api/module_annotation";
import { TrainAPI } from "@/api/module_train";
import { getCameraList } from "@/api/module_video/camera";
import { getAlarmRecordList } from "@/api/module_video/alarm";
import UserAPI from "@/api/module_system/user";
import OnlineAPI from "@/api/module_monitor/online";

const router = useRouter();
const userStore = useUserStoreHook();
const now = new Date(); const h = now.getHours();
const timefix = h < 6 ? "夜深了，" : h < 9 ? "早上好，" : h < 12 ? "上午好，" : h < 14 ? "中午好，" : h < 18 ? "下午好，" : "晚上好，";
const welcome = ["注意休息","新的一天","保持高效","午休时间","继续加油","今天辛苦了"][Math.min(5, Math.floor(h / 4))];
const subText = ["夜深了","开启新一天","上午黄金时间","稍作休息","坚持就是胜利","休息一下吧"][Math.min(5, Math.floor(h / 4))];

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
  { label: "数据集", val: stats.datasetCount, icon: Folder, color: "#409eff", bg: "#ecf5ff", extra: `${stats.annotatedCount} 张已标注`, route: "/annotation/dataset" },
  { label: "标注任务", val: stats.taskTotal, icon: Edit, color: "#67c23a", bg: "#f0f9eb", extra: `${stats.taskCompleted} 已完成`, route: "/annotation/task" },
  { label: "训练任务", val: stats.trainTotal, icon: Aim, color: "#f56c6c", bg: "#fef0f0", extra: `${stats.trainRunning} 训练中`, route: "/train/task" },
  { label: "摄像头", val: stats.cameraTotal, icon: Camera, color: "#e6a23c", bg: "#fdf6ec", extra: `${stats.cameraOnline} 在线`, route: "/video/camera" },
  { label: "告警记录", val: stats.alarmCount, icon: WarningFilled, color: "#f56c6c", bg: "#fef0f0", extra: "最近7天", route: "/video/alarm" },
  { label: "在线用户", val: stats.onlineUsers, icon: UserFilled, color: "#409eff", bg: "#ecf5ff", extra: `共 ${stats.totalUsers} 用户`, route: "/system/user" },
]);

const taskTypePie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: Object.entries(taskTypeCount).map(([k, v]) => ({
      name: typeLbl(k), value: v,
      itemStyle: { color: ({ detection: "#409eff", rotated_detection: "#67c23a", segmentation: "#e6a23c", keypoint: "#f56c6c", ocr: "#9b59b6", classification: "#1abc9c" } as any)[k] || "#95a5a6" },
    })).concat(stats.taskTypeTotal === 0 ? [{ name: "暂无", value: 1, itemStyle: { color: "#eee" } }] : []),
  }],
}));

const taskStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.taskPending || 1, name: "待开始", itemStyle: { color: "#909399" } },
      { value: stats.taskInProgress || 1, name: "进行中", itemStyle: { color: "#409eff" } },
      { value: stats.taskCompleted || 1, name: "已完成", itemStyle: { color: "#67c23a" } },
    ],
  }],
}));

const trainStatusPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.trainPending || 1, name: "待开始", itemStyle: { color: "#909399" } },
      { value: stats.trainRunning || 1, name: "训练中", itemStyle: { color: "#409eff" } },
      { value: stats.trainSuccess || 1, name: "已完成", itemStyle: { color: "#67c23a" } },
      { value: stats.trainFailed || 1, name: "失败", itemStyle: { color: "#f56c6c" } },
    ],
  }],
}));

const trainFrameworkPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{ type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 10 },
    data: [
      { value: stats.trainUltralytics || 1, name: "Ultralytics", itemStyle: { color: "#409eff" } },
      { value: stats.trainPaddleX || 1, name: "PaddleX", itemStyle: { color: "#67c23a" } },
    ],
  }],
}));

const datasetBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "8%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: datasetImageCounts.value.map(d => d.name), axisLabel: { rotate: 30, fontSize: 10, interval: 0 } },
  yAxis: { type: "value" as const, name: "图片数" },
  series: [{ type: "bar" as const, barWidth: "50%", itemStyle: { color: "#409eff", borderRadius: [4, 4, 0, 0] }, data: datasetImageCounts.value.map(d => d.count) }],
}));

const taskTypeBar = computed(() => ({
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
  grid: { left: "8%", right: "4%", bottom: "8%", top: "4%", containLabel: true },
  xAxis: { type: "category" as const, data: Object.keys(taskTypeCount).length ? Object.keys(taskTypeCount).map(k => typeLbl(k)) : ["暂无"], axisLabel: { rotate: 20, fontSize: 10 } },
  yAxis: { type: "value" as const, name: "任务数" },
  series: [{ type: "bar" as const, barWidth: "50%", itemStyle: { color: "#67c23a", borderRadius: [4, 4, 0, 0] }, data: Object.keys(taskTypeCount).length ? Object.values(taskTypeCount) : [0] }],
}));

const camPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{
    type: "pie" as const, radius: ["45%", "68%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 12 },
    data: [
      { value: stats.cameraOnline || 1, name: "在线", itemStyle: { color: "#67c23a" } },
      { value: Math.max(1, stats.cameraTotal - stats.cameraOnline) || 1, name: "离线", itemStyle: { color: "#f56c6c" } },
    ],
  }],
}));

function typeLbl(t: string) {
  return ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" } as any)[t] || t;
}
function sTag(s: string) { return ({ pending: "info", in_progress: "primary", completed: "success" } as any)[s] || "info"; }
function sLbl(s: string) { return ({ pending: "待开始", in_progress: "进行中", completed: "已完成" } as any)[s] || s; }
function trainTag(s: string) { return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info"; }
function trainLbl(s: string) { return ({ pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s; }
function fmt(t?: string) { if (!t) return ""; const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }

onMounted(async () => {
  const [annoR, trainR, camR, alarmR, userR, onlineR] = await Promise.allSettled([
    AnnotationAPI.getOverview(),
    TrainAPI.getTaskList(),
    getCameraList({ page_no: 1, page_size: 100 }),
    getAlarmRecordList({ page_no: 1, page_size: 5 }),
    UserAPI.listUser({ page_no: 1, page_size: 1 }),
    OnlineAPI.listOnline({ page_no: 1, page_size: 1 }),
  ]);

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

  // 获取标注任务列表（类型分布 + 状态）
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

  // 获取数据集列表（各数据集图片数）
  try {
    const r = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
    const items = r.data?.data?.items || [];
    datasetImageCounts.value = items.map((d: any) => ({ name: d.name || `数据集#${d.id}`, count: d.image_count || d.annotated_count || 0 }));
  } catch {}
});
</script>

<style scoped>
.db { padding: 16px 20px; }

.db-banner { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.banner-left { display: flex; align-items: center; gap: 14px; }
.avatar { width: 48px; height: 48px; border-radius: 50%; background: var(--el-fill-color-light); display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; }
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.banner-greeting { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.banner-sub { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 2px; }
.banner-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--el-text-color-regular); background: var(--el-fill-color-light); padding: 5px 12px; border-radius: 16px; }
.chip-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

.db-cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }
.db-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 16px; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: box-shadow .15s, transform .15s; }
.db-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.06); transform: translateY(-1px); }
.card-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.card-body { flex: 1; min-width: 0; }
.card-val { font-size: 20px; font-weight: 700; line-height: 1.2; color: var(--el-text-color-primary); }
.card-lbl { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 1px; }
.card-extra { font-size: 11px; color: var(--el-text-color-secondary); white-space: nowrap; }

.db-charts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.db-charts:has(.chart-card-wide) { grid-template-columns: repeat(3, 1fr); }
.chart-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 14px; }
.chart-hd { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; }
.chart-note { font-size: 11px; font-weight: 400; color: var(--el-text-color-secondary); }

.db-footer { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.footer-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 14px; }
.footer-hd { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.footer-list { max-height: 260px; overflow-y: auto; }
.footer-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.footer-row:last-child { border-bottom: none; }
.row-name { font-size: 13px; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.row-type { font-size: 11px; color: var(--el-text-color-secondary); white-space: nowrap; }
.row-time { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.footer-empty { text-align: center; padding: 24px 0; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
