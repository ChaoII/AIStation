<template>
  <div class="task-detail">
    <div class="detail-header">
      <el-button text size="small" @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="task-name">{{ task?.name }}</span>
      <el-tag :type="(task?.framework === 'ultralytics' ? 'success' : 'primary') as any" size="small" effect="plain">
        {{ task?.framework === "ultralytics" ? "Ultralytics" : "PaddleX" }}
      </el-tag>
      <el-tag :type="(statusTag(task?.status || '') as any)" size="small" :effect="task?.status === 'running' ? 'dark' : 'plain'">
        {{ statusLabel(task?.status || "") }}
      </el-tag>
      <span v-if="displayProgress > 0" class="progress-text">{{ displayProgress }}%</span>
    </div>

    <el-row :gutter="16" class="info-row">
      <el-col :span="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">任务信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="数据集 ID">{{ task?.dataset_id }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ task?.created_time }}</el-descriptions-item>
            <el-descriptions-item label="Docker 镜像"><code class="docker-tag">{{ task?.docker_image }}</code></el-descriptions-item>
            <el-descriptions-item label="创建者 ID">{{ task?.created_id }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">超参数</span></template>
          <el-descriptions v-if="task?.hyperparams" :column="1" size="small" border>
            <el-descriptions-item v-for="(val, key) in task.hyperparams" :key="String(key)" :label="String(key)">
              <template v-if="typeof val === 'boolean'">
                <el-tag :type="val ? 'success' : 'info'" size="small">{{ val ? "是" : "否" }}</el-tag>
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
            <el-descriptions-item label="开始时间">{{ task?.started_at || "—" }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ task?.finished_at || "—" }}</el-descriptions-item>
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
              <el-button type="danger" icon="Delete" @click="handleDelete">删除</el-button>
            </template>
            <template v-else-if="task?.status === 'failed'">
              <el-button type="primary" icon="Refresh" @click="handleRetrain">重新训练</el-button>
              <el-button icon="Reading" @click="scrollToLog">查看日志</el-button>
              <el-button type="danger" icon="Delete" @click="handleDelete">删除</el-button>
            </template>
            <template v-else-if="task?.status === 'cancelled'">
              <el-button type="primary" icon="Refresh" @click="handleRetrain">重新训练</el-button>
            </template>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="displayProgress > 0" :gutter="16" class="progress-row">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span class="card-title">训练进度</span></template>
          <div class="progress-wrapper">
            <div class="progress-bar-area">
              <el-progress
                :percentage="displayProgress"
                :stroke-width="20"
                :text-inside="true"
                :status="task?.status === 'success' ? 'success' : task?.status === 'failed' ? 'exception' : 'warning'"
              />
            </div>
            <div v-if="task?.status === 'running'" class="progress-indicator">
              <span class="pulse-dot" />
              <span class="eta-text">训练中，预计剩余 {{ estimatedEta }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="metrics-row">
      <el-col :span="3"><div class="metric-mini"><span class="metric-val">{{ displayMetrics.epoch }}</span><span class="metric-lbl">Epoch</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val">{{ displayMetrics.boxLoss }}</span><span class="metric-lbl">Box Loss</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val">{{ displayMetrics.clsLoss }}</span><span class="metric-lbl">Cls Loss</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val">{{ displayMetrics.dflLoss }}</span><span class="metric-lbl">Dfl Loss</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val metric-green">{{ displayMetrics.precision }}</span><span class="metric-lbl">Precision</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val metric-blue">{{ displayMetrics.recall }}</span><span class="metric-lbl">Recall</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val metric-orange">{{ displayMetrics.map50 }}</span><span class="metric-lbl">mAP@50</span></div></el-col>
      <el-col :span="3"><div class="metric-mini"><span class="metric-val metric-purple">{{ displayMetrics.map5095 }}</span><span class="metric-lbl">mAP@50:95</span></div></el-col>
    </el-row>

    <el-row v-if="task?.error_log" :gutter="16" class="error-row">
      <el-col :span="24">
        <el-alert title="训练失败" type="error" :description="task.error_log.slice(0, 500)" show-icon closable />
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:0">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span class="card-title">Loss 趋势</span></template>
          <div v-if="displayMetricsLog.length > 0">
            <v-chart :option="lossChartOption" style="height:300px" autoresize />
          </div>
          <div v-else class="chart-placeholder">等待训练数据...</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span class="card-title">验证指标趋势</span></template>
          <div v-if="displayMetricsLog.length > 0">
            <v-chart :option="valChartOption" style="height:300px" autoresize />
          </div>
          <div v-else class="chart-placeholder">等待训练数据...</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row v-if="displayBestMetrics || displayLastMetrics" :gutter="16" style="margin-top:16px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span class="card-title">指标对比</span></template>
          <el-table :data="compareTableData" border size="small" style="width:100%">
            <el-table-column prop="label" label="指标" width="140" />
            <el-table-column label="最优 Epoch">
              <template #default="{ row }">
                <span v-if="displayBestMetrics && row.getter(displayBestMetrics) != null" class="mono">{{ row.fmt(row.getter(displayBestMetrics)) }}</span>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="最终 Epoch">
              <template #default="{ row }">
                <span v-if="displayLastMetrics && row.getter(displayLastMetrics) != null" class="mono">{{ row.fmt(row.getter(displayLastMetrics)) }}</span>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header>
            <div class="log-header">
              <span class="card-title">训练日志</span>
              <div class="log-controls">
                <span class="log-status" :class="{ connected: wsConnected }">{{ wsConnected ? "已连接" : "未连接" }}</span>
                <span class="log-line-count">{{ logLineCount }} 行</span>
                <el-switch v-model="autoScroll" active-text="自动滚动" size="small" style="margin-right:8px" />
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

    <el-row v-if="task?.status === 'success' && task?.model_repo_id" :gutter="16" style="margin-top:16px">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span class="card-title">模型输出</span></template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="模型仓库 ID"><el-tag size="small">{{ task.model_repo_id }}</el-tag></el-descriptions-item>
          </el-descriptions>
          <div class="model-actions" style="margin-top:12px">
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
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

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
  return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info";
}
function statusLabel(s: string) {
  return ({ pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s;
}

const durationText = computed(() => {
  if (!task.value?.started_at) return "—";
  const start = new Date(task.value.started_at).getTime();
  const end = task.value.finished_at ? new Date(task.value.finished_at).getTime() : Date.now();
  const diff = Math.floor((end - start) / 1000);
  if (diff < 60) return `${diff}秒`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分${diff % 60}秒`;
  return `${Math.floor(diff / 3600)}时${Math.floor((diff % 3600) / 60)}分`;
});

const displayProgress = computed(() => {
  if (yoloMetrics.epoch > 0 && yoloMetrics.totalEpochs > 0) return Math.round(yoloMetrics.epoch / yoloMetrics.totalEpochs * 100);
  return task.value?.progress || 0;
});

const estimatedEta = computed(() => {
  const p = displayProgress.value;
  if (p <= 0) return "计算中...";
  if (p >= 100) return "即将完成";
  const elapsed = task.value?.started_at ? (Date.now() - new Date(task.value.started_at).getTime()) / 1000 : 0;
  if (elapsed <= 0) return "计算中...";
  const remaining = Math.max(0, (elapsed / p) * 100 - elapsed);
  if (remaining < 60) return `${Math.round(remaining)}秒`;
  if (remaining < 3600) return `${Math.floor(remaining / 60)}分${Math.round(remaining % 60)}秒`;
  return `${Math.floor(remaining / 3600)}时${Math.floor((remaining % 3600) / 60)}分`;
});

const yoloMetrics = reactive({
  epoch: 0, totalEpochs: 0,
  boxLoss: 0, clsLoss: 0, dflLoss: 0,
  precision: 0, recall: 0, map50: 0, map5095: 0,
  gpuMem: "", progress: 0,
});

const liveMetricsLog = ref<any[]>([]);
const liveBestMetrics = computed(() => {
  const v = liveMetricsLog.value.filter((m: any) => m.map50 != null);
  if (v.length) return v.reduce((b: any, m: any) => m.map50 > (b.map50 || 0) ? m : b, v[0]);
  return liveMetricsLog.value.length ? liveMetricsLog.value[liveMetricsLog.value.length - 1] : null;
});
const liveLastMetrics = computed(() => liveMetricsLog.value.length ? liveMetricsLog.value[liveMetricsLog.value.length - 1] : null);
const metricsLog = computed<any[]>(() => task.value?.metrics_log || []);
const bestMetrics = computed<any>(() => task.value?.best_metrics || null);
const lastMetrics = computed<any>(() => task.value?.last_metrics || null);
const displayMetricsLog = computed<any[]>(() => liveMetricsLog.value.length ? liveMetricsLog.value : metricsLog.value);
const displayBestMetrics = computed<any>(() => liveBestMetrics.value || bestMetrics.value);
const displayLastMetrics = computed<any>(() => liveLastMetrics.value || lastMetrics.value);

const displayMetrics = computed(() => {
  const hasLive = yoloMetrics.epoch > 0;
  if (task.value?.status === 'running' && hasLive) {
    return {
      epoch: `${yoloMetrics.epoch}/${yoloMetrics.totalEpochs}`,
      boxLoss: yoloMetrics.boxLoss.toFixed(4),
      clsLoss: yoloMetrics.clsLoss.toFixed(4),
      dflLoss: yoloMetrics.dflLoss.toFixed(4),
      precision: yoloMetrics.precision > 0 ? (yoloMetrics.precision * 100).toFixed(1) + '%' : '0.0%',
      recall: yoloMetrics.recall > 0 ? (yoloMetrics.recall * 100).toFixed(1) + '%' : '0.0%',
      map50: yoloMetrics.map50 > 0 ? (yoloMetrics.map50 * 100).toFixed(1) + '%' : '0.0%',
      map5095: yoloMetrics.map5095 > 0 ? (yoloMetrics.map5095 * 100).toFixed(1) + '%' : '0.0%',
    };
  }
  const last = displayLastMetrics.value;
  if (last) return metricsFromLast(last);
  return { epoch: '—', boxLoss: '—', clsLoss: '—', dflLoss: '—', precision: '—', recall: '—', map50: '—', map5095: '—' };
});

function metricsFromLast(last: any) {
  return {
    epoch: `${last.epoch || '?'}/${last.total_epochs || '?'}`,
    boxLoss: last.box_loss != null ? last.box_loss.toFixed(4) : '—',
    clsLoss: last.cls_loss != null ? last.cls_loss.toFixed(4) : '—',
    dflLoss: last.dfl_loss != null ? last.dfl_loss.toFixed(4) : '—',
    precision: last.precision != null ? (last.precision * 100).toFixed(1) + '%' : '—',
    recall: last.recall != null ? (last.recall * 100).toFixed(1) + '%' : '—',
    map50: last.map50 != null ? (last.map50 * 100).toFixed(1) + '%' : '—',
    map5095: last.map5095 != null ? (last.map5095 * 100).toFixed(1) + '%' : '—',
  };
}

const lossChartOption = computed(() => {
  const log = displayMetricsLog.value;
  if (!log.length) return {};
  return {
    tooltip: { trigger: "axis" },
    legend: { data: ["Box Loss", "Cls Loss", "Dfl Loss"], top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: log.map((m: any) => m.epoch), name: "Epoch" },
    yAxis: { type: "value", name: "Loss" },
    series: [
      { name: "Box Loss", type: "line", data: log.map((m: any) => m.box_loss ?? null) },
      { name: "Cls Loss", type: "line", data: log.map((m: any) => m.cls_loss ?? null) },
      { name: "Dfl Loss", type: "line", data: log.map((m: any) => m.dfl_loss ?? null) },
    ],
  };
});

const valChartOption = computed(() => {
  const log = displayMetricsLog.value.filter((m: any) => m.precision != null);
  if (!log.length) return {};
  return {
    tooltip: { trigger: "axis" },
    legend: { data: ["Precision", "Recall", "mAP@50", "mAP@50:95"], top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: log.map((m: any) => m.epoch), name: "Epoch" },
    yAxis: { type: "value", name: "Metric" },
    series: [
      { name: "Precision", type: "line", data: log.map((m: any) => m.precision ?? null) },
      { name: "Recall", type: "line", data: log.map((m: any) => m.recall ?? null) },
      { name: "mAP@50", type: "line", data: log.map((m: any) => m.map50 ?? null) },
      { name: "mAP@50:95", type: "line", data: log.map((m: any) => m.map5095 ?? null) },
    ],
  };
});

const compareTableData = computed(() => [
  { label: "Box Loss", getter: (m: any) => m.box_loss, fmt: (v: number) => v.toFixed(4) },
  { label: "Cls Loss", getter: (m: any) => m.cls_loss, fmt: (v: number) => v.toFixed(4) },
  { label: "Dfl Loss", getter: (m: any) => m.dfl_loss, fmt: (v: number) => v.toFixed(4) },
  { label: "Precision", getter: (m: any) => m.precision, fmt: (v: number) => (v * 100).toFixed(1) + "%" },
  { label: "Recall", getter: (m: any) => m.recall, fmt: (v: number) => (v * 100).toFixed(1) + "%" },
  { label: "mAP@50", getter: (m: any) => m.map50, fmt: (v: number) => (v * 100).toFixed(1) + "%" },
  { label: "mAP@50:95", getter: (m: any) => m.map5095, fmt: (v: number) => (v * 100).toFixed(1) + "%" },
]);

function parseYoloMetrics(line: string) {
  const m = line.match(/\s*(\d+)\/(\d+)\s+/);
  if (m && line.includes("G") && (line.includes("loss") || /\d+\.\d+\s+\d+\.\d+/.test(line))) {
    yoloMetrics.epoch = parseInt(m[1]);
    yoloMetrics.totalEpochs = parseInt(m[2]);
    const g = line.match(/([\d.]+)(G|M)/);
    if (g) yoloMetrics.gpuMem = g[0];
    const parts = line.trim().split(/\s+/);
    const lv = parts.filter(p => /^\d+\.\d+$/.test(p));
    if (lv.length >= 1) yoloMetrics.boxLoss = parseFloat(lv[0]);
    if (lv.length >= 2) yoloMetrics.clsLoss = parseFloat(lv[1]);
    if (lv.length >= 3) yoloMetrics.dflLoss = parseFloat(lv[2]);
    yoloMetrics.progress = Math.round(yoloMetrics.epoch / yoloMetrics.totalEpochs * 100);
    return;
  }
  if (/^\s+all\s+/.test(line)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 5) yoloMetrics.precision = parseFloat(parts[3]) || 0;
    if (parts.length >= 6) yoloMetrics.recall = parseFloat(parts[4]) || 0;
    if (parts.length >= 7) yoloMetrics.map50 = parseFloat(parts[5]) || 0;
    if (parts.length >= 7) yoloMetrics.map5095 = parseFloat(parts[6]) || 0;
    if (yoloMetrics.epoch > 0) {
      liveMetricsLog.value.push({
        epoch: yoloMetrics.epoch, total_epochs: yoloMetrics.totalEpochs,
        box_loss: yoloMetrics.boxLoss, cls_loss: yoloMetrics.clsLoss, dfl_loss: yoloMetrics.dflLoss,
        precision: yoloMetrics.precision, recall: yoloMetrics.recall,
        map50: yoloMetrics.map50, map5095: yoloMetrics.map5095,
      });
    }
  }
}

function parseLogForMetrics(text: string) {
  const lines = text.split("\n");
  let current: any = null;
  const metrics: any[] = [];
  for (const raw of lines) {
    const line = raw.trim();
    const epochMatch = line.match(/^\s*(\d+)\/(\d+)\s+/);
    if (epochMatch && line.includes("G")) {
      current = { epoch: parseInt(epochMatch[1]), total_epochs: parseInt(epochMatch[2]) };
      const parts = line.split(/\s+/);
      const lv = parts.filter(p => /^\d+\.\d+$/.test(p));
      if (lv.length >= 1) current.box_loss = parseFloat(lv[0]);
      if (lv.length >= 2) current.cls_loss = parseFloat(lv[1]);
      if (lv.length >= 3) current.dfl_loss = parseFloat(lv[2]);
      continue;
    }
    if (current && /^all\s+/.test(line)) {
      const parts = line.split(/\s+/);
      if (parts.length >= 5) current.precision = parseFloat(parts[3]) || 0;
      if (parts.length >= 6) current.recall = parseFloat(parts[4]) || 0;
      if (parts.length >= 7) current.map50 = parseFloat(parts[5]) || 0;
      if (parts.length >= 7) current.map5095 = parseFloat(parts[6]) || 0;
      metrics.push({ ...current });
      current = null;
    }
  }
  if (metrics.length) liveMetricsLog.value = metrics;
}

function connectWs(id: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/train/logs?task_id=${id}`);
  wsConnected.value = true;
  ws.onmessage = (e: MessageEvent) => {
    const line = e.data.replace(/[\r\x1b\[[0-9;]*m]/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
    logText.value += line + "\n";
    logLineCount.value++;
    parseYoloMetrics(line);
    if (autoScroll.value) {
      nextTick(() => requestAnimationFrame(() => {
        if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
      }));
    }
  };
  ws.onclose = () => { wsConnected.value = false; };
  ws.onerror = () => { wsConnected.value = false; };
}

function clearLogs() { logText.value = ""; logLineCount.value = 0; }

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
    const prevStatus = task.value?.status;
    await loadTask();
    const curStatus = task.value?.status;
    if (curStatus !== prevStatus) {
      if (curStatus === "running" && !ws) connectWs(Number(route.params.id));
    }
    if (curStatus && curStatus !== "running" && curStatus !== "pending") stopPoll();
  }, 5000);
}

function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

async function handleStart() {
  try {
    await ElMessageBox.confirm(`确定开始训练任务「${task.value?.name}」？`, "提示", { type: "info" });
    await TrainAPI.startTask(task.value.id);
    ElMessage.success("训练已开始");
    await loadTask();
    connectWs(task.value.id);
    startPoll();
  } catch (e: any) {
    if (e !== "cancel") ElMessage.error(e?.msg || "开始训练失败");
  }
}

async function handleStop() {
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(task.value.id);
    ElMessage.success("训练已停止");
    await loadTask();
  } catch { /* */ }
}

function handleEditParams() { ElMessage.info("超参数编辑功能请返回列表页"); router.push("/train/task"); }

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确定删除任务「${task.value?.name}」？`, "提示", { type: "warning", confirmButtonText: "删除" });
    await TrainAPI.deleteTask([task.value.id]);
    ElMessage.success("已删除");
    router.push("/train/task");
  } catch { /* */ }
}

function handleRetrain() { ElMessage.info("重新训练功能需要调度器支持"); }
function handleViewModel() { if (task.value?.model_repo_id) router.push(`/train/repo?model_id=${task.value.model_repo_id}`); else ElMessage.warning("暂无关联模型"); }
function handleEvaluate() { ElMessage.info("评估功能需要后端支持"); }
function handleExport() { ElMessage.info("导出功能需要后端支持"); }

onMounted(async () => {
  await loadTask();
  const id = Number(route.params.id);
  if (id) {
    if (task.value?.status === "running") {
      connectWs(id);
      startPoll();
    } else {
      try {
        const r = await TrainAPI.getTaskLogs(id);
        if (r.data?.data?.logs) {
          const cleaned = r.data.data.logs.replace(/[\r\x1b\[[0-9;]*m]/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
          logText.value = cleaned;
          if (!task.value?.metrics_log) parseLogForMetrics(cleaned);
        }
      } catch { /* */ }
    }
  }
});

onBeforeUnmount(() => { ws?.close(); stopPoll(); });
</script>

<style scoped lang="scss">
.task-detail { padding: 16px; overflow-y: auto; }
.detail-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 16px; padding: 10px 16px;
  background: #fff; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.05);
}
.task-name { font-size: 15px; font-weight: 600; margin-right: 4px; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-text { font-size: 13px; font-weight: 500; color: #e6a23c; margin-left: 4px; }
.info-row, .action-row, .progress-row, .error-row, .metrics-row { margin-bottom: 16px; }
.info-card { height: 100%; }
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.docker-tag { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 12px; background: #f5f7fa; padding: 2px 6px; border-radius: 3px; }
.action-buttons { display: flex; gap: 10px; }
.progress-wrapper { display: flex; align-items: center; gap: 16px; }
.progress-bar-area { flex: 1; }
.progress-indicator { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.pulse-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #e6a23c; animation: pulse-anim 1.2s ease-in-out infinite; }
@keyframes pulse-anim { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .5; transform: scale(1.3); } }
.eta-text { font-size: 13px; color: #909399; }
.log-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.log-controls { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #909399; }
.log-status { display: inline-flex; align-items: center; gap: 4px; color: #909399;
  &::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #909399; }
  &.connected { color: #67c23a; &::before { background: #67c23a; } }
}
.log-line-count { font-family: "Cascadia Code", "Fira Code", monospace; }
.log-container { height: 500px; overflow-y: auto; background: #1e1e1e !important; border-radius: 6px; padding: 16px; min-height: 200px; }
.log-text { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
.metric-mini { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 12px 8px; text-align: center; }
.metric-val { display: block; font-size: 16px; font-weight: 700; font-family: "Cascadia Code", monospace; color: var(--el-text-color-primary); }
.metric-lbl { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin-top: 4px; }
.metric-green { color: #67c23a; }
.metric-blue { color: #409eff; }
.metric-orange { color: #e6a23c; }
.metric-purple { color: #9b59b6; }
.text-muted { color: #c0c4cc; }
.mono { font-family: "Cascadia Code", "Fira Code", monospace; }
.chart-placeholder { height: 300px; display: flex; align-items: center; justify-content: center; color: #c0c4cc; font-size: 14px; }
</style>
