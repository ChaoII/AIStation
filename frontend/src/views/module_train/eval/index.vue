<template>
  <div class="app-container">
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="eval-header">
          <el-button text @click="router.back()">← 返回</el-button>
          <span class="text-base font-semibold">模型评估</span>
          <el-tag v-if="modelInfo" type="primary" size="small" effect="plain">{{ modelInfo.name }}</el-tag>
          <el-tag v-if="modelInfo" size="small" effect="plain">v{{ modelInfo.version }}</el-tag>
        </div>
      </template>
      <div v-if="modelInfo" class="model-summary">
        <el-row :gutter="16">
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">框架</span>
              <span class="summary-value">{{ modelInfo.framework === 'ultralytics' ? 'Ultralytics' : 'PaddleX' }}</span>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">状态</span>
              <el-tag :type="modelInfo.status === 'released' ? 'success' : 'info'" size="small">
                {{ ({ draft: '草稿', released: '已发布', archived: '已归档' } as any)[modelInfo.status] || modelInfo.status }}
              </el-tag>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">最新指标</span>
              <span class="summary-value">{{ modelInfo.metrics ? (modelInfo.metrics.mAP || '--') : '--' }}</span>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="summary-item">
              <span class="summary-label">存储路径</span>
              <span class="summary-value text-ellipsis" :title="modelInfo.storage_path">{{ modelInfo.storage_path || '--' }}</span>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="eval-toolbar">
          <span class="text-base font-semibold">评估记录</span>
          <div class="eval-actions">
            <el-select v-model="evalDatasetId" placeholder="选择评估数据集" filterable style="width:240px" size="small">
              <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
            </el-select>
            <el-button type="primary" size="small" :disabled="!evalDatasetId" :loading="creating" @click="handleCreateEval">
              创建评估
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="evalList" border stripe style="width:100%" v-loading="loading">
        <template #empty>
          <el-empty :image-size="80" description="暂无评估记录" />
        </template>
        <el-table-column label="序号" type="index" width="60" align="center" />
        <el-table-column prop="eval_dataset_id" label="评估数据集" width="120">
          <template #default="{ row }">
            <span>{{ datasetName(row.eval_dataset_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评估指标" min-width="320">
          <template #default="{ row }">
            <div v-if="row.metrics" class="metrics-display">
              <el-tag v-for="(v, k) in row.metrics" :key="k" size="small" class="metric-tag">
                {{ k }}: {{ typeof v === 'number' ? v.toFixed(4) : v }}
              </el-tag>
            </div>
            <span v-else class="text-gray-400">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="log" label="评估日志" min-width="160">
          <template #default="{ row }">
            <span v-if="row.log" class="text-ellipsis log-preview" :title="row.log">{{ row.log.slice(0, 60) }}{{ row.log.length > 60 ? '...' : '' }}</span>
            <span v-else class="text-gray-400">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

const route = useRoute();
const router = useRouter();
const modelRepoId = Number(route.query.model_repo_id || 0);

const modelInfo = ref<any>(null);
const evalList = ref<any[]>([]);
const datasets = ref<any[]>([]);
const evalDatasetId = ref<number | null>(null);
const creating = ref(false);
const loading = ref(false);

const datasetMap = computed(() => {
  const m: Record<number, string> = {};
  for (const ds of datasets.value) m[ds.id] = ds.name;
  return m;
});

function datasetName(id: number) {
  return datasetMap.value[id] || `数据集#${id}`;
}

function statusTag(s: string) {
  return ({ pending: "info", running: "warning", success: "success", failed: "danger" } as Record<string, "info" | "warning" | "success" | "danger">)[s] || "info";
}

function statusLabel(s: string) {
  return { pending: "待开始", running: "评估中", success: "已完成", failed: "失败" }[s] || s;
}

async function loadEvalList() {
  loading.value = true;
  try {
    const r = await TrainAPI.getEvalList(modelRepoId);
    evalList.value = r.data?.data || [];
  } finally {
    loading.value = false;
  }
}

async function loadModelInfo() {
  if (!modelRepoId) return;
  const r = await TrainAPI.getModelDetail(modelRepoId);
  modelInfo.value = r.data?.data;
}

onMounted(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
  await Promise.all([loadModelInfo(), loadEvalList()]);
});

async function handleCreateEval() {
  if (!evalDatasetId.value) return;
  creating.value = true;
  try {
    await TrainAPI.createEval({ model_repo_id: modelRepoId, eval_dataset_id: evalDatasetId.value });
    ElMessage.success("评估任务已创建");
    evalDatasetId.value = null;
    await loadEvalList();
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.eval-header { display: flex; align-items: center; gap: 12px; }
.eval-toolbar { display: flex; align-items: center; justify-content: space-between; }
.eval-actions { display: flex; align-items: center; gap: 8px; }
.mb-4 { margin-bottom: 16px; }
.text-base { font-size: 14px; }
.font-semibold { font-weight: 600; }
.text-gray-400 { color: #909399; }
.text-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; max-width: 100%; }
.log-preview { font-family: monospace; font-size: 12px; color: #606266; }

.model-summary { padding: 4px 0; }
.summary-item { display: flex; flex-direction: column; gap: 4px; }
.summary-label { font-size: 12px; color: #909399; }
.summary-value { font-size: 14px; font-weight: 500; color: #303133; }

.metrics-display { display: flex; flex-wrap: wrap; gap: 4px; }
.metric-tag { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 12px; }
</style>
