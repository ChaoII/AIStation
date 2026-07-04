<template>
  <div class="app-container">
    <el-card>
      <template #header>
        <div style="display:flex;align-items:center;gap:12px">
          <el-button text @click="router.back()">← 返回</el-button>
          <span style="font-weight:600">模型评估</span>
          <span class="text-sm text-gray-400">模型ID: {{ modelRepoId }}</span>
        </div>
      </template>
      <div style="margin-bottom:16px;display:flex;gap:12px;align-items:center">
        <el-select v-model="evalDatasetId" placeholder="选择评估数据集" filterable style="width:280px">
          <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
        </el-select>
        <el-button type="primary" :disabled="!evalDatasetId" :loading="creating" @click="handleCreateEval">创建评估</el-button>
      </div>
      <el-table :data="evals" border stripe style="width:100%">
        <el-table-column prop="eval_dataset_id" label="评估数据集ID" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'running' ? 'warning' : 'info'" size="small">
              {{ { pending: '待开始', running: '评估中', success: '已完成', failed: '失败' }[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评估指标" min-width="240">
          <template #default="{ row }">
            <pre v-if="row.metrics" style="margin:0;font-size:12px;white-space:pre-wrap">{{ JSON.stringify(row.metrics, null, 2) }}</pre>
            <span v-else class="text-gray-400">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const modelRepoId = Number(route.query.model_repo_id || 0);
const evals = ref<any[]>([]);
const datasets = ref<any[]>([]);
const evalDatasetId = ref<number | null>(null);
const creating = ref(false);

onMounted(async () => {
  if (modelRepoId) {
    const r = await TrainAPI.getEvalList(modelRepoId);
    evals.value = r.data?.data || [];
  }
  const dsRes = await import("@/api/module_annotation").then(m => m.AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 }));
  datasets.value = dsRes.data?.data?.items || [];
});

async function handleCreateEval() {
  if (!evalDatasetId.value) return;
  creating.value = true;
  try {
    await TrainAPI.createEval({ model_repo_id: modelRepoId, eval_dataset_id: evalDatasetId.value });
    ElMessage.success("评估任务已创建");
    const r = await TrainAPI.getEvalList(modelRepoId);
    evals.value = r.data?.data || [];
  } finally {
    creating.value = false;
  }
}
</script>
