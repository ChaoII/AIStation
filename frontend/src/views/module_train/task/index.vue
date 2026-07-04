<template>
  <div class="app-container">
    <div style="margin-bottom:16px">
      <el-button type="primary" @click="showCreate = true">新建训练</el-button>
    </div>
    <el-card>
      <el-table :data="tasks" border stripe style="width:100%">
        <el-table-column prop="name" label="任务名称" min-width="140" />
        <el-table-column prop="framework" label="框架" width="100">
          <template #default="{ row }">
            <el-tag :type="row.framework === 'ultralytics' ? 'success' : 'primary'" size="small">
              {{ row.framework === 'ultralytics' ? 'YOLO' : 'PaddleX' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dataset_id" label="数据集ID" width="90" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :stroke-width="12" :text-inside="true"
              :status="row.status === 'failed' ? 'exception' : row.status === 'success' ? 'success' : undefined" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'running'" type="danger" size="small" @click="handleStop(row.id)">停止</el-button>
            <el-button size="small" @click="router.push('/train/task/' + row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreate" title="新建训练任务" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="如: 缺陷检测v3" />
        </el-form-item>
        <el-form-item label="选择数据集">
          <el-select v-model="form.dataset_id" filterable style="width:100%" placeholder="请选择标注数据集">
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="框架">
          <el-radio-group v-model="form.framework">
            <el-radio value="ultralytics">Ultralytics (YOLO)</el-radio>
            <el-radio value="paddlex">PaddleX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="超参数 (JSON)">
          <el-input v-model="form.hyperparams" type="textarea" :rows="6" placeholder='{"epochs":100,"batch":16,"lr":0.01,"model":"yolo11n.pt"}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">开始训练</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { TrainAPI } from "@/api/module_train";

const router = useRouter();
const tasks = ref<any[]>([]);
const datasets = ref<any[]>([]);
const showCreate = ref(false);
const submitting = ref(false);
const form = ref({ name: "", dataset_id: null, framework: "ultralytics", hyperparams: "{}" });

function statusTag(s: string) {
  return { pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" }[s] || "info";
}
function statusLabel(s: string) {
  return { pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" }[s] || s;
}

onMounted(async () => {
  await loadTasks();
  const dsRes = await import("@/api/module_annotation").then(m => m.AnnotationAPI.getDatasetList({ page_no: 1, page_size: 999 }));
  datasets.value = dsRes.data?.data?.items || [];
});

async function loadTasks() {
  const r = await TrainAPI.getTaskList();
  tasks.value = r.data?.data || [];
}

async function handleCreate() {
  submitting.value = true;
  try {
    const hp = JSON.parse(form.value.hyperparams || "{}");
    await TrainAPI.createTask({ ...form.value, hyperparams: hp });
    showCreate.value = false;
    ElMessage.success("训练任务已创建");
    await loadTasks();
  } catch (e: any) {
    ElMessage.error("JSON 格式错误");
  } finally {
    submitting.value = false;
  }
}

async function handleStop(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(id);
    ElMessage.success("训练已停止");
    await loadTasks();
  } catch {}
}
</script>
