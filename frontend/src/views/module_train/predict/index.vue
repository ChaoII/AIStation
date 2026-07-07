<template>
  <div class="app-container">
    <PageSearch ref="searchRef" :search-config="searchConfig" @query-click="handleQueryClick" @reset-click="handleResetClick" />
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-button type="primary" size="small" v-hasPerm="'module_train:predict:create'" @click="showCreateDialog = true">创建预测</el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table :ref="tableRef as any" v-loading="loading" row-key="id" :data="data" border stripe>
            <template #empty><el-empty :image-size="80" description="暂无预测任务" /></template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="序号" width="60">
              <template #default="scope">{{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}</template>
            </el-table-column>
            <el-table-column label="模型版本" min-width="150">
              <template #default="{ row }">{{ getModelName(row.model_id) }}</template>
            </el-table-column>
            <el-table-column label="图片来源" width="120">
              <template #default="{ row }">{{ row.source_type === 'dataset' ? '数据集' : '上传图片' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="tagType(row.status)" size="small" effect="plain">{{ tagLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_time" width="170" />
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" type="primary" @click="router.push(`/train/predict/${row.id}`)">详情</el-button>
                <el-button v-if="row.status === 'pending'" text size="small" type="success" @click="handleStart(row.id)">开始</el-button>
                <el-button v-if="row.status === 'running'" text size="small" type="danger" @click="handleStop(row.id)">停止</el-button>
                <el-button v-if="row.result_zip_path" text size="small" type="primary" @click="downloadZip(row.result_zip_path)">下载</el-button>
                <el-popconfirm title="确定删除？" @confirm="handleDelete([row.id])">
                  <template #reference><el-button text size="small" type="danger">删除</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="创建预测任务" width="600px" :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item label="模型版本" required>
          <el-select v-model="createForm.modelId" filterable style="width:100%" placeholder="选择模型版本">
            <el-option v-for="m in models" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="图片来源">
          <el-radio-group v-model="createForm.sourceType">
            <el-radio value="dataset">从数据集</el-radio>
            <el-radio value="upload">上传图片</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'dataset'" label="数据集" required>
          <el-select v-model="createForm.sourceDatasetId" filterable style="width:100%" placeholder="选择数据集">
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'upload'" label="图片" required>
          <el-upload ref="uploadRef" list-type="picture-card" :auto-upload="false" multiple>
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
        <el-form-item label="conf">
          <el-input-number v-model="createForm.hyperparams.conf" :min="0.01" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="iou">
          <el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="imgsz">
          <el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery { page_no: number; page_size: number; [key: string]: any }

const router = useRouter();
const searchRef = ref();
const contentRef = ref();
const uploadRef = ref<any>(null);

const showCreateDialog = ref(false);
const creating = ref(false);
const models = ref<any[]>([]);
const datasets = ref<any[]>([]);
const allPredicts = ref<any[]>([]);

const createForm = reactive({
  modelId: null as number | null,
  sourceType: "dataset",
  sourceDatasetId: null as number | null,
  hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640 },
});

onMounted(async () => {
  const [mRes, dsRes] = await Promise.all([
    TrainAPI.getModelList(),
    AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 }),
  ]);
  models.value = mRes.data?.data || [];
  datasets.value = dsRes.data?.data?.items || [];
});

function getModelName(modelId: number) {
  const m = models.value.find((x: any) => x.id === modelId);
  return m ? `${m.name} v${m.version}` : `#${modelId}`;
}

function tagType(s: string) { return ({ pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" } as any)[s] || "info"; }
function tagLabel(s: string) { return ({ pending: "待开始", running: "预测中", success: "已完成", failed: "失败", cancelled: "已取消" } as any)[s] || s; }

async function reloadData() {
  const r = await TrainAPI.getPredictList();
  allPredicts.value = r.data?.data || [];
}

async function handleCreate() {
  if (!createForm.modelId) { ElMessage.warning("请选择模型版本"); return; }
  if (createForm.sourceType === "dataset" && !createForm.sourceDatasetId) { ElMessage.warning("请选择数据集"); return; }
  const pendingFiles = uploadRef.value?.uploadFiles?.map((f: any) => f.raw).filter(Boolean) || [];
  if (createForm.sourceType === "upload" && pendingFiles.length === 0) { ElMessage.warning("请上传图片"); return; }

  creating.value = true;
  try {
    let sourceImages: string[] | undefined;
    if (createForm.sourceType === "upload") {
      const r = await TrainAPI.uploadPredictImages(pendingFiles);
      sourceImages = r.data?.data;
    }

    await TrainAPI.createPredict({
      model_id: createForm.modelId,
      model_repo_id: models.value.find((m: any) => m.id === createForm.modelId)?.id || 0,
      source_type: createForm.sourceType,
      source_dataset_id: createForm.sourceDatasetId,
      source_images: sourceImages,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success("预测任务已创建");
    showCreateDialog.value = false;
    createForm.modelId = null;
    createForm.sourceType = "dataset";
    createForm.sourceDatasetId = null;
    createForm.hyperparams = { conf: 0.25, iou: 0.45, imgsz: 640 };
    if (uploadRef.value) uploadRef.value.uploadFiles = [];
    await reloadData();
    contentRef.value?.fetchPageData({}, true);
  } finally {
    creating.value = false;
  }
}

async function handleStart(id: number) {
  await TrainAPI.startPredict(id);
  ElMessage.success("预测已开始");
  await reloadData();
  contentRef.value?.fetchPageData({}, true);
}

async function handleStop(id: number) {
  await TrainAPI.stopPredict(id);
  ElMessage.success("预测已停止");
  await reloadData();
  contentRef.value?.fetchPageData({}, true);
}

function downloadZip(url: string) {
  window.open(url, "_blank");
}

async function handleDelete(ids: number[]) {
  await TrainAPI.deletePredict(ids);
  ElMessage.success("已删除");
  await reloadData();
  contentRef.value?.fetchPageData({}, true);
}

const searchConfig = reactive<ISearchConfig>({
  colon: true,
  isExpandable: false,
  form: { labelWidth: "auto" },
  formItems: [
    { prop: "name", label: "任务名称", type: "input", attrs: { placeholder: "请输入", clearable: true } },
  ],
});

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  pk: "id",
  cols: [
    { prop: "selection", label: "选择框", show: true },
    { prop: "index", label: "序号", show: true },
    { prop: "model_id", label: "模型版本", show: true },
    { prop: "source_type", label: "图片来源", show: true },
    { prop: "status", label: "状态", show: true },
    { prop: "created_time", label: "创建时间", show: true },
  ],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    await reloadData();
    const data = allPredicts.value;
    return { total: data.length, list: data.slice((params.page_no - 1) * params.page_size, params.page_no * params.page_size) };
  },
  initialFetch: false,
  defaultToolbar: ["refresh", "filter"],
});

function handleQueryClick() {
  contentRef.value?.fetchPageData({}, true);
}
function handleResetClick() {
  contentRef.value?.fetchPageData({}, true);
}
</script>
