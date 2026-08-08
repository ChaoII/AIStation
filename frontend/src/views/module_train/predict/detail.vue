<template>
  <div class="app-container train-detail-page">
    <div class="detail-header">
      <el-button text size="small" @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="task-name">预测 #{{ predict?.id }}</span>
      <el-tag :type="tagType(predict?.status || '') as any" size="small">
        {{ tagLabel(predict?.status || "") }}
      </el-tag>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">预测信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="模型版本 ID">{{ predict?.model_id }}</el-descriptions-item>
            <el-descriptions-item label="模型仓库 ID">{{ predict?.model_repo_id }}</el-descriptions-item>
            <el-descriptions-item label="图片来源">
              {{ predict?.source_type === "dataset" ? "数据集" : "上传图片" }}
            </el-descriptions-item>
            <el-descriptions-item label="源数据集 ID">
              {{ predict?.source_dataset_id || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">
              {{ predict?.created_time }}
            </el-descriptions-item>
            <el-descriptions-item label="开始时间">
              {{ predict?.started_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="完成时间">
              {{ predict?.finished_at || "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="耗时">{{ durationText }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">预测参数</span></template>
          <div class="hp-grid">
            <div class="hp-item">
              <span class="hp-label">conf</span>
              <span class="hp-value">{{ predict?.hyperparams?.conf ?? 0.25 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">iou</span>
              <span class="hp-value">{{ predict?.hyperparams?.iou ?? 0.45 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">imgsz</span>
              <span class="hp-value">{{ predict?.hyperparams?.imgsz ?? 640 }}</span>
            </div>
            <div class="hp-item">
              <span class="hp-label">GPU 设备</span>
              <span class="hp-value">{{ predict?.hyperparams?.device ?? "0" }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">操作</span></template>
      <div class="action-buttons">
        <template v-if="predict?.status === 'pending'">
          <el-button type="primary" size="default" @click="handleStart">开始预测</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="predict?.status === 'running'">
          <el-button type="danger" size="default" @click="handleStop">停止预测</el-button>
        </template>
        <template v-else-if="predict?.status === 'success'">
          <el-button v-if="predict?.result_zip_path" type="primary" size="default" @click="downloadZip(predict.result_zip_path)">下载结果</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="predict?.status === 'failed'">
          <el-button type="primary" size="default" @click="handleStart">重新预测</el-button>
          <el-button size="default" @click="scrollToLog">查看日志</el-button>
          <el-button type="danger" size="default" @click="handleDelete">删除</el-button>
        </template>
        <template v-else-if="predict?.status === 'cancelled'">
          <el-button type="primary" size="default" @click="handleStart">重新预测</el-button>
        </template>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">预测结果</span></template>
      <el-row :gutter="12">
        <el-col v-for="(url, i) in predict.result_images" :key="i" :xs="24" :sm="12" :md="6">
          <div class="result-item">
            <el-image
              :src="url"
              :preview-src-list="predict.result_images"
              fit="cover"
              style="width: 100%; height: 180px; border-radius: 6px"
            />
          </div>
        </el-col>
      </el-row>
      <el-empty v-if="!predict.result_images || predict.result_images.length === 0" :image-size="40" description="暂无预测结果" />
    </el-card>

    <el-alert
      v-if="predict?.log && predict?.status === 'failed'"
      title="预测失败"
      type="error"
      :description="predict.log.slice(0, 500)"
      show-icon
      closable
      style="margin-bottom: 16px"
    />

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="log-header">
          <span class="card-title">预测日志</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const predict = ref<any>(null);
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
  return ({ pending: "待开始", running: "预测中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s;
}

const durationText = computed(() => {
  if (!predict.value?.started_at) return "—";
  const start = new Date(predict.value.started_at).getTime();
  const end = predict.value.finished_at ? new Date(predict.value.finished_at).getTime() : Date.now();
  const diff = Math.floor((end - start) / 1000);
  if (diff < 60) return `${diff}秒`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分${diff % 60}秒`;
  return `${Math.floor(diff / 3600)}时${Math.floor((diff % 3600) / 60)}分`;
});

function connectWs(predictId: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/predict/logs?predict_id=${predictId}`);
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

async function loadPredict() {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getPredictDetail(id);
  predict.value = r.data?.data;
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    const prevStatus = predict.value?.status;
    await loadPredict();
    const curStatus = predict.value?.status;
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
    await ElMessageBox.confirm(`确定开始预测任务 #${predict.value?.id}？`, "提示", { type: "info" });
    await TrainAPI.startPredict(predict.value.id);
    ElMessage.success("预测已开始");
    await loadPredict();
    connectWs(predict.value.id);
    startPoll();
  } catch (e: any) {
    if (e !== "cancel") ElMessage.error(e?.msg || "开始预测失败");
  } finally {
    submitting.value = false;
  }
}

async function handleStop() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm("确定停止该预测？", "提示", { type: "warning" });
    await TrainAPI.stopPredict(predict.value.id);
    ElMessage.success("预测已停止");
    await loadPredict();
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
    await ElMessageBox.confirm(`确定删除预测 #${predict.value?.id}？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
    });
    await TrainAPI.deletePredict([predict.value.id]);
    ElMessage.success("已删除");
    router.push("/train/predict");
  } catch {
    /* */
  } finally {
    submitting.value = false;
  }
}

function downloadZip(url: string) {
  window.open(url, "_blank");
}

onMounted(async () => {
  await loadPredict();
  const id = Number(route.params.id);
  if (id) {
    if (predict.value?.status === "running") {
      connectWs(id);
      startPoll();
    }
    if (predict.value?.log) {
      logText.value = predict.value.log;
      logLineCount.value = (predict.value.log.match(/\n/g) || []).length;
    }
  }
});

onBeforeUnmount(() => {
  ws?.close();
  stopPoll();
});
</script>
