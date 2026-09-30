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
            <el-descriptions-item label="数据集">{{
              task?.dataset_name || `#${task?.dataset_id}`
            }}</el-descriptions-item>
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
        <el-table-column label="最优值">
          <template #default="{ row }">
            <span v-if="displayBestMetrics && row.getter(displayBestMetrics) != null" class="mono">
              {{ row.fmt(row.getter(displayBestMetrics)) }}
            </span>
            <span v-else class="text-muted">—</span>
            <span v-if="displayBestMetrics?.epoch" class="text-muted sub-epoch">
              epoch {{ displayBestMetrics.epoch }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最终值">
          <template #default="{ row }">
            <span v-if="displayLastMetrics && row.getter(displayLastMetrics) != null" class="mono">
              {{ row.fmt(row.getter(displayLastMetrics)) }}
            </span>
            <span v-else class="text-muted">—</span>
            <span v-if="displayLastMetrics?.epoch" class="text-muted sub-epoch">
              epoch {{ displayLastMetrics.epoch }}
            </span>
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
import { ref, computed, reactive, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowLeft,
  Clock,
  TrendCharts,
  DataBoard,
  DataAnalysis,
} from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";
import { resolveMainMetricSpec, type MetricSpecItem } from "@/utils/trainMetrics";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const route = useRoute();
const router = useRouter();
const task = ref<any>(null);
/**
 * 训练日志缓冲。
 *
 * ⚠️ 原实现是**单个响应式字符串** `logText.value += line + "\n"`：每次追加都要
 * 生成一个新的大字符串并整体替换（响应式代理还要再拷一份），随后整个字符串被
 * `<pre>{{ logText }}</pre>` 全量重渲染。跑到几万行就是几十 MB 级字符串反复重建，
 * 页面直接卡死。
 *
 * 改为「固定容量环形缓冲 + 批量 flush」：
 * 1. 收到的行先 push 进**普通数组**（非响应式），不逐行触发渲染；
 * 2. 每 200ms 或每 200 行 flush 一次，拼成字符串赋给 ref → 每 200ms 只渲染一次；
 * 3. 只保留最近 ``LOG_MAX_LINES`` 行，超出从头丢，并保持自动滚动到底部。
 */
const LOG_MAX_LINES = 3000;
const LOG_FLUSH_LINES = 200;
const LOG_FLUSH_MS = 200;
const logBuf: string[] = [];
let logFlushTimer: ReturnType<typeof setTimeout> | null = null;
let logDropped = 0;
const logRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const wsConnected = ref(false);
const logText = ref("");
const logLineCount = ref(0);

function flushLog() {
  logFlushTimer = null;
  if (!logBuf.length) return;
  logText.value = logBuf.join("\n");
  logLineCount.value = logDropped + logBuf.length;
  if (autoScroll.value) {
    // 等 DOM 更新后再滚到底
    void nextTick(() => {
      const el = logRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
  if (logFlushTimer) clearTimeout(logFlushTimer);
  logFlushTimer = setTimeout(flushLog, LOG_FLUSH_MS);
}

function pushLogLine(line: string) {
  logBuf.push(line);
  if (logBuf.length > LOG_MAX_LINES) {
    const drop = logBuf.length - LOG_MAX_LINES;
    logBuf.splice(0, drop);
    logDropped += drop;
  }
  if (logBuf.length >= LOG_FLUSH_LINES) {
    if (logFlushTimer) clearTimeout(logFlushTimer);
    logFlushTimer = setTimeout(flushLog, 0);
  }
}

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
      torchkiln: "TorchKiln",
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
  // YOLO 分类主指标
  top1: 0,
  top5: 0,
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
const livePrimaryKey = computed(() => {
  if (isPaddlex.value) return paddlexMode.value === "rec" ? "acc" : "hmean";
  // ⚠️ TorchKiln 的主指标**随任务变**（mAP50-95 / mAP50 / acc / hmean / RMSE…），
  //    且行里的键是 `mAP50-95` 这种带连字符的名字，不是硬编码的 `map50`。
  //    这里沿用旧写死的 "map50" 会**永远取不到任何一行**，于是 bestOf 走
  //    「取最后一行」兜底，把 `end` 簿记行当成最优值（epoch 显示成最后一轮）。
  if (isTorchkiln.value) return tkMainIndicator.value;
  return "map50";
});

/** 簿记行（`end` / `start`）本身不含指标值，不能参与「最优/最终」的评选。 */
function isMetricRow(r: any): boolean {
  return !!r && r._kind !== "end";
}

/**
 * 取该 key 的历史最优行。
 *
 * ⚠️ 原实现是 `filter(...).reduce(...)`：每来一个 step 事件就**分配一个
 * N 长度的临时数组 + 全量遍历**一遍（N = 指标行数，上限 5000）。指标一多，
 * 每次 push 都要重扫全表，是页面卡顿的主要来源之一。
 * 改成单趟循环、不分配中间数组，行为完全一致。
 *
 * ⚠️ 两处语义修正：
 *   1. 跳过 `end` 行 —— 它是「训练结束」的簿记，epoch 是最后一轮、但可能没有指标值；
 *      混进来会把最优 epoch 错报成最后一轮。
 *   2. 找不到候选时返回 **null**（交给 task.best_metrics 兜底），而不是「取最后一行」。
 *      旧兜底正是上面「最优值显示成最后一轮」的直接原因。
 *   3. 指标方向：TorchKiln 的 eval/best 行带 `main_indicator_mode`（RMSE/loss 要取最小值），
 *      有就用；没有的框架（YOLO/PaddleX）行为与以前完全一致，仍是取最大值。
 */
function bestOf(log: any[], key: string): any | null {
  let best: any = null;
  let bestV = 0;
  let has = false;
  let mode = "max";
  for (let i = 0; i < log.length; i++) {
    const row = log[i];
    if (!isMetricRow(row)) continue;
    const v = row?.[key];
    if (v == null) continue;
    if (row.main_indicator_mode) mode = String(row.main_indicator_mode).toLowerCase();
    if (!has) {
      best = row;
      bestV = v;
      has = true;
      continue;
    }
    const better = mode === "min" ? v < bestV : v > bestV;
    if (better) {
      best = row;
      bestV = v;
    }
  }
  if (best) return best;
  return null;
}

const liveBestMetrics = computed(() => bestOf(liveMetricsLog.value, livePrimaryKey.value));
/**
 * 「最终值」：优先取最后一条 **eval** 行（与 task.last_metrics 的语义一致——
 * eval 才是「某轮跑完的验证结果」），没有 eval 就退回最后一条指标行。
 *
 * ⚠️ 不能直接取数组末元素：末尾常是 `end` 簿记行，它有 `epoch`/`main_value`，
 * 但没有 `mAP50-95` 这类摊平的指标键、也没有 `total_epochs`，
 * 卡片会因此显示成「—」和「50/?」。
 * （YOLO/PaddleX 的行没有 `_kind`，`isMetricRow` 视为指标行，行为与旧版一致。）
 */
const liveLastMetrics = computed(() => {
  const log = liveMetricsLog.value;
  let fallback: any = null;
  for (let i = log.length - 1; i >= 0; i--) {
    const row = log[i];
    if (!isMetricRow(row)) continue;
    if (row._kind === "eval") return row;
    if (!fallback) fallback = row;
  }
  return fallback;
});
const metricsLog = computed<any[]>(() => task.value?.metrics_log || []);
const bestMetrics = computed<any>(() => task.value?.best_metrics || null);
const lastMetrics = computed<any>(() => task.value?.last_metrics || null);
const displayMetricsLog = computed<any[]>(() =>
  liveMetricsLog.value.length ? liveMetricsLog.value : metricsLog.value
);
const displayBestMetrics = computed<any>(() => liveBestMetrics.value || bestMetrics.value);
const displayLastMetrics = computed<any>(() => liveLastMetrics.value || lastMetrics.value);

// 分类任务：TrainTask 未直接持久化 task_type。
// 真实信号：Ultralytics 分类权重的 model 以 -cls 结尾；兜底依据指标键（top1/top5）推断。
const isClassifyTask = computed(() => {
  const model = String(task.value?.hyperparams?.model || "").toLowerCase();
  if (/-cls(\.|$)/.test(model)) return true;
  const probes = [displayBestMetrics.value, displayLastMetrics.value];
  if (probes.some((m: any) => m && (m.top1 != null || m.top5 != null))) return true;
  return displayMetricsLog.value.some((m: any) => m && (m.top1 != null || m.top5 != null));
});

// TorchKiln（自研平台）：主指标**由训练侧声明**（mAP50-95 / acc / hmean / RMSE…），
// 随任务变化，所以这里从指标事件里动态读，而不是像第三方那样为每个框架硬编码一张表。
// 后端已把 eval 事件的 metrics 子对象摊平到行顶层，故按 main_indicator 取值即可。
const isTorchkiln = computed(
  () => String(task.value?.framework || "").toLowerCase() === "torchkiln"
);
/** TorchKiln 主指标名：取自任意一条带 main_indicator 的行 */
const tkMainIndicator = computed(() => {
  // ⚠️ 原实现 `[...displayMetricsLog.value, best, last]` 每次求值都**浅拷贝一份
  //    完整数组**（上限 5000 行）。它被 metricSpec / compareTableData /
  //    tkMainIsRatio 依赖，等于每来一个 step 事件就多一次全量拷贝。
  //    直接按优先级顺序单趟扫描，语义不变、零分配。
  const b = displayBestMetrics.value;
  if (b?.main_indicator) return String(b.main_indicator);
  const l = displayLastMetrics.value;
  if (l?.main_indicator) return String(l.main_indicator);
  const log = displayMetricsLog.value;
  for (let i = 0; i < log.length; i++) {
    const mi = log[i]?.main_indicator;
    if (mi) return String(mi);
  }
  return "";
});
/** TorchKiln 主指标是 0~1 比例还是任意数值（loss/RMSE 之类要按小数展示） */
const tkMainIsRatio = computed(() => {
  const k = tkMainIndicator.value.toLowerCase();
  if (!k) return true;
  return /map|acc|precision|recall|hmean|iou|ap|f1|acc/.test(k) && !/rmse|mae|loss|error/.test(k);
});

// 主指标定义：PaddleX det→HMean/Precision/Recall；PaddleX rec→Acc；
// YOLO 分类→Top1/Top5；其余（det/seg/obb/pose）→mAP@50/mAP@50:95/Precision/Recall
// 复用 @/utils/trainMetrics，与评估详情保持一致
const metricSpec = computed<MetricSpecItem[]>(() => {
  if (isTorchkiln.value) {
    const k = tkMainIndicator.value;
    if (!k) return [];
    return [{ key: k, label: k, color: "#67c23a" } as MetricSpecItem];
  }
  return resolveMainMetricSpec({
    framework: task.value?.framework,
    mode: paddlexMode.value,
    classify: isClassifyTask.value,
  });
});

// Loss 定义：PaddleX 只有单一 loss；YOLO 检测族保留 box/cls/dfl；分类为单一 Loss
const lossSpec = computed<{ key: string; src: string; label: string; color: string; icon: any }[]>(
  () => {
    if (isTorchkiln.value) {
      // TorchKiln 的 step 事件把各 loss 分量摊平在行顶层（loss_cls/loss_box/…），
      // 名称随模型而变，故从数据里反查有哪些分量，而不是硬编码。
      //
      // ⚠️ 性能：`for (const m of log)` 会对 Vue 的 reactive proxy 做**迭代器**枚举，
      //    再 `Object.keys(m)` 又是一遍属性枚举 —— 5000 行 × ~12 键 ≈ 6 万次字符串
      //    比较，且每次都发生在 proxy 上（比普通对象慢一个量级）。
      //    实测过的写法：把已知的 loss_* 键**缓存**下来，只在前若干行里扫，
      //    因为分量名集合在一个训练任务内是**稳定的**（同一模型结构不变）。
      const seen = new Set<string>();
      const log = displayMetricsLog.value;
      // 扫前 200 行足够覆盖分量名：若还没找齐，再退回全量扫（兜底）
      const scan = (from: number, to: number) => {
        for (let i = from; i < to; i++) {
          const m = log[i];
          if (m == null || m._kind !== "step") continue;
          for (const key in m) {
            if (key === "loss" || key.indexOf("loss_") !== 0) continue;
            if (typeof m[key] === "number") seen.add(key);
          }
        }
      };
      scan(0, Math.min(log.length, 200));
      if (seen.size === 0 && log.length > 200) scan(200, log.length);
      const colors = ["#f56c6c", "#e6a23c", "#409eff", "#909399"];
      const items = [...seen].map((k, i) => ({
        key: k,
        src: k,
        label: k.replace(/^loss_/, "").toUpperCase(),
        color: colors[i % colors.length],
        icon: TrendCharts,
      }));
      return items.length
        ? items
        : [{ key: "loss", src: "loss", label: "Loss", color: "#f56c6c", icon: TrendCharts }];
    }
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

/**
 * 各 loss 分量「最后一条含该键的行」。
 *
 * 单趟**从后往前**扫描：第一个命中的就是最后一条，全部命中即提前结束。
 * 不用 `filter().at(-1)`（每个分量各扫一遍）也不用 `findLast`（部分环境不支持）。
 */
const lastRowWithLoss = computed<Map<string, any>>(() => {
  const want = lossSpec.value.map((s) => s.src);
  const hit = new Map<string, any>();
  if (!want.length) return hit;
  const log = displayMetricsLog.value;
  for (let i = log.length - 1; i >= 0 && hit.size < want.length; i--) {
    const row = log[i];
    if (!row) continue;
    for (const k of want) {
      if (!hit.has(k) && row[k] != null) hit.set(k, row);
    }
  }
  return hit;
});

function lastRowWithKey(key: string): any {
  return lastRowWithLoss.value.get(key);
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
  // PaddleX 指标行用 total，其余框架用 total_epochs
  out.epoch = last?.epoch != null ? `${last.epoch}/${last.total_epochs ?? last.total ?? "?"}` : "—";
  for (const s of metricSpec.value) out[s.key] = fmtRatio(last?.[s.key]);
  // ⚠️ loss 必须去**最后一条含该键的行**取，不能只看 last（eval 行）：
  //    eval 行按设计只有指标、没有 loss 分量，直接读 last 会让「Loss」卡片
  //    在训练完成后恒为「—」，哪怕日志里有 5000 条 step loss。
  for (const s of lossSpec.value) {
    const v = last?.[s.src] ?? lastRowWithKey(s.src)?.[s.src];
    out[s.key] = fmtDecimal(v);
  }
  return out;
});

/**
 * 图表 X 轴取值：**优先用 step**（需求：曲线精确到 step）。
 *
 * ⚠️ 此前用的是 `m.epoch`。TorchKiln 的 step 事件里同一个 epoch 的所有 step
 * epoch 值相同，落在 category 轴上就是**一列重合刻度**——曲线看着像只有几个点，
 * 实际每个点代表一整段 step，损失曲线的细节全被压平了。
 *
 * 判定口径：只要**有任何一行**带 global_step 就整体走 step 轴（缺的那行给 null），
 * 避免同一张图里混用两套量纲。
 */
function useStepAxis(log: any[]): boolean {
  return log.some((m: any) => typeof m?.global_step === "number");
}

function xOf(m: any, stepAxis: boolean): number | null {
  const v = stepAxis ? m?.global_step : m?.epoch;
  return typeof v === "number" ? v : null;
}

/**
 * 统一的折线图 option。
 *
 * - `xAxis.type = "value"`：绕开 category 轴对 N 个刻度做布局与间隔裁剪的开销。
 *   上万 step 时 category 轴本身就是主要瓶颈（`sampling` 只优化 series 绘制，
 *   **不减少轴项数**），换 value 轴才真正省掉这部分。
 * - `sampling: "lttb"`：按视觉保真抽稀，保留尖峰与趋势，替代「等间隔丢点」
 *   （后者会把 loss 突刺抹平，看图等于骗人）。
 * - `large / largeThreshold`：交给 ECharts 的大数据量折线快路径。
 */
/**
 * 图表渲染节流。
 *
 * 指标**每个都收**（存进 `liveMetricsLog`，数据一条不丢），但图表**不必每个都重画**：
 * 实测 5000 点时一次全量重绘约 30ms，step 事件每秒来几个到十几个，等于持续占掉
 * 三成主线程。
 *
 * ⚠️ 这里必须给图表喂**快照副本**而不是活数组。只加一个「节流开关」依赖是**无效**的
 * ——图表 computed 仍在遍历活数组，`push` 一下照样把它标脏、照样全量重算。
 * 正确做法是隔一段时间复制一份给图表看，图表只依赖这份副本。
 *
 * 复制 5000 元素的代价是微秒级，远小于省掉的重绘。
 */
const CHART_THROTTLE_MS = 400;
/** 图表专用的指标快照（只每 CHART_THROTTLE_MS 更新一次） */
const chartLog = ref<any[]>([]);
let chartTickTimer: ReturnType<typeof setTimeout> | null = null;

function syncChartLog() {
  // ⚠️ 必须用 displayMetricsLog 而不是 liveMetricsLog：后者在 SSE 事件到达前是空的，
  //    displayMetricsLog 会回退到 task.value.metrics_log。直接取 liveMetricsLog
  //    会导致「刷新页面后图表空白，直到第一条 SSE 事件到来」。
  chartLog.value = displayMetricsLog.value.slice();
}

/** 有新数据时调用：保证 CHART_THROTTLE_MS 内至少重绘一次（尾沿不丢） */
function scheduleChartRender() {
  if (chartTickTimer) return;
  chartTickTimer = setTimeout(() => {
    chartTickTimer = null;
    syncChartLog();
    // flush 期间若又来了新数据，立刻再排一轮，保证尾沿不丢、也不饿死
    if (chartLog.value.length !== displayMetricsLog.value.length) scheduleChartRender();
  }, CHART_THROTTLE_MS);
}

function lineChartOption(
  log: any[],
  spec: { key: string; label: string; src?: string }[],
  yName: string,
  valueOf: (m: any, s: any) => any
): any {
  const stepAxis = useStepAxis(log);
  // step → epoch 的查表，供 tooltip 显示「step N（epoch M）」
  const epochOf = new Map<number, number>();
  if (stepAxis) {
    for (const m of log) {
      const x = xOf(m, true);
      if (x != null && typeof m?.epoch === "number" && !epochOf.has(x)) {
        epochOf.set(x, m.epoch);
      }
    }
  }
  const xs = log.map((m) => xOf(m, stepAxis));
  const series = spec.map((s) => ({
    name: s.label,
    type: "line",
    showSymbol: false,
    sampling: "lttb",
    large: true,
    largeThreshold: 2000,
    data: log.map((m, i) => {
      const y = valueOf(m, s);
      return [xs[i], y == null || Number.isNaN(y) ? null : y];
    }),
  }));
  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: (params: any[]) => {
        const arr = Array.isArray(params) ? params : [params];
        if (!arr.length) return "";
        const x = arr[0]?.axisValue;
        const ep = stepAxis ? epochOf.get(Number(x)) : undefined;
        const head = stepAxis
          ? `step ${x}${ep != null ? `（epoch ${ep}）` : ""}`
          : `epoch ${x}`;
        const body = arr
          .filter((p: any) => p.value?.[1] != null)
          .map((p: any) => {
            const y = p.value[1];
            return `${p.marker}${p.seriesName}: ${Number(y).toFixed(5)}`;
          })
          .join("<br/>");
        return body ? `${head}<br/>${body}` : head;
      },
    },
    legend: { data: spec.map((s) => s.label), top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: "value",
      name: stepAxis ? "Step" : "Epoch",
      minInterval: stepAxis ? 1 : undefined,
    },
    yAxis: { type: "value", name: yName, scale: true },
    series,
  };
}

const lossChartOption = computed(() => {
  // 读 chartLog（节流快照）而不是 displayMetricsLog：否则每来一个 step 事件
  // 就会全量重算 + 重绘，实测 5000 点时一次要 ~30ms
  const log = chartLog.value;
  if (!log.length) return {};
  return lineChartOption(
    log,
    lossSpec.value,
    "Loss",
    (m, s) => m?.[s.src as string]
  );
});

const valChartOption = computed(() => {
  const spec = metricSpec.value;
  const log = chartLog.value;
  if (!log.length) return {};
  const usable = log.filter((m: any) => spec.some((s) => m[s.key] != null));
  if (!usable.length) return {};
  return lineChartOption(
    usable,
    spec,
    "Metric",
    (m, s) => m?.[s.key]
  );
});

const compareTableData = computed(() => [
  ...lossSpec.value.map((s) => ({
    label: s.label,
    getter: (m: any) => m?.[s.src],
    fmt: (v: number) => Number(v).toFixed(4),
  })),
  ...metricSpec.value.map((s) => ({
    label: s.label,
    // ⚠️ TorchKiln 的 best 事件**不一定**带 metrics 子对象，只有 main_value。
    //    只按指标名取摊平键会在这种情况下取到 null，表格显示「—」，
    //    而值明明就在 main_value 里。找不到摊平键时回退 main_value。
    getter: (m: any) => {
      const v = m?.[s.key];
      if (v != null) return v;
      const isMain = isTorchkiln.value && s.key === tkMainIndicator.value;
      return isMain ? (m?.main_value ?? null) : null;
    },
    // TorchKiln 的主指标可能是 0~1 比例（mAP/acc），也可能是 RMSE/loss 这类任意值
    fmt: (v: number) =>
      isTorchkiln.value && !tkMainIsRatio.value
        ? Number(v).toFixed(4)
        : (Number(v) * 100).toFixed(1) + "%",
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
      top1: yoloMetrics.top1,
      top5: yoloMetrics.top5,
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
    // 检测/分割/姿态汇总为 7 列 P/R/mAP50/mAP50-95；分类汇总为 5 列 top1/top5
    if (parts.length >= 7) {
      yoloMetrics.precision = parseFloat(parts[3]) || 0;
      yoloMetrics.recall = parseFloat(parts[4]) || 0;
      yoloMetrics.map50 = parseFloat(parts[5]) || 0;
      yoloMetrics.map5095 = parseFloat(parts[6]) || 0;
    } else if (parts.length === 5) {
      yoloMetrics.top1 = parseFloat(parts[3]) || 0;
      yoloMetrics.top5 = parseFloat(parts[4]) || 0;
    }
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
      // 检测/分割/姿态汇总为 7 列 P/R/mAP50/mAP50-95；分类汇总为 5 列 top1/top5
      if (parts.length >= 7) {
        current.precision = parseFloat(parts[3]) || 0;
        current.recall = parseFloat(parts[4]) || 0;
        current.map50 = parseFloat(parts[5]) || 0;
        current.map5095 = parseFloat(parts[6]) || 0;
      } else if (parts.length === 5) {
        current.top1 = parseFloat(parts[3]) || 0;
        current.top5 = parseFloat(parts[4]) || 0;
      }
      metrics.push({ ...current });
      current = null;
    }
  }
  if (metrics.length) {
    liveMetricsLog.value = metrics;
    // 整体替换后去重索引全部失效，必须重建（否则新事件会因旧下标误替换）
    rebuildMetricRowIndex();
  }
}

function connectWs(id: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/train/logs?task_id=${id}`);
  wsConnected.value = true;
  ws.onmessage = (e: MessageEvent) => {
    const line = e.data.replace(/\r/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
    // 进环形缓冲，由 flushLog 批量渲染（详见 logBuf 处注释）
    pushLogLine(line);
    parseYoloMetrics(line);
  };
  ws.onclose = () => {
    wsConnected.value = false;
  };
  ws.onerror = () => {
    wsConnected.value = false;
  };
}

function clearLogs() {
  logBuf.length = 0;
  logDropped = 0;
  logText.value = "";
  logLineCount.value = 0;
  if (logFlushTimer) {
    clearTimeout(logFlushTimer);
    logFlushTimer = null;
  }
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
  // ⚠️ 必须用接口返回的 metrics_log 给 liveMetricsLog **播种**，否则图表会塌。
  //
  //    displayMetricsLog 是「liveMetricsLog 非空就用它、否则用 metrics_log」。
  //    页面刷新时 lastSeq 已推到 maxSeqOf(metrics_log)，SSE 只补缺口，于是第一条新事件
  //    到达时 liveMetricsLog.length 由 0 变 1 —— displayMetricsLog 立刻从「5000 条历史」
  //    **整体翻转**成「1 条新数据」，图表瞬间塌成一个点，且越训练越退化。
  //    （浏览器实测：注入 60 条后 liveLen 由 5052 掉到 60。）
  //
  //    播种后 live 数组就是历史的延续，appendMetricRow 才是真正的**增量追加**。
  const rows = r.data?.data?.metrics_log;
  liveMetricsLog.value = Array.isArray(rows) ? rows.slice() : [];
  // 整体替换后去重索引全部失效，必须重建（否则新事件会因旧下标误替换）
  rebuildMetricRowIndex();
  syncChartLog();
}

/**
 * 轮询**只拉状态**，不拉整行详情。
 *
 * ⚠️ `getTaskDetail` 返回完整 `metrics_log`（逐步指标，本项目每任务上限 5000 行），
 * 每 5 秒整体重下一次 = 每 5 秒把整个指标序列重新拉一遍、重新塞进响应式对象、
 * 重新触发所有依赖它的 computed。指标越多页面越卡 —— 这与 AGENTS.md 里
 * 「进度/状态变化只更新对应的一条数据，不要周期性整体刷新」是同一条铁律。
 *
 * 逐步指标由 SSE 流（`metrics/stream`）和 `GET /task/{id}/metrics` 负责，
 * 与状态轮询互不重叠。
 */
async function pollStatus() {
  const id = Number(route.params.id);
  if (!id) return;
  const prevStatus = task.value?.status;
  const r = await TrainAPI.getTaskStatus(id);
  const cur = r.data?.data;
  if (!cur) return;
  // 只就地更新状态相关字段，不整体替换 task 对象（避免连带丢弃局部状态）
  const t: any = task.value;
  if (!t) return;
  for (const k of [
    "status",
    "progress",
    "started_at",
    "finished_at",
    "model_repo_id",
    "best_metrics",
    "last_metrics",
    "error_log",
  ]) {
    if (cur[k] !== undefined) t[k] = cur[k];
  }
  const curStatus = t.status;
  if (curStatus !== prevStatus) {
    if (curStatus === "running" && !ws) connectWs(Number(route.params.id));
  }
  if (curStatus && curStatus !== "running" && curStatus !== "pending") {
    stopPoll();
    stopMetricStream();
  }
}

async function startPoll() {
  stopPoll();
  pollTimer = setInterval(() => {
    void pollStatus();
  }, 5000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ==================================================================
// 指标实时流（SSE）
// ------------------------------------------------------------------
// 为什么不用"每秒整表重拉"：
//   整表重拉会让整块区域重新渲染 —— 闪烁、丢滚动位置、丢选中态。
//   SSE 是**局部增量**：新事件只追加到 liveMetricsLog，曲线/卡片各自重算。
//
// 为什么带 offset：
//   刷新页面/断网重连时带 lastSeq，服务端先补发缺口再切实时，不丢不重。
//   EventSource 会自动重连，但**不会**自动带我们自定义的 offset，
//   所以重连成功后要主动用新的 lastSeq 重新开流。
// ==================================================================
let metricEs: EventSource | null = null;
let metricReconnectTimer: ReturnType<typeof setTimeout> | null = null;
const metricConnected = ref(false);
/** 已消费的最大 seq（用于断点续传；-1=从头） */
let lastSeq = -1;

function isRunningStatus(s?: string) {
  return s === "running" || s === "pending";
}

/** 从已有 metrics_log 推最大 seq（用于首次开流的断点） */
function maxSeqOf(rows: any[] | undefined) {
  let m = -1;
  for (const r of rows || []) {
    if (typeof r?.seq === "number" && r.seq > m) m = r.seq;
  }
  return m;
}

function stopMetricStream() {
  if (metricReconnectTimer) {
    clearTimeout(metricReconnectTimer);
    metricReconnectTimer = null;
  }
  if (metricEs) {
    metricEs.close();
    metricEs = null;
  }
  metricConnected.value = false;
}

/** 把一条指标事件转成 liveMetricsLog 的一行（结构与后端 metrics_log 一致） */
function metricEventToRow(ev: any) {
  const type = ev?.type;
  if (type === "step") {
    const row: any = {
      _kind: "step",
      epoch: ev.epoch,
      global_step: ev.global_step,
      loss: ev.loss,
      lr: ev.lr,
      ips: ev.ips,
      mem_reserved: ev.mem_reserved,
    };
    for (const [k, v] of Object.entries(ev.comps || {})) {
      if (typeof v === "number") row[k] = v;
    }
    return row;
  }
  if (type === "eval" || type === "best") {
    const row: any = {
      _kind: type,
      best: type === "best" ? true : undefined,
      epoch: ev.epoch,
      global_step: ev.global_step,
      main_indicator: ev.main_indicator,
      main_indicator_mode: ev.main_indicator_mode,
      main_value: ev.main_value,
    };
    if (typeof ev.fps === "number") row.fps = ev.fps;
    for (const [k, v] of Object.entries(ev.metrics || {})) {
      if (typeof v === "number") row[k] = v;
    }
    return row;
  }
  if (type === "end") {
    return {
      _kind: "end",
      exit_reason: ev.exit_reason,
      epoch: ev.epoch,
      main_indicator: ev.main_indicator,
      main_value: ev.main_value,
      duration_sec: ev.duration_sec,
    };
  }
  return null;
}

/**
 * 指标行去重索引：`(kind|epoch|step) -> 在 liveMetricsLog 里的**绝对**下标`。
 *
 * ⚠️ 原实现每收一个事件都用 `findIndex` 在 Vue 的 **reactive proxy** 上线性全扫
 * （上限 5000 行）—— 5000 次 proxy 属性访问，每次 push 都付一遍，是卡顿主因之一。
 * 换成 Map 后是 O(1)。step 事件本身按 seq 严格递增、天然不会重复，
 * 但 eval 事件在断线重连时会被补发，所以仍要去重，只是不能再线性扫。
 *
 * ⚠️ 存**绝对**下标（= `metricBase` + 数组下标）而不是数组下标，是为了在丢弃队首
 * 时**不必重建整张索引表**：丢弃后剩余行的数组下标整体左移，但绝对下标不变，
 * 只要 `metricBase` 加上偏移量即可。浏览器实测：不做这一步时，指标一越过
 * 5000 行上限，**每个事件**都要全量重建索引，注入 60 条要 1.66 秒。
 */
const metricRowIndex = new Map<string, number>();
/** 已从队首丢弃的行数；绝对下标 = metricBase + 数组下标 */
let metricBase = 0;
const MAX_METRIC_ROWS = 5000;
/**
 * 攒够这么多「超限行」才切一次队首。
 *
 * 上限 5000 之上允许再溢出 1024 行才做一次 `splice(0, drop)`。
 * 对响应式代理数组做 `splice(0, n)` 是 O(n) 且逐次走 `set` 陷阱，
 * 逐事件执行时是「数据量大了界面卡」的直接元凶（profiler: `set` 占 20.7%）。
 * 攒成块后平摊为每 1024 个事件一次，数组占用只多 20%。
 */
const TRIM_CHUNK = 1024;

function metricRowKey(r: any): string {
  return `${r?._kind}|${r?.epoch}|${r?.global_step}`;
}

/** 数组被**整体替换**后绝对下标失效，调用方负责在此重建索引（并把 metricBase 归零）。 */
function rebuildMetricRowIndex() {
  metricRowIndex.clear();
  metricBase = 0;
  const log = liveMetricsLog.value;
  for (let i = 0; i < log.length; i++) metricRowIndex.set(metricRowKey(log[i]), i);
}

function appendMetricRow(row: any) {
  if (!row) return;
  // ⚠️ `liveMetricsLog` 是**深响应式 ref**，`liveMetricsLog.value` 每访问一次都要走
  //    toRaw + isShallow + isReadonly + reactive 一整套解包。
  //    CPU profiler 实测：单次 append 里重复取 5 次 .value 就占掉约 13% 采样。
  //    这里**只取一次**并复用。
  const log = liveMetricsLog.value;
  // 同一 epoch 的 eval 可能被补发（断线重连），按 (kind,epoch,step) 去重
  const key = metricRowKey(row);
  const abs = metricRowIndex.get(key);
  // 绝对下标换算成当前数组下标；越界说明那行已被丢弃，按新行处理
  const pos = abs === undefined ? -1 : abs - metricBase;
  if (pos >= 0 && pos < log.length) {
    log.splice(pos, 1, row);
  } else {
    metricRowIndex.set(key, metricBase + log.length);
    log.push(row);
  }
  // 曲线点太多会卡渲染，只保留末尾（后端落库同样是 5000 行上限）。
  //
  // ⚠️ 不能一超限就 splice：对 5000 元素的**响应式代理数组**做 splice(0, drop) 是
  //    O(n)，且每次搬移都走一遍 set 陷阱（profiler 里 `set` 占 20.7% 自耗时）。
  //    逐事件都做，实测注入 300 条要 3 秒。
  //    改成**攒够一整块再切一次**，把 O(n) 摊薄成每 TRIM_CHUNK 个事件一次。
  if (log.length > MAX_METRIC_ROWS + TRIM_CHUNK) {
    const drop = log.length - MAX_METRIC_ROWS;
    // 只删**被丢弃那些行**的索引项（O(drop)），其余行的绝对下标不变 ——
    // 因此不需要重建整张索引表。
    for (let i = 0; i < drop; i++) {
      metricRowIndex.delete(metricRowKey(log[i]));
    }
    log.splice(0, drop);
    metricBase += drop;
  }
  // 数据已入数组，这里只**安排**一次节流重绘（不是每个事件都重画）
  scheduleChartRender();
}

function startMetricStream(taskId: number) {
  stopMetricStream();
  const base = import.meta.env.VITE_API_BASE || "/api/v1";
  const url = `${base}/train/task/${taskId}/metrics/stream?offset=${lastSeq}`;
  let es: EventSource;
  try {
    es = new EventSource(url, { withCredentials: true });
  } catch {
    scheduleMetricReconnect(taskId);
    return;
  }
  metricEs = es;

  es.onopen = () => {
    metricConnected.value = true;
  };
  es.onerror = () => {
    metricConnected.value = false;
    // EventSource 会自己重连，但不会带 offset；主动关掉后按新 lastSeq 重开
    es.close();
    if (metricEs === es) metricEs = null;
    scheduleMetricReconnect(taskId);
  };
  const onData = (e: MessageEvent) => {
    let ev: any;
    try {
      ev = JSON.parse(e.data);
    } catch {
      return;
    }
    if (ev && typeof ev.seq === "number") lastSeq = Math.max(lastSeq, ev.seq);
    if (ev?.type === "end" || ev?.__end__) {
      // 作业终结：收流并刷新一次任务详情拿最终状态
      stopMetricStream();
      void loadTask();
      return;
    }
    appendMetricRow(metricEventToRow(ev));
  };
  for (const t of ["step", "eval", "best", "end", "metric"]) {
    es.addEventListener(t, onData as EventListener);
  }
}

function scheduleMetricReconnect(taskId: number) {
  if (metricReconnectTimer) return;
  // 退避到 10s，避免服务不可用时疯狂重连打爆后端
  metricReconnectTimer = setTimeout(() => {
    metricReconnectTimer = null;
    if (isRunningStatus(task.value?.status)) startMetricStream(taskId);
  }, 5000);
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
    rebuildMetricRowIndex();
    syncChartLog();   // 重新训练后清图表（否则节流快照还留着上一轮的曲线）
    Object.assign(yoloMetrics, {
      epoch: 0,
      totalEpochs: 0,
      boxLoss: 0,
      clsLoss: 0,
      dflLoss: 0,
      loss: 0,
      hmean: 0,
      acc: 0,
      top1: 0,
      top5: 0,
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
  const repoId = task.value?.model_repo_id;
  if (!repoId) {
    ElMessage.warning("暂无关联模型，请先完成训练");
    return;
  }
  router.push({ path: "/train/eval", query: { model_repo_id: String(repoId), autoCreate: "1" } });
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
  // 首屏灌一次图表快照：否则节流定时器还没轮到，图表会一直空着
  syncChartLog();
  const id = Number(route.params.id);
  if (id) {
    try {
      const r = await TrainAPI.getTaskLogs(id);
      if (r.data?.data?.logs) {
        const cleaned = r.data.data.logs
          .replace(/\r/g, "")
          .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
        // 历史日志同样走缓冲并只保留末尾 LOG_MAX_LINES 行：整份塞进响应式字符串
        // 会让 <pre> 首屏就渲染一个几十 MB 的文本节点。
        const all = cleaned.split("\n");
        const keep = all.slice(-LOG_MAX_LINES);
        logDropped = all.length - keep.length;
        logBuf.length = 0;
        logBuf.push(...keep);
        flushLog();
        if (!task.value?.metrics_log) parseLogForMetrics(cleaned);
      }
    } catch {
      /* */
    }
    if (task.value?.status === "running") {
      connectWs(id);
      startPoll();
      // 指标走 SSE 局部增量；日志走 WS 文本流。两者互补。
      lastSeq = maxSeqOf(task.value?.metrics_log);
      startMetricStream(id);
    }
  }
});

onBeforeUnmount(() => {
  ws?.close();
  stopPoll();
  stopMetricStream();
  // 定时器不清理会一直跑到页面卸载之后
  if (logFlushTimer) {
    clearTimeout(logFlushTimer);
    logFlushTimer = null;
  }
  if (chartTickTimer) {
    clearTimeout(chartTickTimer);
    chartTickTimer = null;
  }
  metricRowIndex.clear();
});
</script>
