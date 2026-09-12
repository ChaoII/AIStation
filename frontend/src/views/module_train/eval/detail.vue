<template>
  <div class="app-container train-detail-page">
    <div class="detail-header">
      <el-button text size="small" @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="task-name">评估 #{{ evalData?.id }}</span>
      <el-tag :type="tagType(evalData?.status || '') as any" size="small">
        {{ tagLabel(evalData?.status || "") }}
      </el-tag>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">评估信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="模型仓库 ID">
              {{ evalData?.model_repo_id }}
            </el-descriptions-item>
            <el-descriptions-item label="模型版本 ID">
              {{ evalData?.model_id || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="评估数据集">
              {{ evalData?.eval_dataset_name || `#${evalData?.eval_dataset_id}` }}
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">
              {{ evalData?.created_time }}
            </el-descriptions-item>
            <el-descriptions-item label="开始时间">
              {{ evalData?.started_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="完成时间">
              {{ evalData?.finished_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="耗时">{{ durationText }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">评估参数</span></template>
          <div class="hp-grid">
            <div class="hp-item">
              <span class="hp-label">imgsz</span>
              <span class="hp-value">{{ evalData?.hyperparams?.imgsz ?? 640 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">batch</span>
              <span class="hp-value">{{ evalData?.hyperparams?.batch ?? 16 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">conf</span>
              <span class="hp-value">{{ evalData?.hyperparams?.conf ?? 0.001 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">iou</span>
              <span class="hp-value">{{ evalData?.hyperparams?.iou ?? 0.6 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">GPU 设备</span>
              <span class="hp-value">{{ evalData?.hyperparams?.device ?? "0" }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">操作</span></template>
      <div class="action-buttons">
        <template v-if="evalData?.status === 'pending'">
          <el-button type="primary" size="default" @click="handleStart">开始评估</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="evalData?.status === 'running'">
          <el-button type="danger" size="default" @click="handleStop">停止评估</el-button>
        </template>
        <template v-else-if="evalData?.status === 'success'">
          <el-button size="default" @click="handleReEval">重新评估</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="evalData?.status === 'failed'">
          <el-button type="primary" size="default" @click="handleReEval">重新评估</el-button>
          <el-button size="default" @click="scrollToLog">查看日志</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="evalData?.status === 'cancelled'">
          <el-button type="primary" size="default" @click="handleReEval">重新评估</el-button>
        </template>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">评估指标</span></template>
      <el-row v-if="evalData?.metrics" :gutter="12">
        <el-col v-for="s in metricSpec" :key="s.key" :xs="24" :sm="12" :md="6">
          <div class="metric-item">
            <el-icon :size="22" :style="{ color: s.color, marginBottom: '4px' }">
              <component :is="s.icon" />
            </el-icon>
            <span class="metric-val" :style="{ color: s.color }">
              {{ fmtRatio(evalData.metrics[s.key]) }}
            </span>
            <span class="metric-lbl">{{ s.label }}</span>
          </div>
        </el-col>
      </el-row>
      <el-empty v-else :image-size="40" description="暂无评估指标" />
    </el-card>

    <!-- Per-class metrics table -->
    <el-card v-if="evalData?.metrics?.classes" shadow="never" class="section-card">
      <template #header><span class="card-title">各类别指标</span></template>
      <el-table :data="classTableData" border size="small" style="width: 100%">
        <el-table-column prop="cls" label="类别" width="100" />
        <el-table-column label="Precision">
          <template #default="{ row }">{{ fmtPct(row.precision) }}</template>
        </el-table-column>
        <el-table-column label="Recall">
          <template #default="{ row }">{{ fmtPct(row.recall) }}</template>
        </el-table-column>
        <el-table-column label="mAP@50">
          <template #default="{ row }">{{ fmtPct(row.map50) }}</template>
        </el-table-column>
        <el-table-column label="mAP@50:95">
          <template #default="{ row }">{{ fmtPct(row.map5095) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert
      v-if="evalData?.error_log"
      title="评估失败"
      type="error"
      :description="evalData.error_log.slice(0, 500)"
      show-icon
      closable
      style="margin-bottom: 16px"
    />

    <!-- Log area -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="log-header">
          <span class="card-title">评估日志</span>
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

    <el-card v-if="evalData?.model_repo_id" shadow="never" class="section-card">
      <template #header><span class="card-title">模型输出</span></template>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="模型仓库 ID">
          <el-tag size="small">{{ evalData.model_repo_id }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 12px">
        <el-button type="primary" size="default" @click="handleViewModel">查看模型</el-button>
        <el-button size="default" @click="handleExport">导出模型</el-button>
        <el-button
          v-if="evalData?.status === 'success'"
          size="default"
          type="primary"
          @click="handleGoPredict"
        >
          去预测
        </el-button>
      </div>
    </el-card>

    <ModelExportDialog
      v-model="exportDialogVisible"
      :model-id="evalData?.model_id || 0"
      :model-name="evalData?.model_id ? `评估 #${evalData?.id}` : ''"
      @done="loadEval"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";
import { resolveMainMetricSpec, fmtRatio, type MetricSpecItem } from "@/utils/trainMetrics";
import ModelExportDialog from "@/components/ModelExportDialog/index.vue";

const route = useRoute();
const router = useRouter();
const evalData = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);
const wsConnected = ref(false);
const logLineCount = ref(0);
const submitting = ref(false);
let ws: WebSocket | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;

function tagType(s: string) {
  return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info";
}
function tagLabel(s: string) {
  return ({ pending: "待开始", running: "评估中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s;
}
function fmtPct(v: number | undefined) {
  return v != null ? (v * 100).toFixed(1) + "%" : "—";
}

// 评估框架可能未持久化，且 YOLO 分类无 task_type 字段；
// 分类信号优先看指标键 top1/top5（与训练详情同一推断思路）。
const isClassifyEval = computed(() => {
  const m = evalData.value?.metrics;
  return !!(m && (m.top1 != null || m.top5 != null));
});

// 主指标按框架/模式渲染：PaddleX det→HMean/PR、rec→Acc；YOLO cls→Top1/5；其余→mAP/PR
const metricSpec = computed<MetricSpecItem[]>(() =>
  resolveMainMetricSpec({
    framework: evalData.value?.framework,
    mode: evalData.value?.hyperparams?.mode,
    classify: isClassifyEval.value,
  })
);

const classTableData = computed(() => {
  const cls = evalData.value?.metrics?.classes;
  if (!cls) return [];
  return Object.entries(cls).map(([k, v]: [string, any]) => ({
    cls: k,
    precision: v.precision,
    recall: v.recall,
    map50: v.map50,
    map5095: v.map5095,
  }));
});

const durationText = computed(() => {
  if (!evalData.value?.started_at) return "—";
  const start = new Date(evalData.value.started_at).getTime();
  const end = evalData.value.finished_at ? new Date(evalData.value.finished_at).getTime() : Date.now();
  const diff = Math.floor((end - start) / 1000);
  if (diff < 60) return `${diff}秒`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分${diff % 60}秒`;
  return `${Math.floor(diff / 3600)}时${Math.floor((diff % 3600) / 60)}分`;
});

function connectWs(evalId: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/eval/logs?eval_id=${evalId}`);
  wsConnected.value = true;
  ws.onmessage = (e: MessageEvent) => {
    const line = e.data.replace(/\r/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
    logText.value += line + "\n";
    logLineCount.value++;
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

async function loadEval() {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getEvalDetail(id);
  evalData.value = r.data?.data;
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    const prevStatus = evalData.value?.status;
    await loadEval();
    const curStatus = evalData.value?.status;
    if (curStatus !== prevStatus) {
      if (curStatus === "running" && !ws) {
        const id = Number(route.params.id);
        connectWs(id);
      }
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
    await ElMessageBox.confirm(`确定开始评估任务 #${evalData.value?.id}？`, "提示", { type: "info" });
    await TrainAPI.startEval(evalData.value.id);
    await loadEval();
    connectWs(evalData.value.id);
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
    await ElMessageBox.confirm("确定停止该评估？", "提示", { type: "warning" });
    await TrainAPI.stopEval(evalData.value.id);
    await loadEval();
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

async function handleDelete() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定删除评估 #${evalData.value?.id}？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
    });
    await TrainAPI.deleteEval([evalData.value.id]);
    router.push("/train/eval");
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

async function handleReEval() {
  if (submitting.value) return;
  submitting.value = true;
  if (!evalData.value) {
    submitting.value = false;
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定重新评估 #${evalData.value.id}？将清除之前的评估结果。`,
      "重新评估",
      { type: "warning", confirmButtonText: "确定重新评估" }
    );
    stopPoll();
    if (ws) {
      ws.close();
      ws = null;
    }
    clearLogs();
    await TrainAPI.startEval(evalData.value.id);
    await loadEval();
    connectWs(evalData.value.id);
    startPoll();
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

function handleViewModel() {
  if (evalData.value?.model_repo_id) router.push(`/train/repo?model_id=${evalData.value.model_repo_id}`);
  else ElMessage.warning("暂无关联模型");
}

function handleGoPredict() {
  if (!evalData.value?.model_id) {
    ElMessage.warning("暂无模型版本，无法预测");
    return;
  }
  router.push({
    path: "/train/predict",
    query: {
      model_id: String(evalData.value.model_id),
      model_repo_id: String(evalData.value.model_repo_id || 0),
      autoCreate: "1",
    },
  });
}

const exportDialogVisible = ref(false);

function handleExport() {
  if (!evalData.value?.model_id) {
    ElMessage.warning("暂无关联模型");
    return;
  }
  // 导出需要版本 id（model_id），仓库 id 不能用于 export 接口
  TrainAPI.getModelDetail(evalData.value.model_id).then(res => {
    if (res.data?.data) {
      exportDialogVisible.value = true;
    } else {
      ElMessage.error("关联模型已不存在");
    }
  }).catch(() => {
    ElMessage.error("关联模型已不存在");
  });
}

onMounted(async () => {
  await loadEval();
  const id = Number(route.params.id);
  if (id) {
    if (evalData.value?.status === "running") {
      connectWs(id);
      startPoll();
    }
    try {
      const r = await TrainAPI.getEvalLogs(id);
      if (r.data?.data?.logs) {
        logText.value = r.data.data.logs;
        logLineCount.value = (r.data.data.logs.match(/\n/g) || []).length;
      }
    } catch {
      if (evalData.value?.log) {
        logText.value = evalData.value.log;
        logLineCount.value = (evalData.value.log.match(/\n/g) || []).length;
      }
    }
  }
});

onBeforeUnmount(() => {
  ws?.close();
  stopPoll();
});
</script>
