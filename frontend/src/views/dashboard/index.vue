<template>
  <div class="db">
    <!-- 顶部横幅 -->
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
        <div class="chip"><span class="chip-dot" style="background:#e6a23c" />{{ stats.taskInProgress + stats.trainRunning }} 进行中</div>
      </div>
    </div>

    <!-- 核心指标 -->
    <div class="db-cards">
      <div v-for="c in cards" :key="c.label" class="db-card" @click="c.route && router.push(c.route)">
        <div class="card-icon" :style="{ background: c.bg }"><el-icon :size="20" :color="c.color"><component :is="c.icon" /></el-icon></div>
        <div class="card-body">
          <div class="card-val">{{ c.val }}</div>
          <div class="card-lbl">{{ c.label }}</div>
        </div>
        <div class="card-extra">{{ c.extra }}</div>
      </div>
    </div>

    <!-- 图表行 -->
    <div class="db-charts">
      <div class="chart-card">
        <div class="chart-hd">标注任务状态</div>
        <ECharts :options="annoPie" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd">训练任务状态</div>
        <ECharts :options="trainPie" height="200" />
      </div>
      <div class="chart-card">
        <div class="chart-hd">摄像头在线率</div>
        <ECharts :options="camPie" height="200" />
      </div>
    </div>

    <!-- 最近动态 -->
    <div class="db-footer">
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><Edit /></el-icon> 最近标注任务</div>
        <div class="footer-list">
          <div v-for="t in recentAnnoTasks" :key="t.id" class="footer-row">
            <span class="row-name">{{ t.name }}</span>
            <el-tag :type="annoStatusTag(t.status)" size="small" effect="plain">{{ annoStatusLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentAnnoTasks.length" class="footer-empty">暂无数据</div>
        </div>
      </div>
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><Aim /></el-icon> 最近训练任务</div>
        <div class="footer-list">
          <div v-for="t in recentTrainTasks" :key="t.id" class="footer-row">
            <span class="row-name">{{ t.name }}</span>
            <el-tag :type="trainStatusTag(t.status)" size="small" effect="plain">{{ trainStatusLbl(t.status) }}</el-tag>
          </div>
          <div v-if="!recentTrainTasks.length" class="footer-empty">暂无数据</div>
        </div>
      </div>
      <div class="footer-card">
        <div class="footer-hd"><el-icon size="14"><Connection /></el-icon> 告警记录</div>
        <div class="footer-list">
          <div v-for="a in recentAlarms" :key="a.id" class="footer-row">
            <span class="row-name">{{ a.name || a.alarm_type || '告警' }}</span>
            <span class="row-time">{{ fmtTime(a.created_time) }}</span>
          </div>
          <div v-if="!recentAlarms.length" class="footer-empty">暂无告警</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { UserFilled, Folder, Edit, Aim, Camera, Connection, WarningFilled } from "@element-plus/icons-vue";
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
const now = new Date();
const h = now.getHours();
const timefix = h < 6 ? "夜深了，" : h < 9 ? "早上好，" : h < 12 ? "上午好，" : h < 14 ? "中午好，" : h < 18 ? "下午好，" : "晚上好，";
const welcome = h < 6 ? "注意休息" : h < 9 ? "新的一天" : h < 12 ? "保持高效" : h < 14 ? "午休时间" : h < 18 ? "继续加油" : "今天辛苦了";
const subText = h < 6 ? "夜深了" : h < 9 ? "开启新一天的工作" : h < 12 ? "上午是黄金时间" : h < 14 ? "稍作休息" : h < 18 ? "坚持就是胜利" : "休息一下吧";

const stats = reactive({
  onlineUsers: 0, totalUsers: 0,
  datasetCount: 0, taskCount: 0, annotatedCount: 0,
  taskPending: 0, taskInProgress: 0, taskCompleted: 0,
  trainPending: 0, trainRunning: 0, trainSuccess: 0, trainFailed: 0,
  cameraTotal: 0, cameraOnline: 0,
  alarmCount: 0,
});

const recentAnnoTasks = ref<any[]>([]);
const recentTrainTasks = ref<any[]>([]);
const recentAlarms = ref<any[]>([]);

const cards = computed(() => [
  { label: "标注数据集", val: stats.datasetCount, icon: Folder, color: "#409eff", bg: "#ecf5ff", extra: `${stats.annotatedCount} 张已标注`, route: "/annotation/dataset" },
  { label: "标注任务", val: stats.taskCount, icon: Edit, color: "#67c23a", bg: "#f0f9eb", extra: `${stats.taskCompleted} 已完成`, route: "/annotation/task" },
  { label: "训练任务", val: stats.trainPending + stats.trainRunning + stats.trainSuccess + stats.trainFailed, icon: Aim, color: "#f56c6c", bg: "#fef0f0", extra: `${stats.trainRunning} 进行中`, route: "/train/task" },
  { label: "摄像头", val: stats.cameraTotal, icon: Camera, color: "#e6a23c", bg: "#fdf6ec", extra: `${stats.cameraOnline} 在线`, route: "/video/camera" },
]);

const annoPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c}" },
  series: [{
    type: "pie" as const, radius: ["50%", "70%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.taskPending || 1, name: "待开始", itemStyle: { color: "#909399" } },
      { value: stats.taskInProgress || 1, name: "进行中", itemStyle: { color: "#409eff" } },
      { value: stats.taskCompleted || 1, name: "已完成", itemStyle: { color: "#67c23a" } },
    ],
  }],
}));

const trainPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c}" },
  series: [{
    type: "pie" as const, radius: ["50%", "70%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.trainPending || 1, name: "待开始", itemStyle: { color: "#909399" } },
      { value: stats.trainRunning || 1, name: "训练中", itemStyle: { color: "#409eff" } },
      { value: stats.trainSuccess || 1, name: "已完成", itemStyle: { color: "#67c23a" } },
      { value: stats.trainFailed || 1, name: "失败", itemStyle: { color: "#f56c6c" } },
    ],
  }],
}));

const camPie = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c}" },
  series: [{
    type: "pie" as const, radius: ["50%", "70%"], center: ["50%", "50%"],
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.cameraOnline || 1, name: "在线", itemStyle: { color: "#67c23a" } },
      { value: Math.max(1, (stats.cameraTotal - stats.cameraOnline)) || 1, name: "离线", itemStyle: { color: "#f56c6c" } },
    ],
  }],
}));

function fmtTime(t?: string) {
  if (!t) return "";
  const d = new Date(t);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function annoStatusTag(s: string) {
  return ({ pending: "info", in_progress: "primary", completed: "success" } as any)[s] || "info";
}
function annoStatusLbl(s: string) {
  return ({ pending: "待开始", in_progress: "进行中", completed: "已完成" } as any)[s] || s;
}
function trainStatusTag(s: string) {
  return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info";
}
function trainStatusLbl(s: string) {
  return ({ pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s;
}

onMounted(async () => {
  const [annoR, trainR, camR, alarmR, userR, onlineR] = await Promise.allSettled([
    AnnotationAPI.getOverview(),
    TrainAPI.getTaskList(),
    getCameraList({ page_no: 1, page_size: 1 }),
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
    for (const t of tasks) {
      if (t.status === "pending") stats.trainPending++;
      else if (t.status === "running") stats.trainRunning++;
      else if (t.status === "success") stats.trainSuccess++;
      else if (t.status === "failed") stats.trainFailed++;
    }
    recentTrainTasks.value = tasks.slice(0, 5);
  }

  if (camR.status === "fulfilled") {
    const items = camR.value.data?.data?.items || [];
    stats.cameraTotal = camR.value.data?.data?.total || 0;
    stats.cameraOnline = items.filter((c: any) => c.reachable === true).length;
  }

  if (alarmR.status === "fulfilled") {
    const items = alarmR.value.data?.data?.items || [];
    stats.alarmCount = alarmR.value.data?.data?.total || 0;
    recentAlarms.value = items.slice(0, 5);
  }

  if (userR.status === "fulfilled") stats.totalUsers = userR.value.data?.data?.total || 0;
  if (onlineR.status === "fulfilled") stats.onlineUsers = onlineR.value.data?.data?.total || 0;

  // Fetch annotation tasks for status breakdown
  try {
    const r = await AnnotationAPI.getTaskList({ page_no: 1, page_size: 100 });
    const tasks = r.data?.data?.items || [];
    for (const t of tasks) {
      if (t.status === "pending") stats.taskPending++;
      else if (t.status === "in_progress") stats.taskInProgress++;
      else if (t.status === "completed") stats.taskCompleted++;
    }
    recentAnnoTasks.value = tasks.slice(0, 5);
  } catch {}
});
</script>

<style scoped>
.db { padding: 16px 20px; }

/* 横幅 */
.db-banner { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.banner-left { display: flex; align-items: center; gap: 14px; }
.avatar { width: 48px; height: 48px; border-radius: 50%; background: var(--el-fill-color-light); display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; }
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.banner-greeting { font-size: 17px; font-weight: 700; color: var(--el-text-color-primary); }
.banner-sub { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 2px; }
.banner-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--el-text-color-regular); background: var(--el-fill-color-light); padding: 5px 12px; border-radius: 16px; }
.chip-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

/* 核心指标 */
.db-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }
.db-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 18px; display: flex; align-items: center; gap: 14px; cursor: pointer; transition: box-shadow .15s, transform .15s; }
.db-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.06); transform: translateY(-1px); }
.card-icon { width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.card-body { flex: 1; min-width: 0; }
.card-val { font-size: 22px; font-weight: 700; line-height: 1.2; color: var(--el-text-color-primary); }
.card-lbl { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.card-extra { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }

/* 图表行 */
.db-charts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 16px; }
.chart-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 16px; }
.chart-hd { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 8px; }

/* 底部三列 */
.db-footer { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.footer-card { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 16px; }
.footer-hd { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.footer-list { max-height: 260px; overflow-y: auto; }
.footer-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--el-border-color-lighter); gap: 8px; }
.footer-row:last-child { border-bottom: none; }
.row-name { font-size: 13px; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.row-time { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.footer-empty { text-align: center; padding: 24px 0; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
