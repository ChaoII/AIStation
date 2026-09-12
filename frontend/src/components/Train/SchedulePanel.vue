<template>
  <div class="schedule-panel">
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建定时计划</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
      <el-table-column label="框架" prop="framework" width="120" />
      <el-table-column label="cron" prop="cron_expr" min-width="140" />
      <el-table-column label="启用" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上次运行" prop="last_run_at" min-width="170" />
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <EnhancedDialog
      v-model="dialogVisible"
      :title="form.id ? '编辑定时计划' : '新建定时计划'"
      append-to-body
      width="680px"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" placeholder="如：每晚 2 点训练" />
        </el-form-item>
        <el-form-item label="框架">
          <el-radio-group v-model="form.framework">
            <el-radio value="ultralytics">Ultralytics</el-radio>
            <el-radio value="paddlex">PaddleX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数据集" required>
          <el-select v-model="form.dataset_id" filterable style="width: 100%" placeholder="选择数据集"
            @visible-change="(v: boolean) => v && loadDatasets()"
          >
            <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="cron 表达式" required>
          <div class="cron-row">
            <el-input v-model="form.cron_expr" placeholder="分 时 日 月 周，如 0 2 * * *" />
            <el-popover :width="520" trigger="click">
              <template #reference>
                <el-button>可视化</el-button>
              </template>
              <vue3CronPlus :expression="form.cron_expr" i18n="cn" @change="onCronChange" />
            </el-popover>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { vue3CronPlus } from "vue3-cron-plus";
import "vue3-cron-plus/dist/index.css";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";
import { cachedOptions } from "@/composables/useOptions";

const rows = ref<any[]>([]);
const datasets = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);

const emptyForm = () => ({
  id: 0,
  name: "",
  framework: "ultralytics",
  dataset_id: null as number | null,
  cron_expr: "0 2 * * *",
  enabled: true,
});
const form = reactive<any>(emptyForm());

function onCronChange(expr: any) {
  form.cron_expr = typeof expr === "string" ? expr : expr?.cron || form.cron_expr;
}

async function load() {
  loading.value = true;
  try {
    const res = await TrainAPI.getTrainScheduleList();
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

let datasetsLoaded = false;
async function loadDatasets() {
  if (datasetsLoaded) return;
  datasetsLoaded = true;
  try {
    datasets.value = await cachedOptions(
      "annotation:datasets",
      async () => (await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    datasetsLoaded = false;
  }
}

function openCreate() {
  Object.assign(form, emptyForm());
  loadDatasets();
  dialogVisible.value = true;
}

function openEdit(row: any) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    framework: row.framework || "ultralytics",
    dataset_id: row.dataset_id,
    cron_expr: row.cron_expr,
    enabled: row.enabled !== false,
  });
  loadDatasets();
  dialogVisible.value = true;
}

async function submit() {
  if (!form.name || !form.dataset_id || !form.cron_expr) {
    ElMessage.warning("请填写名称、数据集与 cron 表达式");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      framework: form.framework,
      dataset_id: form.dataset_id,
      cron_expr: form.cron_expr,
      enabled: form.enabled,
    };
    if (form.id) await TrainAPI.updateTrainSchedule(form.id, payload);
    else await TrainAPI.createTrainSchedule(payload);
    dialogVisible.value = false;
    await load();
  } finally {
    saving.value = false;
  }
}

async function remove(id: number) {
  await TrainAPI.deleteTrainSchedule([id]);
  await load();
}

onMounted(async () => {
  await load();
});

defineExpose({ load });
</script>

<style scoped>
.schedule-panel {
  padding: 8px 0;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.cron-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
</style>
