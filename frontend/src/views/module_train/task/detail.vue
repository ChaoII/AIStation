<template>
  <div>
    <div class="train-detail-page">
      <div class="detail-header">
      <el-button text size="small" @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="task-name">{{ task?.name }}</span>
      <el-tag
        :type="(task?.framework === 'ultralytics' ? 'success' : 'primary') as any"
        size="small"
        effect="plain"
      >
        {{ frameworkLabel(task?.framework) }}
      </el-tag>
      <el-tag
        :type="statusTag(task?.status || '') as any"
        size="small"
        :effect="task?.status === 'running' ? 'dark' : 'plain'"
      >
        {{ statusLabel(task?.status || "") }}
      </el-tag>
      <span v-if="displayProgress > 0" class="progress-text">{{ displayProgress }}%</span>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">任务信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="数据集 ID">{{ task?.dataset_id }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ task?.created_time }}</el-descriptions-item>
            <el-descriptions-item label="Docker 镜像">
              <code class="docker-tag">{{ task?.docker_image }}</code>
            </el-descriptions-item>
            <el-descriptions-item label="Docker 命令">
              <pre
                style="
                  margin: 0;
                  font-size: 11px;
                  line-height: 1.4;
                  background: #f5f7fa;
                  padding: 6px 8px;
                  border-radius: 4px;
                  white-space: pre-wrap;
                  word-break: break-all;
                  max-width: 500px;
                "
                >{{ dockerCmd || "—" }}</pre>
            </el-descriptions-item>
            <el-descriptions-item label="创建者 ID">{{ task?.created_id }}</el-descriptions-item>
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
      <el-col :xs="24" :md="12">
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
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">操作</span></template>
      <div class="action-buttons">
        <template v-if="task?.status === 'pending'">
          <el-button type="primary" size="default" @click="handleStart">开始训练</el-button>
          <el-button size="default" @click="handleEditParams">编辑参数</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="task?.status === 'running'">
          <el-button type="danger" size="default" @click="handleStop">停止训练</el-button>
        </template>
        <template v-else-if="task?.status === 'success'">
          <el-button type="primary" size="default" @click="handleViewModel">查看模型</el-button>
          <el-button size="default" @click="handleEvaluate">评估模型</el-button>
          <el-button size="default" @click="handleExport">导出模型</el-button>
          <el-button size="default" @click="handleRetrain">重新训练</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="task?.status === 'failed'">
          <el-button type="primary" size="default" @click="handleRetrain">重新训练</el-button>
          <el-button size="default" @click="scrollToLog">查看日志</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="task?.status === 'cancelled'">
          <el-button type="primary" size="default" @click="handleRetrain">重新训练</el-button>
        </template>
      </div>
    </el-card>

    <el-card v-if="displayProgress > 0" shadow="never" class="section-card">
      <template #header><span class="card-title">训练进度</span></template>
      <el-progress
        :percentage="displayProgress"
        :stroke-width="20"
        :text-inside="true"
        :status="
          task?.status === 'success'
            ? 'success'
            : task?.status === 'failed'
              ? 'exception'
              : 'warning'
        "
      />
      <div v-if="task?.status === 'running'" class="progress-eta">
        <span class="pulse-dot" />
        训练中，预计剩余 {{ estimatedEta }}
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">训练指标</span></template>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12" :md="6">
          <div class="metric-item">
            <el-icon :size="22" style="color: #909399; margin-bottom: 4px"><Clock /></el-icon>
            <span class="metric-val">{{ displayMetrics.epoch }}</span>
            <span class="metric-lbl">Epoch</span>
          </div>
        </el-col>
        <!-- 损失卡片：按框架选择（PaddleX 单一 Loss / YOLO box-cls-dfl） -->
        <el-col v-for="s in lossSpec" :key="s.key" :xs="24" :sm="12" :md="6">
          <div class="metric-item">
            <el-icon :size="22" :style="{ color: s.color, marginBottom: '4px' }">
              <component :is="s.icon" />
            </el-icon>
            <span class="metric-val">{{ displayMetrics[s.key] }}</span>
            <span class="metric-lbl">{{ s.label }}</span>
          </div>
        </el-col>
        <!-- 主指标卡片：按框架选择（PaddleX hmean/acc、YOLO mAP/PR、分类 top1/top5） -->
        <el-col v-for="s in metricSpec" :key="s.key" :xs="24" :sm="12" :md="6">
          <div class="metric-item">
            <el-icon :size="22" :style="{ color: s.color, marginBottom: '4px' }">
              <component :is="s.icon" />
            </el-icon>
            <span class="metric-val" :style="{ color: s.color }">{{ displayMetrics[s.key] }}</span>
            <span class="metric-lbl">{{ s.label }}</span>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-alert
      v-if="task?.error_log"
      title="训练失败"
      type="error"
      :description="task.error_log.slice(0, 500)"
      show-icon
      closable
      style="margin-bottom: 16px"
    />

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">Loss 趋势</span></template>
          <VChart
            v-if="displayMetricsLog.length > 0"
            :option="lossChartOption"
            style="height: 280px"
            autoresize
          />
          <div v-else class="chart-empty">等待训练数据...</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">验证指标趋势</span></template>
          <VChart
            v-if="displayMetricsLog.length > 0"
            :option="valChartOption"
            style="height: 280px"
            autoresize
          />
          <div v-else class="chart-empty">等待训练数据...</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="displayBestMetrics || displayLastMetrics" shadow="never" class="section-card">
      <template #header><span class="card-title">指标对比</span></template>
      <el-table :data="compareTableData" border size="small" style="width: 100%">
        <el-table-column prop="label" label="指标" width="140" />
        <el-table-column label="最优 Epoch">
          <template #default="{ row }">
            <span v-if="displayBestMetrics && row.getter(displayBestMetrics) != null" class="mono">
              {{ row.fmt(row.getter(displayBestMetrics)) }}
            </span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="最终 Epoch">
          <template #default="{ row }">
            <span v-if="displayLastMetrics && row.getter(displayLastMetrics) != null" class="mono">
              {{ row.fmt(row.getter(displayLastMetrics)) }}
            </span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
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

    <el-card
      v-if="task?.status === 'success' && task?.model_repo_id"
      shadow="never"
      class="section-card"
    >
      <template #header><span class="card-title">模型输出</span></template>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="模型仓库 ID">
          <el-tag size="small">{{ task.model_repo_id }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 12px">
        <el-button type="primary" size="default" @click="handleViewModel">查看模型</el-button>
        <el-button size="default" @click="handleExport">导出模型</el-button>
        <el-button size="default" @click="handleEvaluate">评估模型</el-button>
      </div>
    </el-card>
  </div>

  <ModelExportDialog
    v-model:visible="exportDialogVisible"
    :model-id="task?.model_repo_id || 0"
    :model-name="task?.name"
    @done="loadTask"
  />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowLeft,
  Clock,
  TrendCharts,
  DataBoard,
  DataAnalysis,
  Aim,
  Search,
  StarFilled,
  TrophyBase,
} from "@element-plus/icons-vue";
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
const submitting = ref(false);
let ws: WebSocket | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

function statusTag(s: string) {
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
function statusLabel(s: string) {
  return (
    (
      {
        pending: "待开始",
        running: "训练中",
        success: "已完成",
        failed: "失败",
        cancelled: "已取消",
      } as any
    )[s] || s
  );
}

function frameworkLabel(fw?: string) {
  return (
    {
      ultralytics: "Ultralytics",
      paddlex: "PaddleX",
    } as any
  )[fw || ""] || fw || "—";
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

const tempDir = ref("${TEMP_DIR}");
TrainAPI.getTempDir()
  .then((res) => {
    if (res?.data?.data?.tempdir) tempDir.value = res.data.data.tempdir;
  })
  .catch(() => {});

const dockerCmd = computed(() => {
  if (!task.value?.id) return "";
  const dataDir = `${tempDir.value}/train_output/${task.value.id}`;
  const cacheDir = `${tempDir.value}/train_output/.models_cache`;
  const hp = task.value?.hyperparams || {};
  if (task.value?.framework === "ultralytics") {
    return `docker run --gpus all \\\n  -v ${dataDir}/data:/data \\\n  -v ${dataDir}:/output \\\n  -v ${cacheDir}:/models \\\n  ${task.value.docker_image} \\\n  yolo train \\\n    model=/models/${hp.model || ""} \\\n    data=/data/dataset.yaml \\\n    epochs=${hp.epochs || 100} \\\n    batch=${hp.batch || 16} \\\n    ...`;
  }
  if (task.value?.framework === "paddlex") {
    return `docker run --gpus all \\\n  -v ${dataDir}/data:/data \\\n  -v ${dataDir}:/output \\\n  ${task.value.docker_image} \\\n  paddlex \\\n    --model ${hp.model || ""} \\\n    --data /data \\\n    --epochs ${hp.epochs || 100} \\\n    --batch ${hp.batch || 16} \\\n    ...`;
  }
  return "";
});

const displayProgress = computed(() => {
  if (yoloMetrics.epoch > 0 && yoloMetrics.totalEpochs > 0)
    return Math.round((yoloMetrics.epoch / yoloMetrics.totalEpochs) * 100);
  return task.value?.progress || 0;
});

const estimatedEta = computed(() => {
  const p = displayProgress.value;
  if (p <= 0) return "计算中...";
  if (p >= 100) return "即将完成";
  const elapsed = task.value?.started_at
    ? (Date.now() - new Date(task.value.started_at).getTime()) / 1000
    : 0;
  if (elapsed <= 0) return "计算中...";
  const remaining = Math.max(0, (elapsed / p) * 100 - elapsed);
  if (remaining < 60) return `${Math.round(remaining)}秒`;
  if (remaining < 3600) return `${Math.floor(remaining / 60)}分${Math.round(remaining % 60)}秒`;
  return `${Math.floor(remaining / 3600)}时${Math.floor((remaining % 3600) / 60)}分`;
});

const yoloMetrics = reactive({
  epoch: 0,
  totalEpochs: 0,
  boxLoss: 0,
  clsLoss: 0,
  dflLoss: 0,
  // PaddleX 单一 loss 与主指标
  loss: 0,
  hmean: 0,
  acc: 0,
  precision: 0,
  recall: 0,
  map50: 0,
  map5095: 0,
  gpuMem: "",
  progress: 0,
});

const liveMetricsLog = ref<any[]>([]);

// 框架感知：PaddleX 以 hmean(det)/acc(rec) 为主指标，其余框架为 map50
const isPaddlex = computed(() => String(task.value?.framework || "").toLowerCase() === "paddlex");
const paddlexMode = computed(() => String(task.value?.hyperparams?.mode || "det").toLowerCase());
const livePrimaryKey = computed(() =>
  isPaddlex.value ? (paddlexMode.value === "rec" ? "acc" : "hmean") : "map50"
);

const liveBestMetrics = computed(() => {
  const key = livePrimaryKey.value;
  const v = liveMetricsLog.value.filter((m: any) => m[key] != null);
  if (v.length) return v.reduce((b: any, m: any) => (m[key] > (b[key] ?? 0) ? m : b), v[0]);
  return liveMetricsLog.value.length ? liveMetricsLog.value[liveMetricsLog.value.length - 1] : null;
});
const liveLastMetrics = computed(() =>
  liveMetricsLog.value.length ? liveMetricsLog.value[liveMetricsLog.value.length - 1] : null
);
const metricsLog = computed<any[]>(() => task.value?.metrics_log || []);
const bestMetrics = computed<any>(() => task.value?.best_metrics || null);
const lastMetrics = computed<any>(() => task.value?.last_metrics || null);
const displayMetricsLog = computed<any[]>(() =>
  liveMetricsLog.value.length ? liveMetricsLog.value : metricsLog.value
);
const displayBestMetrics = computed<any>(() => liveBestMetrics.value || bestMetrics.value);
const displayLastMetrics = computed<any>(() => liveLastMetrics.value || lastMetrics.value);

// 分类任务：TrainTask 未直接持久化 task_type，优先看超参，其次依据指标键（top1/top5）推断
const isClassifyTask = computed(() => {
  const hp = task.value?.hyperparams || {};
  const tt = String(hp.task_type || hp.task || "").toLowerCase();
  if (tt === "cls" || tt === "classification") return true;
  const probes = [displayBestMetrics.value, displayLastMetrics.value];
  if (probes.some((m: any) => m && (m.top1 != null || m.top5 != null))) return true;
  return displayMetricsLog.value.some((m: any) => m && (m.top1 != null || m.top5 != null));
});

interface MetricItem {
  key: string;
  label: string;
  color: string;
  icon: any;
}

// 主指标定义：PaddleX det→HMean/Precision/Recall；PaddleX rec→Acc；
// YOLO 分类→Top1/Top5；其余（det/seg/obb/pose）→mAP@50/mAP@50:95/Precision/Recall
const metricSpec = computed<MetricItem[]>(() => {
  if (isPaddlex.value) {
    return paddlexMode.value === "rec"
      ? [{ key: "acc", label: "Acc", color: "#409eff", icon: Aim }]
      : [
          { key: "hmean", label: "HMean", color: "#52c41a", icon: StarFilled },
          { key: "precision", label: "Precision", color: "#409eff", icon: Aim },
          { key: "recall", label: "Recall", color: "#fa8c16", icon: Search },
        ];
  }
  if (isClassifyTask.value) {
    return [
      { key: "top1", label: "Top1", color: "#52c41a", icon: Aim },
      { key: "top5", label: "Top5", color: "#409eff", icon: StarFilled },
    ];
  }
  return [
    { key: "map50", label: "mAP@50", color: "#fa8c16", icon: StarFilled },
    { key: "map5095", label: "mAP@50:95", color: "#9b59b6", icon: TrophyBase },
    { key: "precision", label: "Precision", color: "#52c41a", icon: Aim },
    { key: "recall", label: "Recall", color: "#409eff", icon: Search },
  ];
});

// Loss 定义：PaddleX 只有单一 loss；YOLO 检测族保留 box/cls/dfl；分类为单一 Loss
const lossSpec = computed<{ key: string; src: string; label: string; color: string; icon: any }[]>(
  () => {
    if (isPaddlex.value) {
      return [{ key: "loss", src: "loss", label: "Loss", color: "#f56c6c", icon: TrendCharts }];
    }
    if (isClassifyTask.value) {
      // Ultralytics 分类日志的 loss 仅一项，后端解析落在首列 box_loss 上
      return [{ key: "loss", src: "box_loss", label: "Loss", color: "#f56c6c", icon: TrendCharts }];
    }
    return [
      { key: "boxLoss", src: "box_loss", label: "Box Loss", color: "#f56c6c", icon: TrendCharts },
      { key: "clsLoss", src: "cls_loss", label: "Cls Loss", color: "#e6a23c", icon: DataBoard },
      { key: "dflLoss", src: "dfl_loss", label: "Dfl Loss", color: "#409eff", icon: DataAnalysis },
    ];
  }
);

// 0-1 比例指标 → 百分比；loss → 保留 4 位小数
function fmtRatio(v: any): string {
  return v != null && !isNaN(Number(v)) ? (Number(v) * 100).toFixed(1) + "%" : "—";
}
function fmtDecimal(v: any): string {
  return v != null && !isNaN(Number(v)) ? Number(v).toFixed(4) : "—";
}

// 运行中实时值（来自 WS 解析）；否则取最终一轮（last_metrics）
const liveMetricsActive = computed(
  () => task.value?.status === "running" && yoloMetrics.epoch > 0
);

function liveMetricValue(key: string): any {
  return (yoloMetrics as any)[key];
}
function liveLossValue(src: string): any {
  const map: Record<string, any> = {
    box_loss: yoloMetrics.boxLoss,
    cls_loss: yoloMetrics.clsLoss,
    dfl_loss: yoloMetrics.dflLoss,
    loss: yoloMetrics.loss,
  };
  return map[src];
}

const displayMetrics = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {};
  const last = displayLastMetrics.value;
  if (liveMetricsActive.value) {
    out.epoch = `${yoloMetrics.epoch}/${yoloMetrics.totalEpochs}`;
    for (const s of metricSpec.value) out[s.key] = fmtRatio(liveMetricValue(s.key));
    for (const s of lossSpec.value) out[s.key] = fmtDecimal(liveLossValue(s.src));
    return out;
  }
  out.epoch = last?.epoch != null ? `${last.epoch}/${last.total_epochs ?? "?"}` : "—";
  for (const s of metricSpec.value) out[s.key] = fmtRatio(last?.[s.key]);
  for (const s of lossSpec.value) out[s.key] = fmtDecimal(last?.[s.src]);
  return out;
});

const lossChartOption = computed(() => {
  const log = displayMetricsLog.value;
  if (!log.length) return {};
  const spec = lossSpec.value;
  return {
    tooltip: { trigger: "axis" },
    legend: { data: spec.map((s) => s.label), top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: log.map((m: any) => m.epoch), name: "Epoch" },
    yAxis: { type: "value", name: "Loss" },
    series: spec.map((s) => ({
      name: s.label,
      type: "line",
      data: log.map((m: any) => m[s.src] ?? null),
    })),
  };
});

const valChartOption = computed(() => {
  const spec = metricSpec.value;
  const log = displayMetricsLog.value;
  if (!log.length) return {};
  const usable = log.filter((m: any) => spec.some((s) => m[s.key] != null));
  if (!usable.length) return {};
  return {
    tooltip: { trigger: "axis" },
    legend: { data: spec.map((s) => s.label), top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category", data: usable.map((m: any) => m.epoch), name: "Epoch" },
    yAxis: { type: "value", name: "Metric" },
    series: spec.map((s) => ({
      name: s.label,
      type: "line",
      data: usable.map((m: any) => m[s.key] ?? null),
    })),
  };
});

const compareTableData = computed(() => [
  ...lossSpec.value.map((s) => ({
    label: s.label,
    getter: (m: any) => m?.[s.src],
    fmt: (v: number) => Number(v).toFixed(4),
  })),
  ...metricSpec.value.map((s) => ({
    label: s.label,
    getter: (m: any) => m?.[s.key],
    fmt: (v: number) => (Number(v) * 100).toFixed(1) + "%",
  })),
]);

function pushLiveMetrics() {
  if (yoloMetrics.epoch > 0) {
    liveMetricsLog.value.push({
      epoch: yoloMetrics.epoch,
      total_epochs: yoloMetrics.totalEpochs,
      box_loss: yoloMetrics.boxLoss,
      cls_loss: yoloMetrics.clsLoss,
      dfl_loss: yoloMetrics.dflLoss,
      loss: yoloMetrics.loss,
      precision: yoloMetrics.precision,
      recall: yoloMetrics.recall,
      map50: yoloMetrics.map50,
      map5095: yoloMetrics.map5095,
      hmean: yoloMetrics.hmean,
      acc: yoloMetrics.acc,
    });
  }
}
function parseYoloMetrics(line: string) {
  // PaddleX: `epoch: [1/100], ... hmean/acc/loss`
  const pe = line.match(/epoch:\s*\[(\d+)\/(\d+)\]/);
  if (pe) {
    yoloMetrics.epoch = parseInt(pe[1]);
    yoloMetrics.totalEpochs = parseInt(pe[2]);
    yoloMetrics.progress = Math.round((yoloMetrics.epoch / yoloMetrics.totalEpochs) * 100);
    const hm = line.match(/hmean:\s*([\d.]+)/);
    if (hm) yoloMetrics.hmean = parseFloat(hm[1]);
    const ca = line.match(/acc:\s*([\d.]+)/);
    if (ca) yoloMetrics.acc = parseFloat(ca[1]);
    const lo = line.match(/loss:\s*([\d.]+)/);
    if (lo) yoloMetrics.loss = parseFloat(lo[1]);
    const pr = line.match(/precision:\s*([\d.]+)/);
    if (pr) yoloMetrics.precision = parseFloat(pr[1]);
    const rc = line.match(/recall:\s*([\d.]+)/);
    if (rc) yoloMetrics.recall = parseFloat(rc[1]);
    pushLiveMetrics();
    return;
  }
  // PaddleX det / rec eval 行
  const eh = line.match(/eval hmean\s+([\d.]+)/);
  if (eh) {
    yoloMetrics.hmean = parseFloat(eh[1]);
    pushLiveMetrics();
    return;
  }
  const ec = line.match(/eval char_acc\s+([\d.]+)/);
  if (ec) {
    yoloMetrics.acc = parseFloat(ec[1]);
    pushLiveMetrics();
    return;
  }
  const m = line.match(/\s*(\d+)\/(\d+)\s+/);
  if (m && line.includes("G") && (line.includes("loss") || /\d+\.\d+\s+\d+\.\d+/.test(line))) {
    yoloMetrics.epoch = parseInt(m[1]);
    yoloMetrics.totalEpochs = parseInt(m[2]);
    const g = line.match(/([\d.]+)(G|M)/);
    if (g) yoloMetrics.gpuMem = g[0];
    const parts = line.trim().split(/\s+/);
    const lv = parts.filter((p) => /^\d+\.\d+$/.test(p));
    if (lv.length >= 1) yoloMetrics.boxLoss = parseFloat(lv[0]);
    if (lv.length >= 2) yoloMetrics.clsLoss = parseFloat(lv[1]);
    if (lv.length >= 3) yoloMetrics.dflLoss = parseFloat(lv[2]);
    yoloMetrics.progress = Math.round((yoloMetrics.epoch / yoloMetrics.totalEpochs) * 100);
    return;
  }
  if (/^\s+all\s+/.test(line)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 5) yoloMetrics.precision = parseFloat(parts[3]) || 0;
    if (parts.length >= 6) yoloMetrics.recall = parseFloat(parts[4]) || 0;
    if (parts.length >= 7) yoloMetrics.map50 = parseFloat(parts[5]) || 0;
    if (parts.length >= 7) yoloMetrics.map5095 = parseFloat(parts[6]) || 0;
    pushLiveMetrics();
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
      const lv = parts.filter((p) => /^\d+\.\d+$/.test(p));
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
    const line = e.data.replace(/\r/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
    logText.value += line + "\n";
    logLineCount.value++;
    parseYoloMetrics(line);
    if (autoScroll.value)
      nextTick(() =>
        requestAnimationFrame(() => {
          if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
        })
      );
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
    const el = document.querySelector(".log-container");
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

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function handleStart() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定开始训练任务「${task.value?.name}」？`, "提示", {
      type: "info",
    });
    await TrainAPI.startTask(task.value.id);
    await loadTask();
    connectWs(task.value.id);
    startPoll();
  } catch {
    /* 提示由请求拦截器统一处理 */
  } finally {
    submitting.value = false;
  }
}

async function handleStop() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(task.value.id);
    await loadTask();
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

function handleEditParams() {
  router.push(`/train/task?edit_id=${task.value?.id}`);
}

async function handleDelete() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定删除任务「${task.value?.name}」？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
    });
    await TrainAPI.deleteTask([task.value.id]);
    router.push("/train/task");
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

async function handleRetrain() {
  if (submitting.value) return;
  submitting.value = true;
  if (!task.value) {
    submitting.value = false;
    return;
  }
  try {
    await ElMessageBox.confirm(
      `重新训练任务「${task.value.name}」？将清除之前的训练结果。`,
      "重新训练",
      { type: "warning", confirmButtonText: "确定重新训练" }
    );
    stopPoll();
    if (ws) {
      ws.close();
      ws = null;
    }
    clearLogs();
    liveMetricsLog.value = [];
    Object.assign(yoloMetrics, {
      epoch: 0,
      totalEpochs: 0,
      boxLoss: 0,
      clsLoss: 0,
      dflLoss: 0,
      loss: 0,
      hmean: 0,
      acc: 0,
      precision: 0,
      recall: 0,
      map50: 0,
      map5095: 0,
      gpuMem: "",
      progress: 0,
    });
    await TrainAPI.startTask(task.value.id);
    await loadTask();
    connectWs(task.value.id);
    startPoll();
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

function handleViewModel() {
  if (task.value?.model_repo_id) router.push(`/train/repo?model_id=${task.value.model_repo_id}`);
  else ElMessage.warning("暂无关联模型");
}

function handleEvaluate() {
  ElMessage.info("评估功能需要后端支持");
}

const exportDialogVisible = ref(false);

function handleExport() {
  if (!task.value?.model_repo_id) {
    ElMessage.warning("暂无关联模型，请先完成训练");
    return;
  }
  // 先验证模型是否存在
  TrainAPI.getModelDetail(task.value.model_repo_id).then(res => {
    if (res.data?.data) {
      exportDialogVisible.value = true;
    } else {
      ElMessage.error("关联模型已不存在，请重新训练");
    }
  }).catch(() => {
    ElMessage.error("关联模型已不存在，请重新训练");
  });
}

onMounted(async () => {
  await loadTask();
  const id = Number(route.params.id);
  if (id) {
    try {
      const r = await TrainAPI.getTaskLogs(id);
      if (r.data?.data?.logs) {
        const cleaned = r.data.data.logs
          .replace(/\r/g, "")
          .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
        logText.value = cleaned;
        if (!task.value?.metrics_log) parseLogForMetrics(cleaned);
      }
    } catch {
      /* */
    }
    if (task.value?.status === "running") {
      connectWs(id);
      startPoll();
    }
  }
});

onBeforeUnmount(() => {
  ws?.close();
  stopPoll();
});
</script>
