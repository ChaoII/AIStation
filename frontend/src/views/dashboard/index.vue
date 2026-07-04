<template>
  <div class="dashboard-container">
    <!-- 顶部欢迎卡 -->
    <el-card shadow="never" class="welcome-card">
      <div class="welcome-inner">
        <div class="welcome-left">
          <div class="avatar-wrap">
            <img v-if="userStore.basicInfo.avatar" class="avatar-img" :src="userStore.basicInfo.avatar + '?imageView2/1/w/80/h/80'" />
            <el-icon v-else :size="36"><UserFilled /></el-icon>
          </div>
          <div class="welcome-text">
            <div class="greeting">{{ timefix }}{{ userStore.basicInfo.name }}，{{ welcome }}</div>
            <div class="sub-text">{{ subText }}</div>
          </div>
        </div>
        <div class="welcome-stats">
          <div class="stat-chip"><span class="chip-dot" style="background:#67c23a" />{{ stats.onlineUsers }} 在线</div>
          <div class="stat-chip"><span class="chip-dot" style="background:#409eff" />{{ stats.totalUsers }} 用户</div>
          <div class="stat-chip"><span class="chip-dot" style="background:#e6a23c" />{{ stats.activeJobs }} 任务</div>
        </div>
      </div>
    </el-card>

    <!-- 核心指标卡片 -->
    <el-row :gutter="16" class="mt-4">
      <el-col :xs="12" :sm="6" v-for="card in metricCards" :key="card.label">
        <el-card shadow="never" class="metric-card" @click="card.route && router.push(card.route)">
          <div class="metric-inner">
            <div class="metric-icon" :style="{ background: card.bg }">
              <el-icon :size="22" :color="card.color"><component :is="card.icon" /></el-icon>
            </div>
            <div class="metric-info">
              <div class="metric-value">{{ card.value }}</div>
              <div class="metric-label">{{ card.label }}</div>
            </div>
          </div>
          <div class="metric-footer">
            <span class="trend" :class="card.trend >= 0 ? 'up' : 'down'">
              {{ card.trend >= 0 ? '↑' : '↓' }} {{ Math.abs(card.trend) }}%
            </span>
            <span class="metric-sub">{{ card.sub }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 + 列表 -->
    <el-row :gutter="16" class="mt-4">
      <!-- ECharts 环形图 -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">标注任务分布</span></template>
          <div class="chart-box"><ECharts :options="pieOptions" height="260" /></div>
        </el-card>
      </el-col>

      <!-- ECharts 柱状图 -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">系统资源</span></template>
          <div class="chart-box"><ECharts :options="barOptions" height="260" /></div>
        </el-card>
      </el-col>

      <!-- 快速入口 -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">快速入口</span></template>
          <div class="quick-grid">
            <div v-for="item in quickLinks" :key="item.label" class="quick-item" @click="router.push(item.route)">
              <div class="quick-icon" :style="{ background: item.bg }">
                <el-icon :size="20" :color="item.color"><component :is="item.icon" /></el-icon>
              </div>
              <span class="quick-label">{{ item.label }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 底部：系统信息 + 最新动态 -->
    <el-row :gutter="16" class="mt-4">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never">
          <template #header><span class="card-title">系统信息</span></template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="服务版本">v{{ sysInfo.version }}</el-descriptions-item>
            <el-descriptions-item label="运行环境">{{ sysInfo.environment }}</el-descriptions-item>
            <el-descriptions-item label="Python 版本">{{ sysInfo.pythonVersion }}</el-descriptions-item>
            <el-descriptions-item label="数据库">{{ sysInfo.database }}</el-descriptions-item>
            <el-descriptions-item label="Redis">{{ sysInfo.redisStatus }}</el-descriptions-item>
            <el-descriptions-item label="CPU 负载">{{ sysInfo.cpuLoad }}</el-descriptions-item>
            <el-descriptions-item label="内存使用">{{ sysInfo.memUsage }}</el-descriptions-item>
            <el-descriptions-item label="磁盘使用">{{ sysInfo.diskUsage }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="never">
          <template #header><span class="card-title">最近动态</span></template>
          <div class="activity-list">
            <div v-for="(act, i) in activities" :key="i" class="activity-item">
              <div class="activity-dot" :style="{ background: act.color }" />
              <div class="activity-content">
                <span class="activity-text">{{ act.text }}</span>
                <span class="activity-time">{{ act.time }}</span>
              </div>
            </div>
            <div v-if="activities.length === 0" class="empty-tip">暂无动态</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { UserFilled, Connection, Monitor, Folder, Document, Edit, DataBoard, Aim, Collection, Setting, Bell } from "@element-plus/icons-vue";
import { useUserStoreHook } from "@/store";
import ECharts from "@/components/ECharts/index.vue";
import { AnnotationAPI } from "@/api/module_annotation";
import { TrainAPI } from "@/api/module_train";
import UserAPI from "@/api/module_system/user";
import OnlineAPI from "@/api/module_monitor/online";
import ServerAPI from "@/api/module_monitor/server";

const router = useRouter();
const userStore = useUserStoreHook();

const now = new Date();
const hour = now.getHours();
const timefix = hour < 6 ? "夜深了，" : hour < 9 ? "早上好，" : hour < 12 ? "上午好，" : hour < 14 ? "中午好，" : hour < 18 ? "下午好，" : "晚上好，";
const welcome = hour < 6 ? "注意休息" : hour < 9 ? "新的一天开始了" : hour < 12 ? "加油工作" : hour < 14 ? "午休时间" : hour < 18 ? "继续努力" : "今天辛苦了";
const subText = hour < 6 ? "夜深了，注意休息哦～" : hour < 9 ? "早晨！今天有哪些任务要完成？" : hour < 12 ? "上午好，保持高效工作！" : hour < 14 ? "午休片刻，下午继续战斗" : hour < 18 ? "下午好，坚持就是胜利" : "辛苦了，今天收获满满！";

const stats = reactive({
  onlineUsers: 0, totalUsers: 0, activeJobs: 0,
  datasetCount: 0, taskCount: 0, annotatedCount: 0,
  trainTaskCount: 0, cameraCount: 0,
});
const sysInfo = reactive({
  version: "0.1.0", environment: "dev", pythonVersion: "3.13",
  database: "PostgreSQL 17", redisStatus: "已连接",
  cpuLoad: "--", memUsage: "--", diskUsage: "--",
});
const activities = ref<any[]>([]);

const metricCards = computed(() => [
  { label: "数据集", value: stats.datasetCount, icon: Folder, color: "#409eff", bg: "#ecf5ff", trend: 0, sub: "标注数据集", route: "/annotation/dataset" },
  { label: "标注任务", value: stats.taskCount, icon: Edit, color: "#67c23a", bg: "#f0f9eb", trend: 0, sub: "标注任务", route: "/annotation/task" },
  { label: "已标注图片", value: stats.annotatedCount, icon: Collection, color: "#e6a23c", bg: "#fdf6ec", trend: 0, sub: "已完成", route: "/annotation/task" },
  { label: "训练任务", value: stats.trainTaskCount, icon: Aim, color: "#f56c6c", bg: "#fef0f0", trend: 0, sub: "模型训练", route: "/train/task" },
]);

const pieOptions = computed(() => ({
  tooltip: { trigger: "item" as const, formatter: "{b}: {c} ({d}%)" },
  series: [{
    type: "pie", radius: ["45%", "70%"], avoidLabelOverlap: true,
    label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
    data: [
      { value: stats.datasetCount || 1, name: "数据集", itemStyle: { color: "#409eff" } },
      { value: stats.taskCount || 1, name: "标注任务", itemStyle: { color: "#67c23a" } },
      { value: stats.annotatedCount || 1, name: "已标注", itemStyle: { color: "#e6a23c" } },
      { value: stats.trainTaskCount || 1, name: "训练任务", itemStyle: { color: "#f56c6c" } },
    ],
  }],
}));

const barOptions = computed(() => {
  const cpuVal = parseFloat(sysInfo.cpuLoad) || 0;
  const memVal = parseFloat(sysInfo.memUsage) || 0;
  const diskVal = parseFloat(sysInfo.diskUsage) || 0;
  return {
    tooltip: { trigger: "axis" as const },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: { type: "category" as const, data: ["CPU", "内存", "磁盘"] },
    yAxis: { type: "value" as const, max: 100, axisLabel: { formatter: "{value}%" } },
    series: [{
      type: "bar" as const, barWidth: "40%",
      data: [
        { value: cpuVal, itemStyle: { color: cpuVal > 80 ? "#f56c6c" : cpuVal > 50 ? "#e6a23c" : "#67c23a" } },
        { value: memVal, itemStyle: { color: memVal > 80 ? "#f56c6c" : memVal > 50 ? "#e6a23c" : "#67c23a" } },
        { value: diskVal, itemStyle: { color: diskVal > 80 ? "#f56c6c" : diskVal > 50 ? "#e6a23c" : "#67c23a" } },
      ],
    }],
  };
});

const quickLinks = [
  { label: "数据集", icon: Folder, route: "/annotation/dataset", bg: "#ecf5ff", color: "#409eff" },
  { label: "标注任务", icon: Edit, route: "/annotation/task", bg: "#f0f9eb", color: "#67c23a" },
  { label: "模型训练", icon: Aim, route: "/train/task", bg: "#fef0f0", color: "#f56c6c" },
  { label: "模型仓库", icon: DataBoard, route: "/train/repo", bg: "#fdf6ec", color: "#e6a23c" },
  { label: "系统管理", icon: Setting, route: "/system/user", bg: "#f4f4f5", color: "#909399" },
  { label: "公告通知", icon: Bell, route: "/system/notice", bg: "#ecf5ff", color: "#409eff" },
];

onMounted(async () => {
  try {
    const [annoR, userR, onlineR, serverR, trainR] = await Promise.allSettled([
      AnnotationAPI.getOverview(),
      UserAPI.listUser({ page_no: 1, page_size: 1 }),
      OnlineAPI.listOnline({ page_no: 1, page_size: 1 }),
      ServerAPI.getServer(),
      TrainAPI.getTaskList(),
    ]);

    if (annoR.status === "fulfilled") {
      const d = annoR.value.data?.data;
      if (d) { stats.datasetCount = d.dataset_count || 0; stats.taskCount = d.task_count || 0; stats.annotatedCount = d.annotated_image_count || 0; }
    }
    if (userR.status === "fulfilled") { stats.totalUsers = userR.value.data?.data?.total || 0; }
    if (onlineR.status === "fulfilled") { stats.onlineUsers = onlineR.value.data?.data?.total || 0; }
    if (trainR.status === "fulfilled") { stats.trainTaskCount = (trainR.value.data?.data || []).length; }

    if (serverR.status === "fulfilled") {
      const s = serverR.value.data?.data;
      if (s) {
        sysInfo.cpuLoad = s.cpu?.used ?? "--";
        sysInfo.memUsage = s.mem?.usage ?? "--";
        sysInfo.diskUsage = s.disk?.usage ?? "--";
        sysInfo.pythonVersion = s.system?.pythonVersion ?? "3.13";
      }
    }
  } catch {}
});
</script>

<style scoped>
.dashboard-container { padding: 16px; max-width: 1400px; margin: 0 auto; }
.welcome-card { border-radius: 12px; }
.welcome-inner { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.welcome-left { display: flex; align-items: center; gap: 16px; }
.avatar-wrap { width: 56px; height: 56px; border-radius: 50%; background: var(--el-fill-color-light); display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; }
.greeting { font-size: 18px; font-weight: 700; color: var(--el-text-color-primary); }
.sub-text { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.welcome-stats { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-chip { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--el-text-color-regular); background: var(--el-fill-color-light); padding: 6px 14px; border-radius: 20px; }
.chip-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.mt-4 { margin-top: 16px; }
.metric-card { border-radius: 10px; cursor: pointer; transition: transform .15s, box-shadow .15s; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.08); }
.metric-inner { display: flex; align-items: center; gap: 14px; }
.metric-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.metric-info { flex: 1; min-width: 0; }
.metric-value { font-size: 24px; font-weight: 700; line-height: 1.2; color: var(--el-text-color-primary); }
.metric-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.metric-footer { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--el-border-color-lighter); font-size: 12px; }
.trend { font-weight: 600; }
.trend.up { color: #67c23a; }
.trend.down { color: #f56c6c; }
.metric-sub { color: var(--el-text-color-secondary); }

.chart-card { border-radius: 10px; height: 100%; }
.chart-box { padding: 4px 0; }
.card-title { font-size: 14px; font-weight: 600; }

.quick-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 4px 0; }
.quick-item { display: flex; flex-direction: column; align-items: center; gap: 8px; cursor: pointer; padding: 12px 4px; border-radius: 8px; transition: background .15s; }
.quick-item:hover { background: var(--el-fill-color-light); }
.quick-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.quick-label { font-size: 12px; color: var(--el-text-color-regular); }

.activity-list { max-height: 300px; overflow-y: auto; }
.activity-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.activity-item:last-child { border-bottom: none; }
.activity-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.activity-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.activity-text { font-size: 13px; color: var(--el-text-color-primary); }
.activity-time { font-size: 12px; color: var(--el-text-color-secondary); }
.empty-tip { text-align: center; padding: 32px 0; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
