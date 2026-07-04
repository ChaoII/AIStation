<template>
  <div class="app-container">
    <el-card>
      <div style="margin-bottom:16px">
        <el-button type="primary" @click="showCreate = true">新建模型</el-button>
      </div>
      <el-table :data="models" border stripe style="width:100%">
        <el-table-column prop="name" label="模型名称" min-width="160" />
        <el-table-column prop="framework" label="框架" width="120">
          <template #default="{ row }">
            <el-tag :type="row.framework === 'ultralytics' ? 'success' : 'primary'" size="small">
              {{ row.framework === 'ultralytics' ? 'Ultralytics' : 'PaddleX' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="metrics" label="最新指标" width="180">
          <template #default="{ row }">
            <span v-if="row.metrics">{{ row.metrics.mAP || '-' }}</span>
            <span v-else class="text-gray-400">--</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'released' ? 'success' : 'info'" size="small">
              {{ { draft: '草稿', released: '已发布', archived: '已归档' }[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="handleTrain(row)">训练</el-button>
            <el-button text size="small" @click="handleEval(row)">评估</el-button>
            <el-button text size="small" type="success" @click="handleDeploy(row)">部署</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreate" title="新建模型" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="模型名称">
          <el-input v-model="form.name" placeholder="如: 缺陷检测" />
        </el-form-item>
        <el-form-item label="框架">
          <el-select v-model="form.framework" style="width:100%">
            <el-option label="Ultralytics" value="ultralytics" />
            <el-option label="PaddleX" value="paddlex" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { TrainAPI } from "@/api/module_train";

const router = useRouter();
const models = ref<any[]>([]);
const showCreate = ref(false);
const form = reactive({ name: "", framework: "ultralytics" });

onMounted(async () => {
  const r = await TrainAPI.getModelList();
  models.value = r.data?.data || [];
});

async function handleCreate() {
  await TrainAPI.createModel(form);
  showCreate.value = false;
  ElMessage.success("模型已创建");
  const r = await TrainAPI.getModelList();
  models.value = r.data?.data || [];
}

function handleTrain(row: any) {
  router.push(`/train/task/create?model_id=${row.id}&framework=${row.framework}`);
}

function handleEval(row: any) {
  router.push(`/train/eval?model_repo_id=${row.id}`);
}

function handleDeploy(row: any) {
  ElMessage.info("部署功能即将上线");
}
</script>
