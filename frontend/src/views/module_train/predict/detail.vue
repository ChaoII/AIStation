<template>
  <div class="app-container train-detail-page">
    <div class="detail-header">
      <el-button text size="small" @click="router.back()"><el-icon><ArrowLeft /></el-icon></el-button>
      <span class="task-name">预测 #{{ predict?.id }}</span>
      <el-tag :type="(tagType(predict?.status || '') as any)" size="small">{{ tagLabel(predict?.status || '') }}</el-tag>
    </div>

    <div class="info-cards">
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">预测信息</span></template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="模型版本 ID">{{ predict?.model_id }}</el-descriptions-item>
          <el-descriptions-item label="图片来源">{{ predict?.source_type === 'dataset' ? '数据集' : '上传图片' }}</el-descriptions-item>
          <el-descriptions-item label="源数据集 ID">{{ predict?.source_dataset_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ predict?.created_time }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ predict?.finished_at || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">预测参数</span></template>
        <div class="hp-grid">
          <div class="hp-item"><span class="hp-label">conf</span><span class="hp-value">{{ predict?.hyperparams?.conf ?? 0.25 }}</span></div>
          <div class="hp-item"><span class="hp-label">iou</span><span class="hp-value">{{ predict?.hyperparams?.iou ?? 0.45 }}</span></div>
          <div class="hp-item"><span class="hp-label">imgsz</span><span class="hp-value">{{ predict?.hyperparams?.imgsz ?? 640 }}</span></div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="card-title">预测结果</span>
          <el-button v-if="predict?.result_zip_path" size="small" type="primary" @click="downloadZip(predict.result_zip_path)">下载全部</el-button>
        </div>
      </template>
      <div v-if="predict?.result_images?.length" class="result-grid">
        <div v-for="(url, i) in predict.result_images" :key="i" class="result-item">
          <el-image :src="url" :preview-src-list="predict.result_images" fit="cover" style="width:100%;height:180px;border-radius:6px" />
        </div>
      </div>
      <el-empty v-else :image-size="40" description="暂无预测结果" />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">预测日志</span></template>
      <div ref="logRef" class="log-container">
        <pre class="log-text">{{ logText || '等待日志...' }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft } from "@element-plus/icons-vue";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const predict = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
let ws: WebSocket | null = null;

function tagType(s: string) { return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info"; }
function tagLabel(s: string) { return ({ pending: "待开始", running: "预测中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s; }

function downloadZip(url: string) { window.open(url, "_blank"); }

function connectWs(predictId: number) {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/^http/, "ws");
  ws = new WebSocket(`${baseUrl}/api/v1/train/ws/predict/logs?predict_id=${predictId}`);
  ws.onmessage = (e: MessageEvent) => {
    logText.value += e.data.replace(/[\r\x1b\[[0-9;]*m]/g, "").replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "") + "\n";
  };
  ws.onclose = () => {};
  ws.onerror = () => {};
}

onMounted(async () => {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getPredictDetail(id);
  predict.value = r.data?.data;
  if (predict.value?.status === "running") {
    connectWs(id);
  }
  if (predict.value?.log) {
    logText.value = predict.value.log;
  }
});

onBeforeUnmount(() => { ws?.close(); });
</script>

<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>

<style scoped lang="scss">
.detail-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 10px 16px; background: #fff; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }
.task-name { font-size: 15px; font-weight: 600; margin-right: 4px; color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-title { font-weight: 600; font-size: 14px; color: #303133; }
.info-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.info-card { height: 100%; }
.hp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.hp-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f2f3f5; }
.hp-label { color: #909399; font-size: 13px; }
.hp-value { color: #303133; font-size: 13px; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.result-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.result-item { border-radius: 8px; overflow: hidden; border: 1px solid #ebeef5; padding: 4px; background: #fafafa; transition: box-shadow .2s; &:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); } }
.log-container { height: 500px; min-height: 200px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code","Fira Code",monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
