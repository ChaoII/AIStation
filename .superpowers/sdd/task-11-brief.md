# Task 11: 前端预测页面 — 列表 + 详情

## 要创建的文件
- Create: `frontend/src/views/module_train/predict/index.vue`
- Create: `frontend/src/views/module_train/predict/detail.vue`

## 要求

### A. 创建 `predict/index.vue`

```vue
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
          <el-upload ref="uploadRef" list-type="picture-card" :auto-upload="false" multiple :on-change="handleUploadChange">
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
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import type { IContentConfig } from "@/components/CURD/types";
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
const uploadFiles = ref<File[]>([]);

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

function handleUploadChange(file: any) {
  uploadFiles.value = uploadRef.value?.uploadFiles?.map((f: any) => f.raw).filter(Boolean) || [];
}

async function reloadData() {
  const r = await TrainAPI.getPredictList();
  allPredicts.value = r.data?.data || [];
}

async function handleCreate() {
  if (!createForm.modelId) { ElMessage.warning("请选择模型版本"); return; }
  if (createForm.sourceType === "dataset" && !createForm.sourceDatasetId) { ElMessage.warning("请选择数据集"); return; }
  if (createForm.sourceType === "upload" && uploadFiles.value.length === 0) { ElMessage.warning("请上传图片"); return; }

  creating.value = true;
  try {
    let sourceImages: string[] | undefined;
    if (createForm.sourceType === "upload") {
      const r = await TrainAPI.uploadPredictImages(uploadFiles.value);
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
    uploadFiles.value = [];
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

const searchConfig = {
  formItems: [
    { type: "input", prop: "name", label: "任务名称", placeholder: "请输入" },
  ],
};

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
```

### B. 创建 `predict/detail.vue`

```vue
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
```

## 前置条件
- Directory `frontend/src/views/module_train/predict/` 已创建
- `TrainAPI` 已有 `getModelList`, `getPredictList`, `getPredictDetail`, `startPredict`, `stopPredict`, `deletePredict`, `uploadPredictImages`, `createPredict`（Task 9）
- `AnnotationAPI.getDatasetList` 已有
- `CrudToolbarRight` 和 `IContentConfig` 已有

## 提交信息
```bash
git add frontend/src/views/module_train/predict/
git commit -m "feat(train): add predict list and detail pages"
```
