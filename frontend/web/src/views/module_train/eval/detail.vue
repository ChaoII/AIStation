<template>
  <div class="train-detail-page">
    <div class="detail-header">
      <ElButton text size="small" @click="router.back()">
        <ElIcon><ArrowLeft /></ElIcon>
      </ElButton>
      <span class="task-name">评估 #{{ evalData?.id }}</span>
      <ElTag :type="tagType(evalData?.status || '') as any" size="small">
        {{ tagLabel(evalData?.status || "") }}
      </ElTag>
    </div>

    <ElRow :gutter="16">
      <ElCol :xs="24" :md="12">
        <ElCard shadow="never" class="info-card">
          <template #header><span class="card-title">评估信息</span></template>
          <ElDescriptions :column="1" size="small" border>
            <ElDescriptionsItem label="模型仓库 ID">{{ evalData?.model_repo_id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="模型版本 ID">{{ evalData?.model_id || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="评估数据集 ID">{{ evalData?.eval_dataset_id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="创建时间">{{ evalData?.created_time }}</ElDescriptionsItem>
            <ElDescriptionsItem label="开始时间">{{ evalData?.started_at || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="完成时间">{{ evalData?.finished_at || "—" }}</ElDescriptionsItem>
            <ElDescriptionsItem label="耗时">{{ durationText }}</ElDescriptionsItem>
          </ElDescriptions>
        </ElCard>
      </ElCol>
      <ElCol :xs="24" :md="12">
        <ElCard shadow="never" class="info-card">
          <template #header><span class="card-title">评估参数</span></template>
          <div class="hp-grid">
            <div class="hp-item"><span class="hp-label">imgsz</span><span class="hp-value">{{ evalData?.hyperparams?.imgsz ?? 640 }}</span></div>
            <div class="hp-item"><span class="hp-label">batch</span><span class="hp-value">{{ evalData?.hyperparams?.batch ?? 16 }}</span></div>
            <div class="hp-item"><span class="hp-label">conf</span><span class="hp-value">{{ evalData?.hyperparams?.conf ?? 0.001 }}</span></div>
            <div class="hp-item"><span class="hp-label">iou</span><span class="hp-value">{{ evalData?.hyperparams?.iou ?? 0.6 }}</span></div>
            <div class="hp-item"><span class="hp-label">GPU 设备</span><span class="hp-value">{{ evalData?.hyperparams?.device ?? "0" }}</span></div>
          </div>
        </ElCard>
      </ElCol>
    </ElRow>

    <ElCard shadow="never" class="section-card">
      <template #header><span class="card-title">操作</span></template>
      <div class="action-buttons">
        <template v-if="evalData?.status === 'pending'">
          <ElButton type="primary" size="default" @click="handleStart">开始评估</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="evalData?.status === 'running'">
          <ElButton type="danger" size="default" @click="handleStop">停止评估</ElButton>
        </template>
        <template v-else-if="evalData?.status === 'success'">
          <ElButton size="default" @click="handleReEval">重新评估</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="evalData?.status === 'failed'">
          <ElButton type="primary" size="default" @click="handleReEval">重新评估</ElButton>
          <ElButton size="default" @click="scrollToLog">查看日志</ElButton>
          <ElButton type="danger" size="default" @click="handleDelete">删除</ElButton>
        </template>
        <template v-else-if="evalData?.status === 'cancelled'">
          <ElButton type="primary" size="default" @click="handleReEval">重新评估</ElButton>
        </template>
      </div>
    </ElCard>

    <ElCard shadow="never" class="section-card">
      <template #header><span class="card-title">评估指标</span></template>
      <ElRow v-if="evalData?.metrics" :gutter="12">
        <ElCol :xs="24" :sm="12" :md="6">
          <div class="metric-item"><span class="metric-val metric-green">{{ fmtPct(evalData.metrics.precision) }}</span><span class="metric-lbl">Precision</span></div>
        </ElCol>
        <ElCol :xs="24" :sm="12" :md="6">
          <div class="metric-item"><span class="metric-val metric-blue">{{ fmtPct(evalData.metrics.recall) }}</span><span class="metric-lbl">Recall</span></div>
        </ElCol>
        <ElCol :xs="24" :sm="12" :md="6">
          <div class="metric-item"><span class="metric-val metric-orange">{{ fmtPct(evalData.metrics.map50) }}</span><span class="metric-lbl">mAP@50</span></div>
        </ElCol>
        <ElCol :xs="24" :sm="12" :md="6">
          <div class="metric-item"><span class="metric-val metric-purple">{{ fmtPct(evalData.metrics.map5095) }}</span><span class="metric-lbl">mAP@50:95</span></div>
        </ElCol>
      </ElRow>
      <ElEmpty v-else :image-size="40" description="暂无评估指标" />
    </ElCard>

    <ElCard v-if="evalData?.metrics?.classes" shadow="never" class="section-card">
      <template #header><span class="card-title">各类别指标</span></template>
      <ElTable :data="classTableData" border size="small" style="width: 100%">
        <ElTableColumn prop="cls" label="类别" width="100" />
        <ElTableColumn label="Precision"><template #default="{ row }">{{ fmtPct(row.precision) }}</template></ElTableColumn>
        <ElTableColumn label="Recall"><template #default="{ row }">{{ fmtPct(row.recall) }}</template></ElTableColumn>
        <ElTableColumn label="mAP@50"><template #default="{ row }">{{ fmtPct(row.map50) }}</template></ElTableColumn>
        <ElTableColumn label="mAP@50:95"><template #default="{ row }">{{ fmtPct(row.map5095) }}</template></ElTableColumn>
      </ElTable>
    </ElCard>

    <ElAlert
      v-if="evalData?.error_log"
      title="评估失败"
      type="error"
      :description="evalData.error_log.slice(0, 500)"
      show-icon
      closable
      style="margin-bottom: 16px"
    />

    <ElCard shadow="never" class="section-card">
      <template #header>
        <div class="log-header">
          <span class="card-title">评估日志</span>
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

    <ElCard v-if="evalData?.model_repo_id" shadow="never" class="section-card">
      <template #header><span class="card-title">模型输出</span></template>
      <ElDescriptions :column="2" size="small" border>
        <ElDescriptionsItem label="模型仓库 ID"><ElTag size="small">{{ evalData.model_repo_id }}</ElTag></ElDescriptionsItem>
      </ElDescriptions>
      <div style="margin-top: 12px">
        <ElButton type="primary" size="default" @click="handleViewModel">查看模型</ElButton>
        <ElButton size="default" @click="router.push('/train/repo')">返回列表</ElButton>
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

defineOptions({ name: "TrainEvalDetail" });

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
  const r = await TrainAPI.detailEval(id);
  evalData.value = r.data?.data;
}

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    const prevStatus = evalData.value?.status;
    await loadEval();
    const curStatus = evalData.value?.status;
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
    await ElMessageBox.confirm(`确定开始评估任务 #${evalData.value?.id}？`, "提示", { type: "info" });
    await TrainAPI.startEval(evalData.value.id);
    ElMessage.success("评估已开始");
    await loadEval();
    connectWs(evalData.value.id);
    startPoll();
  } catch (e: any) {
    if (e !== "cancel") ElMessage.error(e?.msg || "开始评估失败");
  } finally { submitting.value = false; }
}

async function handleStop() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm("确定停止该评估？", "提示", { type: "warning" });
    await TrainAPI.stopEval(evalData.value.id);
    ElMessage.success("评估已停止");
    await loadEval();
  } catch {
    /* */
  } finally { submitting.value = false; }
}

async function handleDelete() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定删除评估 #${evalData.value?.id}？`, "提示", { type: "warning", confirmButtonText: "删除" });
    await TrainAPI.deleteEval([evalData.value.id]);
    ElMessage.success("已删除");
    router.push("/train/eval");
  } catch {
    /* */
  } finally { submitting.value = false; }
}

async function handleReEval() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    await ElMessageBox.confirm(`确定重新评估 #${evalData.value?.id}？将清除之前的评估结果。`, "重新评估", { type: "warning", confirmButtonText: "确定重新评估" });
    stopPoll();
    if (ws) { ws.close(); ws = null; }
    clearLogs();
    await TrainAPI.startEval(evalData.value.id);
    ElMessage.success("评估已重新开始");
    await loadEval();
    connectWs(evalData.value.id);
    startPoll();
  } catch {
    /* */
  } finally { submitting.value = false; }
}

function handleViewModel() {
  if (evalData.value?.model_repo_id) router.push(`/train/repo?model_id=${evalData.value.model_repo_id}`);
  else ElMessage.warning("暂无关联模型");
}

onMounted(async () => {
  await loadEval();
  const id = Number(route.params.id);
  if (id) {
    if (evalData.value?.status === "running") { connectWs(id); startPoll(); }
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
.task-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.info-card { height: 100%; }
.hp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.hp-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f2f3f5; }
.hp-label { color: #909399; font-size: 13px; }
.hp-value { color: #303133; font-size: 13px; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.metric-item { background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 16px 12px; text-align: center; transition: box-shadow 0.2s; }
.metric-item:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); }
.metric-val { display: block; font-size: 18px; font-weight: 700; font-family: "Cascadia Code", monospace; color: #303133; }
.metric-lbl { display: block; font-size: 12px; color: #909399; margin-top: 4px; }
.metric-green { color: #67c23a; }
.metric-blue { color: #409eff; }
.metric-orange { color: #e6a23c; }
.metric-purple { color: #9b59b6; }
.log-header { display: flex; align-items: center; justify-content: space-between; }
.log-controls { display: flex; align-items: center; gap: 8px; }
.log-status { font-size: 12px; color: #909399; }
.log-status.connected { color: #67c23a; }
.log-line-count { font-size: 12px; color: #909399; }
.log-container { height: 400px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
