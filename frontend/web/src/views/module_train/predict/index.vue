<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      ref="searchBarRef"
      v-model="searchForm"
      :items="searchItems"
      :rules="searchBarRules"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :default-expanded="false"
      @search="handleSearch"
      @reset="onResetSearch"
    />

    <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <FaTableHeaderLeft
            :remove-ids="selectedIds"
            :perm-create="['module_train:predict:create']"
            :perm-delete="['module_train:predict:delete']"
            :delete-loading="batchDeleting"
            @add="showCreateDialog = true"
            @delete="handleBatchDelete"
          />
        </template>
      </FaTableHeader>

      <FaTable
        ref="faTableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @selection-change="onTableSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <ElDialog v-model="showCreateDialog" title="创建预测任务" width="600px" :close-on-click-modal="false">
      <ElForm label-width="100px">
        <ElFormItem label="模型仓库" required>
          <ElSelect v-model="createForm.modelRepoId" filterable style="width:100%" placeholder="选择模型仓库" @change="onRepoChange">
            <ElOption v-for="r in repos" :key="r.id" :label="r.name" :value="r.id!" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="模型版本" required>
          <ElSelect v-model="createForm.modelId" filterable style="width:100%" placeholder="选择模型版本" :disabled="!createForm.modelRepoId">
            <ElOption v-for="v in versionOptions" :key="v.id" :label="`${v.name} v${v.version}`" :value="v.id!" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="图片来源">
          <ElRadioGroup v-model="createForm.sourceType">
            <ElRadio value="dataset">从数据集</ElRadio>
            <ElRadio value="upload">上传图片</ElRadio>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem v-if="createForm.sourceType === 'dataset'" label="数据集" required>
          <ElSelect v-model="createForm.sourceDatasetId" filterable style="width:100%" placeholder="选择数据集">
            <ElOption v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem v-if="createForm.sourceType === 'upload'" label="图片" required>
          <ElUpload ref="uploadRef" list-type="picture-card" :auto-upload="false" multiple @change="onUploadChange">
            <ElIcon><Plus /></ElIcon>
          </ElUpload>
        </ElFormItem>
        <ElFormItem label="conf">
          <ElInputNumber v-model="createForm.hyperparams.conf" :min="0.01" :max="1" :step="0.05" />
        </ElFormItem>
        <ElFormItem label="iou">
          <ElInputNumber v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" />
        </ElFormItem>
        <ElFormItem label="imgsz">
          <ElInputNumber v-model="createForm.hyperparams.imgsz" :min="32" :step="32" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showCreateDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="handleCreate">创建</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox, ElTag, ElProgress } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { useTable } from "@/hooks/core/useTable";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import { TrainAPI, type TrainPredictTable, type TablePageQuery, type TrainModelRepoTable, type TrainModelVersionTable } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

defineOptions({ name: "TrainPredict", inheritAttrs: false });

const route = useRoute();
const router = useRouter();
const { hasAuth } = useAuth();
const qRepoId = Number(route.query.model_repo_id || 0);
const qVersionId = Number(route.query.model_id || 0);

const showCreateDialog = ref(false);
const creating = ref(false);
const repos = ref<TrainModelRepoTable[]>([]);
const versionOptions = ref<TrainModelVersionTable[]>([]);
const versionLookup = reactive<Record<number, { name?: string; version?: string }>>({});
const datasets = ref<any[]>([]);
const pendingFiles = ref<File[]>([]);
const uploadRef = ref<any>(null);

const createForm = reactive({
  modelRepoId: null as number | null,
  modelId: null as number | null,
  sourceType: "dataset",
  sourceDatasetId: null as number | null,
  hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640, device: "0" },
});

Promise.all([TrainAPI.listModelRepos({ page_no: 1, page_size: 100 }), AnnotationAPI.listDataset({ page_no: 1, page_size: 100 })])
  .then(([mRes, dsRes]) => {
    repos.value = mRes.data?.data?.items || [];
    datasets.value = dsRes.data?.data?.items || [];
  })
  .catch(() => {});

async function onRepoChange(repoId: number | null) {
  versionOptions.value = [];
  createForm.modelId = null;
  if (!repoId) return;
  try {
    const r = await TrainAPI.listModelVersions(repoId);
    versionOptions.value = r.data?.data || [];
    versionOptions.value.forEach(v => { if (v.id) versionLookup[v.id] = { name: v.name, version: v.version }; });
  } catch {
    /* */
  }
}

function getModelName(modelId?: number) {
  const v = versionLookup[modelId || 0];
  if (!v) return `#${modelId}`;
  return v.name ? `${v.name} v${v.version}` : `v${v.version}`;
}

function buildVersionLookup(rows: TrainPredictTable[]) {
  const repoIds = new Set<number>();
  rows.forEach(r => { if (r.model_repo_id) repoIds.add(r.model_repo_id); });
  repoIds.forEach(repoId => {
    TrainAPI.listModelVersions(repoId)
      .then(r => {
        (r.data?.data || []).forEach(v => { if (v.id) versionLookup[v.id] = { name: v.name, version: v.version }; });
      })
      .catch(() => {});
  });
}

function statusTag(s?: string) {
  const map: Record<string, { type: "info" | "success" | "warning" | "danger"; text: string }> = {
    pending: { type: "info", text: "待开始" },
    running: { type: "warning", text: "预测中" },
    success: { type: "success", text: "已完成" },
    failed: { type: "danger", text: "失败" },
    cancelled: { type: "info", text: "已取消" },
  };
  const c = map[s || ""] || { type: "info" as const, text: s || "—" };
  return h(ElTag, { type: c.type }, () => c.text);
}
function progressCell(row: TrainPredictTable) {
  return h(ElProgress, {
    percentage: row.progress || 0,
    "stroke-width": 14,
    "text-inside": true,
    status: row.status === "failed" ? "exception" : row.status === "success" ? "success" : undefined,
  });
}

function onUploadChange(_file: any, fileList: any[]) {
  pendingFiles.value = fileList.map(f => f.raw).filter(Boolean);
}

async function handleCreate() {
  if (!createForm.modelRepoId) { ElMessage.warning("请选择模型仓库"); return; }
  if (!createForm.modelId) { ElMessage.warning("请选择模型版本"); return; }
  if (createForm.sourceType === "dataset" && !createForm.sourceDatasetId) { ElMessage.warning("请选择数据集"); return; }
  if (createForm.sourceType === "upload" && pendingFiles.value.length === 0) { ElMessage.warning("请上传图片"); return; }
  creating.value = true;
  try {
    let sourceImages: string[] | undefined;
    if (createForm.sourceType === "upload") {
      const formData = new FormData();
      pendingFiles.value.forEach(f => formData.append("files", f));
      const r = await TrainAPI.uploadPredictImages(formData);
      sourceImages = r.data?.data;
    }
    await TrainAPI.createPredict({
      model_repo_id: createForm.modelRepoId ?? undefined,
      model_id: createForm.modelId ?? undefined,
      source_type: createForm.sourceType,
      source_dataset_id: createForm.sourceDatasetId ?? undefined,
      source_images: sourceImages,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success("预测任务已创建");
    showCreateDialog.value = false;
    createForm.modelRepoId = null;
    createForm.modelId = null;
    createForm.sourceType = "dataset";
    createForm.sourceDatasetId = null;
    createForm.hyperparams = { conf: 0.25, iou: 0.45, imgsz: 640, device: "0" };
    versionOptions.value = [];
    pendingFiles.value = [];
    if (uploadRef.value) uploadRef.value.uploadFiles = [];
    await refreshData();
  } finally {
    creating.value = false;
  }
}

onMounted(async () => {
  if (qRepoId) {
    createForm.modelRepoId = qRepoId;
    await onRepoChange(qRepoId);
    if (qVersionId && versionOptions.value.some(v => v.id === qVersionId)) createForm.modelId = qVersionId;
    showCreateDialog.value = true;
  }
});

function buildRowActions(
  row: TrainPredictTable,
  ctx: { onStart: (id: number) => void; onStop: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    {
      key: "detail",
      label: "详情",
      artType: "view",
      icon: "ri:eye-line",
      perm: "module_train:predict:query",
      run: () => router.push(`/train/predict/${row.id}`),
    },
  ];
  if (row.status === "pending") {
    actions.unshift({
      key: "start",
      label: "开始预测",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_train:predict:create",
      run: () => ctx.onStart(row.id!),
    });
  }
  if (row.status === "running") {
    actions.unshift({
      key: "stop",
      label: "停止",
      artType: "view",
      icon: "ri:stop-circle-line",
      iconColor: "var(--el-color-danger)",
      perm: "module_train:predict:create",
      run: () => ctx.onStop(row.id!),
    });
  }
  actions.push({
    key: "delete",
    label: "删除",
    artType: "delete",
    icon: "ri:delete-bin-4-line",
    perm: "module_train:predict:delete",
    run: () => ctx.onDelete(row.id!),
  });
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; framework?: string; status?: string }>({
  name: undefined, framework: undefined, status: undefined,
});
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "模型名称", key: "name", type: "input", placeholder: "请输入模型名称", clearable: true, span: 6 },
  {
    label: "框架",
    key: "framework",
    type: "select",
    props: { placeholder: "请选择框架", clearable: true, options: [
      { label: "Ultralytics", value: "ultralytics" },
      { label: "PaddleX", value: "paddlex" },
    ] },
    span: 6,
  },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: { placeholder: "请选择状态", clearable: true, options: [
      { label: "待开始", value: "pending" },
      { label: "预测中", value: "running" },
      { label: "已完成", value: "success" },
      { label: "失败", value: "failed" },
      { label: "已取消", value: "cancelled" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainPredictTable>();

async function startPredict(id: number) {
  try {
    await ElMessageBox.confirm("确定开始预测？", "提示", { type: "info" });
    await TrainAPI.startPredict(id);
    ElMessage.success("预测已开始");
    await refreshData();
  } catch {
    // cancel
  }
}
async function stopPredict(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该预测？", "提示", { type: "warning" });
    await TrainAPI.stopPredict(id);
    ElMessage.success("预测已停止");
    await refreshData();
  } catch {
    // cancel
  }
}
async function deletePredictRow(id: number) {
  try {
    await confirmDelete();
    await TrainAPI.deletePredict([id]);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  }
}
async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    await TrainAPI.deletePredict(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

const opCtx = {
  onStart: startPredict,
  onStop: stopPredict,
  onDelete: deletePredictRow,
};

const { columns, columnChecks, data, loading, pagination, searchParams, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listPredict,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainPredictTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "model_version", label: "模型版本", minWidth: 150, formatter: (row: TrainPredictTable) => getModelName(row.model_id) },
      { prop: "framework", label: "框架", width: 100, formatter: (row: TrainPredictTable) => h(ElTag, { type: row.framework === "ultralytics" ? "success" : "primary" }, () => row.framework === "ultralytics" ? "YOLO" : "PaddleX") },
      { prop: "source_type", label: "图片来源", width: 100, formatter: (row: TrainPredictTable) => row.source_type === "dataset" ? "数据集" : "上传图片" },
      { prop: "status", label: "状态", width: 100, formatter: (row: TrainPredictTable) => statusTag(row.status) },
      { prop: "progress", label: "进度", width: 180, formatter: (row: TrainPredictTable) => progressCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 220,
        fixed: "right",
        align: "right",
        formatter: (row: TrainPredictTable) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
  hooks: { onSuccess: (rows) => buildVersionLookup(rows as TrainPredictTable[]) },
});

function handleSearch(params: { name?: string; framework?: string; status?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, framework: undefined, status: undefined };
  void resetSearchParams();
}
</script>
