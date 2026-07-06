<template>
  <div class="task-detail">
    <div class="detail-header">
      <el-button text @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </el-button>
      <div class="header-info">
        <h2 class="task-name">{{ task?.name }}</h2>
        <el-tag
          :type="(task?.framework === 'ultralytics' ? 'success' : 'primary') as any"
          size="small"
        >
          {{ task?.framework === "ultralytics" ? "Ultralytics" : "PaddleX" }}
        </el-tag>
        <el-tag :type="statusTag(task?.status || '') as any" size="small">
          {{ statusLabel(task?.status || "") }}
        </el-tag>
        <span v-if="task?.status === 'running'" class="progress-text">
          {{ task?.progress || 0 }}%
        </span>
      </div>
    </div>

    <el-row :gutter="16" class="info-row">
      <el-col :span="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">任务信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="数据集 ID">{{ task?.dataset_id }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ task?.created_time }}</el-descriptions-item>
            <el-descriptions-item label="Docker 镜像">
              <code class="docker-tag">{{ task?.docker_image }}</code>
            </el-descriptions-item>
            <el-descriptions-item label="创建者 ID">{{ task?.created_id }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">超参数</span></template>
          <el-descriptions v-if="task?.hyperparams" :column="1" size="small" border>
            <el-descriptions-item
              v-for="(val, key) in task.hyperparams"
              :key="String(key)"
              :label="String(key)"
            >
              <template v-if="typeof val === 'boolean'">
                <el-tag :type="val ? 'success' : 'info'" size="small">
                  {{ val ? "是" : "否" }}
                </el-tag>
              </template>
              <template v-else>{{ val }}</template>
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else :image-size="40" description="无超参数" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">时间信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="开始时间">
              {{ task?.started_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="结束时间">
              {{ task?.finished_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="耗时">{{ durationText }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="action-row">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span class="card-title">操作</span></template>
          <div class="action-buttons">
            <template v-if="task?.status === 'pending'">
              <el-button type="primary" icon="VideoPlay" @click="handleStart">开始训练</el-button>
              <el-button icon="Edit" @click="handleEditParams">编辑参数</el-button>
              <el-button type="danger" icon="Delete" @click="handleDelete">删除</el-button>
            </template>
            <template v-else-if="task?.status === 'running'">
              <el-button type="danger" icon="VideoPause" @click="handleStop">停止训练</el-button>
            </template>
            <template v-else-if="task?.status === 'success'">
              <el-button type="primary" icon="View" @click="handleViewModel">查看模型</el-button>
              <el-button icon="DataAnalysis" @click="handleEvaluate">评估模型</el-button>
              <el-button icon="Download" @click="handleExport">导出模型</el-button>
            </template>
            <template v-else-if="task?.status === 'failed'">
              <el-button type="primary" icon="Refresh" @click="handleRetrain">重新训练</el-button>
              <el-button icon="Reading" @click="scrollToLog">查看日志</el-button>
            </template>
            <template v-else-if="task?.status === 'cancelled'">
              <el-button type="primary" icon="Refresh" @click="handleRetrain">重新训练</el-button>
            </template>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="task?.status === 'running'" :gutter="16" class="progress-row">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <span class="card-title">训练进度</span>
          </template>
          <div class="progress-wrapper">
            <div class="progress-bar-area">
              <el-progress
                :percentage="task?.progress || 0"
                :stroke-width="20"
                :text-inside="true"
                status="warning"
              />
            </div>
            <div class="progress-indicator">
              <span class="pulse-dot" />
              <span class="eta-text">训练中，预计剩余 {{ estimatedEta }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- YOLO Metrics -->
    <el-row :gutter="12" class="metrics-row">
      <el-col :span="4">
        <div class="metric-mini">
          <span class="metric-mini-value">{{ yoloMetrics.epoch }}/{{ yoloMetrics.totalEpochs }}</span>
          <span class="metric-mini-label">Epoch</span>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="metric-mini">
          <span class="metric-mini-value">{{ yoloMetrics.boxLoss.toFixed(4) }}</span>
          <span class="metric-mini-label">Box Loss</span>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="metric-mini">
          <span class="metric-mini-value">{{ yoloMetrics.clsLoss.toFixed(4) }}</span>
          <span class="metric-mini-label">Cls Loss</span>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="metric-mini">
          <span class="metric-mini-value metric-green">{{ (yoloMetrics.precision * 100).toFixed(1) }}%</span>
          <span class="metric-mini-label">Precision</span>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="metric-mini">
          <span class="metric-mini-value metric-blue">{{ (yoloMetrics.recall * 100).toFixed(1) }}%</span>
          <span class="metric-mini-label">Recall</span>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="metric-mini">
          <span class="metric-mini-value metric-orange">{{ (yoloMetrics.map50 * 100).toFixed(1) }}%</span>
          <span class="metric-mini-label">mAP@50</span>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="metric-mini">
          <span class="metric-mini-value metric-purple">{{ (yoloMetrics.map5095 * 100).toFixed(1) }}%</span>
          <span class="metric-mini-label">mAP@50:95</span>
        </div>
      </el-col>
    </el-row>

    <!-- Error display -->
    <el-row v-if="task?.error_log" :gutter="16" class="error-row">
      <el-col :span="24">
        <el-alert title="训练失败" type="error" :description="task.error_log.slice(0, 500)" show-icon closable />
      </el-col>
    </el-row>

    <!-- 训练日志 -->
    <el-row :gutter="16" style="margin-top: 0">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="log-header">
              <span class="card-title">训练日志</span>
              <div class="log-controls">
                <span class="log-status" :class="{ connected: wsConnected }">
                  {{ wsConnected ? "已连接" : "未连接" }}
                </span>
                <span class="log-line-count">{{ logLineCount }} 行</span>
                <el-switch
                  v-model="autoScroll"
                  active-text="自动滚动"
                  size="small"
                  style="margin-right: 8px"
                />
                <el-button size="small" text icon="Delete" @click="clearLogs">清空</el-button>
              </div>
            </div>
          </template>
          <div ref="logRef" class="log-container">
            <pre class="log-text">{{ logText || "等待日志..." }}</pre>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="task?.status === 'pending'" :gutter="16" class="params-row">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="log-header">
              <span class="card-title">超参数编辑</span>
              <el-button size="small" text icon="Edit" @click="handleEditParams">编辑</el-button>
            </div>
          </template>
          <p class="text-secondary">超参数当前为只读模式，点击「编辑」返回列表页修改。</p>
          <el-descriptions v-if="task?.hyperparams" :column="3" size="small" border>
            <el-descriptions-item
              v-for="(val, key) in task.hyperparams"
              :key="String(key)"
              :label="String(key)"
            >
              <template v-if="typeof val === 'boolean'">
                <el-tag :type="val ? 'success' : 'info'" size="small">
                  {{ val ? "是" : "否" }}
                </el-tag>
              </template>
              <template v-else>{{ val }}</template>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="task?.status === 'success' && task?.model_repo_id" :gutter="16" class="model-row">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span class="card-title">模型输出</span></template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="模型仓库 ID">
              <el-tag size="small">{{ task.model_repo_id }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <div class="model-actions" style="margin-top: 12px">
            <el-button type="primary" icon="View" @click="handleViewModel">查看模型</el-button>
            <el-button icon="Download" @click="handleExport">导出模型</el-button>
            <el-button icon="DataAnalysis" @click="handleEvaluate">评估模型</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const task = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const wsConnected = ref(false);
const logLineCount = ref(0);
let ws: WebSocket | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

function statusTag(s: string) {
  return (
    {
      pending: "info",
      running: "warning",
      success: "success",
      failed: "danger",
      cancelled: "info",
    }[s] || "info"
  );
}

function statusLabel(s: string) {
  return (
    {
      pending: "待开始",
      running: "训练中",
      success: "已完成",
      failed: "失败",
      cancelled: "已取消",
    }[s] || s
  );
}

const durationText = computed(() => {
  if (!task.value?.started_at) return "—";
  const start = new Date(task.value.started_at).getTime();
  const end = task.value.finished_at ? new Date(task.value.finished_at).getTime() : Date.now();
  const diff = Math.floor((end - start) / 1000);
  if (diff < 60) return `${diff}秒`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分${diff % 60}秒`;
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  return `${h}时${m}分`;
});

const estimatedEta = computed(() => {
  const progress = task.value?.progress || 0;
  if (progress <= 0) return "计算中...";
  if (progress >= 100) return "即将完成";
  const elapsed = task.value?.started_at
    ? (Date.now() - new Date(task.value.started_at).getTime()) / 1000
    : 0;
  if (elapsed <= 0) return "计算中...";
  const total = (elapsed / progress) * 100;
  const remaining = Math.max(0, total - elapsed);
  if (remaining < 60) return `${Math.round(remaining)}秒`;
  if (remaining < 3600) return `${Math.floor(remaining / 60)}分${Math.round(remaining % 60)}秒`;
  const h = Math.floor(remaining / 3600);
  const m = Math.floor((remaining % 3600) / 60);
  return `${h}时${m}分`;
});

// Real-time YOLO metrics
const yoloMetrics = reactive({
  epoch: 0, totalEpochs: 0,
  boxLoss: 0, clsLoss: 0, dflLoss: 0,
  precision: 0, recall: 0, map50: 0, map5095: 0,
  gpuMem: "",
  progress: 0,
});

function parseYoloMetrics(line: string) {
  // Epoch line: "     1/2      0G         1.234      0.567      0.890 ..."
  const epochMatch = line.match(/\s*(\d+)\/(\d+)\s+/);
  if (epochMatch && line.includes("G") && (line.includes("loss") || /\d+\.\d+\s+\d+\.\d+/.test(line))) {
    yoloMetrics.epoch = parseInt(epochMatch[1]);
    yoloMetrics.totalEpochs = parseInt(epochMatch[2]);
    // Extract GPU memory
    const gpuMatch = line.match(/([\d.]+)(G|M)/);
    if (gpuMatch) yoloMetrics.gpuMem = gpuMatch[0];
    // Extract losses: look for decimal numbers after GPU column
    const parts = line.trim().split(/\s+/);
    const lossValues = parts.filter(p => /^\d+\.\d+$/.test(p));
    if (lossValues.length >= 1) yoloMetrics.boxLoss = parseFloat(lossValues[0]);
    if (lossValues.length >= 2) yoloMetrics.clsLoss = parseFloat(lossValues[1]);
    if (lossValues.length >= 3) yoloMetrics.dflLoss = parseFloat(lossValues[2]);
    yoloMetrics.progress = Math.round(yoloMetrics.epoch / yoloMetrics.totalEpochs * 100);
    return;
  }
  // Validation: "all  10  100  0.812  0.745  0.789  0.534"
  if (/^\s+all\s+/.test(line)) {
    const parts = line.trim().split(/\s+/);
    // parts: ["all", "10", "100", "0.812", "0.745", "0.789", "0.534"]
    if (parts.length >= 5) yoloMetrics.precision = parseFloat(parts[3]) || 0;
    if (parts.length >= 6) yoloMetrics.recall = parseFloat(parts[4]) || 0;
    if (parts.length >= 7) yoloMetrics.map50 = parseFloat(parts[5]) || 0;
    if (parts.length >= 8) yoloMetrics.map5095 = parseFloat(parts[6]) || 0;
  }
}

function connectWs(id: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  const wsUrl = `${baseUrl}/api/v1/train/ws/train/logs?task_id=${id}`;
  ws = new WebSocket(wsUrl);
  wsConnected.value = true;
  ws.onmessage = (e: MessageEvent) => {
    const line = e.data;
    logText.value += line + "\n";
    logLineCount.value++;
    // Parse YOLO metrics from log lines
    parseYoloMetrics(line);
    if (autoScroll.value) {
      nextTick(() => requestAnimationFrame(() => {
        if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
      }));
    }
  };
  ws.onclose = () => {
    wsConnected.value = false;
  };
  ws.onerror = () => {
    wsConnected.value = false;
  };
}

function clearLogs() {
  logText.value = "";
  logLineCount.value = 0;
}

function scrollToLog() {
  setTimeout(() => {
    const el = document.querySelector(".log-row");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }, 100);
}

async function loadTask() {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getTaskDetail(id);
  task.value = r.data?.data;
}

async function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    await loadTask();
    if (task.value?.status && task.value.status !== "running") {
      stopPoll();
    }
  }, 5000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function handleStart() {
  await ElMessageBox.confirm(`确定开始训练任务「${task.value?.name}」？`, "提示", { type: "info" });
  ElMessage.info("开始训练功能需要调度器支持");
}

async function handleStop() {
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(task.value.id);
    ElMessage.success("训练已停止");
    await loadTask();
  } catch {
    //
  }
}

function handleEditParams() {
  ElMessage.info("超参数编辑功能请返回列表页操作");
  router.push("/train/task");
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确定删除任务「${task.value?.name}」？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
    });
    await TrainAPI.deleteTask([task.value.id]);
    ElMessage.success("已删除");
    router.push("/train/task");
  } catch {
    //
  }
}

function handleRetrain() {
  ElMessage.info("重新训练功能需要调度器支持");
}

function handleViewModel() {
  if (task.value?.model_repo_id) {
    router.push(`/train/repo?model_id=${task.value.model_repo_id}`);
  } else {
    ElMessage.warning("暂无关联模型");
  }
}

function handleEvaluate() {
  ElMessage.info("评估功能需要后端支持");
}

function handleExport() {
  ElMessage.info("导出功能需要后端支持");
}

onMounted(async () => {
  await loadTask();
  const id = Number(route.params.id);
  if (id) {
    if (task.value?.status === "running") {
      connectWs(id);
      startPoll();
    } else {
      // Load saved logs from API for completed/failed tasks
      try {
        const r = await TrainAPI.getTaskLogs(id);
        if (r.data?.data?.logs) {
          logText.value = r.data.data.logs;
        }
      } catch {}
    }
  }
});

onBeforeUnmount(() => {
  ws?.close();
  stopPoll();
});
</script>

<style scoped lang="scss">
.task-detail {
  padding: 16px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.header-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.task-name {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

.progress-text {
  font-size: 14px;
  font-weight: 500;
  color: #e6a23c;
}

.info-row,
.action-row,
.progress-row,
.log-row,
.params-row,
.model-row {
  margin-bottom: 16px;
}

.info-card {
  height: 100%;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.docker-tag {
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 12px;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}

.action-buttons {
  display: flex;
  gap: 10px;
}

.progress-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
}

.progress-bar-area {
  flex: 1;
}

.progress-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e6a23c;
  animation: pulse-anim 1.2s ease-in-out infinite;
}

@keyframes pulse-anim {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.3);
  }
}

.eta-text {
  font-size: 13px;
  color: #909399;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.log-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #909399;
}

.log-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #909399;
  &::before {
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #909399;
  }
  &.connected {
    color: #67c23a;
    &::before {
      background: #67c23a;
    }
  }
}

.log-line-count {
  font-family: "Cascadia Code", "Fira Code", monospace;
}

.log-container {
  height: 500px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 6px;
  padding: 16px;
}

.log-text {
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.metrics-row { margin-bottom: 16px; }
.metric-mini { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 12px 8px; text-align: center; }
.metric-mini-value { display: block; font-size: 18px; font-weight: 700; font-family: "Cascadia Code", monospace; color: var(--el-text-color-primary); }
.metric-mini-label { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin-top: 2px; }
.metric-green { color: #67c23a; }
.metric-blue { color: #409eff; }
.metric-orange { color: #e6a23c; }
.metric-purple { color: #9b59b6; }
.error-row { margin-bottom: 16px; }

.text-secondary {
  color: #909399;
  font-size: 13px;
  margin-bottom: 12px;
}
</style>
