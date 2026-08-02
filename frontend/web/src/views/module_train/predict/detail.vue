<template>
  <div class="train-detail-page">
    <div class="detail-header">
      <ElButton text size="small" @click="router.back()">
        <ElIcon><ArrowLeft /></ElIcon>
      </ElButton>
      <span class="task-name">预测 #{{ predict?.id }}</span>
      <ElTag :type="tagType(predict?.status || '') as any" size="small">
        {{ tagLabel(predict?.status || "") }}
      </ElTag>
    </div>

    <ElRow :gutter="16">
      <ElCol :xs="24" :md="12">
        <ElCard shadow="never" class="info-card">
          <template #header><span class="card-title">预测信息</span></template>
          <ElDescriptions :column="1" size="small" border>
            <ElDescriptionsItem label="模型版本 ID">{{ predict?.model_id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="模型仓库 ID">{{ predict?.model_repo_id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="图片来源">{{ predict?.source_type === "dataset" ? "数据集" : "上传图片" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="源数据集 ID">{{ predict?.source_dataset_id || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="创建时间">{{ predict?.created_time }}</ElDescriptionsItem>
            <ElDescriptionsItem label="开始时间">{{ predict?.started_at || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="完成时间">{{ predict?.finished_at || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="耗时">{{ durationText }}</ElDescriptionsItem>
          </ElDescriptions>
        </ElCard>
      </ElCol>
      <ElCol :xs="24" :md="12">
        <ElCard shadow="never" class="info-card">
          <template #header><span class="card-title">预测参数</span></template>
          <div class="hp-grid">
            <div class="hp-item"><span class="hp-label">conf</span><span class="hp-value">{{ predict?.hyperparams?.conf ?? 0.25 }}</span></div>
            <div class="hp-item"><span class="hp-label">iou</span><span class="hp-value">{{ predict?.hyperparams?.iou ?? 0.45 }}</span></div>
            <div class="hp-item"><span class="hp-label">imgsz</span><span class="hp-value">{{ predict?.hyperparams?.imgsz ?? 640 }}</span></div>
            <div class="hp-item"><span class="hp-label">GPU 设备</span><span class="hp-value">{{ predict?.hyperparams?.device ?? "0" }}</span></div>
          </div>
        </ElCard>
      </ElCol>
    </ElRow>

    <ElCard shadow="never" class="section-card">
      <template #header><span class="card-title">操作</span></template>
      <div class="action-buttons">
        <template v-if="predict?.status === 'pending'">
          <ElButton type="primary" size="default" @click="handleStart">开始预测</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="predict?.status === 'running'">
          <ElButton type="danger" size="default" @click="handleStop">停止预测</ElButton>
        </template>
        <template v-else-if="predict?.status === 'success'">
          <ElButton v-if="predict?.result_zip_path" type="primary" size="default" @click="downloadZip(predict.result_zip_path)">下载结果</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="predict?.status === 'failed'">
          <ElButton type="primary" size="default" @click="handleStart">重新预测</ElButton>
          <ElButton size="default" @click="scrollToLog">查看日志</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="predict?.status === 'cancelled'">
          <ElButton type="primary" size="default" @click="handleStart">重新预测</ElButton>
        </template>
      </div>
    </ElCard>

    <ElCard shadow="never" class="section-card">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="card-title">预测结果</span>
          <ElButton v-if="predict?.result_zip_path" size="small" type="primary" @click="downloadZip(predict.result_zip_path)">下载全部</ElButton>
        </div>
      </template>
      <ElRow v-if="predict?.result_images?.length" :gutter="12">
        <ElCol v-for="(url, i) in predict.result_images" :key="i" :xs="24" :sm="12" :md="6">
          <div class="result-item">
            <ElImage :src="url" :preview-src-list="predict.result_images" fit="cover" style="width:100%;height:180px;border-radius:6px" />
          </div>
        </ElCol>
      </ElRow>
      <ElEmpty v-else :image-size="40" description="暂无预测结果" />
    </ElCard>

    <ElAlert
      v-if="predict?.log && predict?.status === 'failed'"
      title="预测失败"
      type="error"
      :description="predict.log.slice(0, 500)"
      show-icon
      closable
      style="margin-bottom: 16px"
    />

    <ElCard shadow="never" class="section-card">
      <template #header>
        <div class="log-header">
          <span class="card-title">预测日志</span>
          <div class="log-controls">
            <span class="log-status" :class="{ connected: wsConnected }">{{ wsConnected ? "已连接" : "未连接" }}</span>
            <span class="log-line-count">{{ logLineCount }} 行</span>
            <ElSwitch v-model="autoScroll" active-text="自动滚动" size="small" style="margin-right: 8px" />
            <ElButton size="small" text @click="clearLogs">清空</ElButton>
          </div>
        </div>
      </template>
      <div ref="logRef" class="log-container">
        <pre class="log-text">{{ logText || "等待日志..." }}</pre>
      </div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

defineOptions({ name: "TrainPredictDetail" });

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
    const line = e.data.replace(/[\r\x1b\[[0-9;]*m]/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "");
    logText.value += line + "\n";
    logLineCount.value++;
    if (autoScroll.value)
      nextTick(() =>
        requestAnimationFrame(() => {
          if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
        })
      );
  };
  ws.onclose = () => { wsConnected.value = false; };
  ws.onerror = () => { wsConnected.value = false; };
}

function clearLogs() { logText.value = ""; logLineCount.value = 0; }

function scrollToLog() {
  setTimeout(() => {
    const el = document.querySelector(".log-container");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }, 100);
}

async function loadPredict() {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.detailPredict(id);
  predict.value = r.data?.data;
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    const prevStatus = predict.value?.status;
    await loadPredict();
    const curStatus = predict.value?.status;
    if (curStatus !== prevStatus && curStatus === "running" && !ws) connectWs(Number(route.params.id));
    if (curStatus && curStatus !== "running" && curStatus !== "pending") stopPoll();
  }, 5000);
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
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
  } finally { submitting.value = false; }
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
  } finally { submitting.value = false; }
}

async function handleDelete() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定删除预测 #${predict.value?.id}？`, "提示", { type: "warning", confirmButtonText: "删除" });
    await TrainAPI.deletePredict([predict.value.id]);
    ElMessage.success("已删除");
    router.push("/train/predict");
  } catch {
    /* */
  } finally { submitting.value = false; }
}

function downloadZip(url: string) {
  window.open(url, "_blank");
}

onMounted(async () => {
  await loadPredict();
  const id = Number(route.params.id);
  if (id) {
    if (predict.value?.status === "running") { connectWs(id); startPoll(); }
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

<style lang="scss" scoped>
.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.task-name { font-size: 15px; font-weight: 600; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.info-card { height: 100%; }
.hp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.hp-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f2f3f5; }
.hp-label { color: #909399; font-size: 13px; }
.hp-value { color: #303133; font-size: 13px; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.result-item { border-radius: 8px; overflow: hidden; border: 1px solid #ebeef5; padding: 4px; background: #fafafa; transition: box-shadow 0.2s; }
.result-item:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); }
.log-header { display: flex; align-items: center; justify-content: space-between; }
.log-controls { display: flex; align-items: center; gap: 8px; }
.log-status { font-size: 12px; color: #909399; }
.log-status.connected { color: #67c23a; }
.log-line-count { font-size: 12px; color: #909399; }
.log-container { height: 400px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
