<template>
  <div class="app-container">
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-select v-model="evalDatasetId" placeholder="选择评估数据集" filterable style="width:220px" size="small" clearable>
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
          <el-button type="primary" size="small" @click="createDialogVisible = true">创建评估</el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table :ref="tableRef as any" v-loading="loading" row-key="id" :data="data" border stripe>
            <template #empty>
              <el-empty :image-size="80" description="暂无评估记录" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column fixed label="序号" width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column label="评估数据集" prop="eval_dataset_id" width="120" />
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="tagType(row.status)" size="small" effect="plain">{{ tagLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="评估指标" min-width="300">
              <template #default="{ row }">
                <div v-if="row.metrics" style="display:flex;flex-wrap:wrap;gap:4px">
                  <el-tag v-for="(v, k) in row.metrics" :key="k" size="small" style="font-family:monospace;font-size:12px">
                    {{ k }}: {{ typeof v === 'number' ? v.toFixed(4) : v }}
                  </el-tag>
                </div>
                <span v-else style="color:var(--el-text-color-secondary)">--</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_time" label="创建时间" width="170" />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" type="primary" @click="router.push(`/train/eval/${row.id}`)">详情</el-button>
                <el-button v-if="row.status === 'pending'" text size="small" type="success" @click="handleStartEval(row.id)">开始</el-button>
                <el-button v-if="row.status === 'running'" text size="small" type="danger" @click="handleStopEval(row.id)">停止</el-button>
                <el-popconfirm title="确定删除？" @confirm="handleDeleteEval([row.id])">
                  <template #reference><el-button text size="small" type="danger">删除</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <el-dialog v-model="createDialogVisible" title="创建评估" width="500px">
      <el-form label-width="100px">
        <el-form-item label="模型版本">
          <el-select v-model="createForm.modelId" filterable style="width:100%">
            <el-option v-for="m in modelVersions" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="评估数据集">
          <el-select v-model="createForm.evalDatasetId" filterable style="width:100%">
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="imgsz"><el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" /></el-form-item>
        <el-form-item label="batch"><el-input-number v-model="createForm.hyperparams.batch" :min="1" :max="128" /></el-form-item>
        <el-form-item label="conf"><el-input-number v-model="createForm.hyperparams.conf" :min="0.001" :max="1" :step="0.01" /></el-form-item>
        <el-form-item label="iou"><el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateEval">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { IContentConfig } from "@/components/CURD/types";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery { page_no: number; page_size: number; [key: string]: any }

const route = useRoute();
const router = useRouter();
const modelRepoId = Number(route.query.model_repo_id || 0);

const contentRef = ref();
const creating = ref(false);
const evalDatasetId = ref<number | null>(null);
const datasets = ref<any[]>([]);

const createDialogVisible = ref(false);
const modelVersions = ref<any[]>([]);
const createForm = reactive({
  modelId: null as number | null,
  evalDatasetId: null as number | null,
  hyperparams: { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6 },
});

(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
})();

(async () => {
  const r = await TrainAPI.getModelList();
  modelVersions.value = r.data?.data || [];
})();

const allEvals = ref<any[]>([]);

async function reloadEvalData() {
  if (!modelRepoId) return;
  const r = await TrainAPI.getEvalList(modelRepoId);
  allEvals.value = r.data?.data || [];
}

onMounted(async () => {
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
});

function tagType(s: string): "info" | "warning" | "success" | "danger" | undefined {
  return ({ pending: "info", running: "warning", success: "success", failed: "danger" } as Record<string, any>)[s];
}
function tagLabel(s: string) {
  return ({ pending: "待开始", running: "评估中", success: "已完成", failed: "失败" } as any)[s] || s;
}

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  pk: "id",
  cols: [
    { prop: "selection", label: "选择框", show: true },
    { prop: "index", label: "序号", show: true },
    { prop: "eval_dataset_id", label: "评估数据集", show: true },
    { prop: "status", label: "状态", show: true },
    { prop: "metrics", label: "评估指标", show: true },
    { prop: "created_time", label: "创建时间", show: true },
  ],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    await reloadEvalData();
    const data = allEvals.value;
    return {
      total: data.length,
      list: data.slice((params.page_no - 1) * params.page_size, params.page_no * params.page_size),
    };
  },
  initialFetch: false,
  defaultToolbar: ["refresh", "filter"],
});

async function handleCreateEval() {
  if (!createForm.modelId || !createForm.evalDatasetId) {
    ElMessage.warning("请选择模型版本和评估数据集");
    return;
  }
  creating.value = true;
  try {
    await TrainAPI.createEval({
      model_repo_id: modelRepoId,
      model_id: createForm.modelId,
      eval_dataset_id: createForm.evalDatasetId,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success("评估任务已创建");
    createDialogVisible.value = false;
    createForm.modelId = null;
    createForm.evalDatasetId = null;
    createForm.hyperparams = { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6 };
    await reloadEvalData();
    contentRef.value?.fetchPageData({}, true);
  } finally {
    creating.value = false;
  }
}

async function handleStartEval(id: number) {
  await TrainAPI.startEval(id);
  ElMessage.success("评估已开始");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}

async function handleStopEval(id: number) {
  await TrainAPI.stopEval(id);
  ElMessage.success("评估已停止");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}

async function handleDeleteEval(ids: number[]) {
  await TrainAPI.deleteEval(ids);
  ElMessage.success("已删除");
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
}
</script>
