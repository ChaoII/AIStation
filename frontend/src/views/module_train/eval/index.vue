<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="text-base font-semibold">
            模型评估
            <template v-if="modelInfo">
              <el-tag type="primary" size="small" effect="plain" style="margin-left:8px">{{ modelInfo.name }}</el-tag>
              <el-tag size="small" effect="plain">v{{ modelInfo.version }}</el-tag>
            </template>
          </span>
          <div class="header-actions">
            <el-select v-model="evalDatasetId" placeholder="选择评估数据集" filterable style="width:220px" size="small" clearable>
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
        <el-table-column label="评估数据集" prop="eval_dataset_id" width="120" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)" size="small">{{ tagLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评估指标" min-width="300">
          <template #default="{ row }">
            <div v-if="row.metrics" class="metric-list">
              <el-tag v-for="(v, k) in row.metrics" :key="k" size="small" class="metric-item">
                {{ k }}: {{ typeof v === 'number' ? v.toFixed(4) : v }}
              </el-tag>
            </div>
            <span v-else class="text-secondary">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

const route = useRoute();
const modelRepoId = Number(route.query.model_repo_id || 0);

const modelInfo = ref<any>(null);
const evalList = ref<any[]>([]);
const datasets = ref<any[]>([]);
const evalDatasetId = ref<number | null>(null);
const creating = ref(false);
const loading = ref(false);

function tagType(s: string) {
  const m: Record<string, "info" | "warning" | "success" | "danger"> = { pending: "info", running: "warning", success: "success", failed: "danger" };
  return m[s] || "info";
}
function tagLabel(s: string) {
  return { pending: "待开始", running: "评估中", success: "已完成", failed: "失败" }[s] || s;
}

onMounted(async () => {
  if (!modelRepoId) return;
  const [dsRes, modelRes, evalRes] = await Promise.all([
    AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 }),
    TrainAPI.getModelDetail(modelRepoId),
    TrainAPI.getEvalList(modelRepoId),
  ]);
  datasets.value = dsRes.data?.data?.items || [];
  modelInfo.value = modelRes.data?.data;
  evalList.value = evalRes.data?.data || [];
  loading.value = false;
});

async function handleCreateEval() {
  if (!evalDatasetId.value) return;
  creating.value = true;
  try {
    await TrainAPI.createEval({ model_repo_id: modelRepoId, eval_dataset_id: evalDatasetId.value });
    ElMessage.success("评估任务已创建");
    evalDatasetId.value = null;
    const r = await TrainAPI.getEvalList(modelRepoId);
    evalList.value = r.data?.data || [];
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.card-header { display: flex; align-items: center; justify-content: space-between; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.text-base { font-size: 14px; }
.font-semibold { font-weight: 600; }
.text-secondary { color: var(--el-text-color-secondary); }
.metric-list { display: flex; flex-wrap: wrap; gap: 4px; }
.metric-item { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 12px; }
</style>
