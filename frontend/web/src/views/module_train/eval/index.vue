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
            :perm-create="['module_train:eval:create']"
            :perm-delete="['module_train:eval:delete']"
            :delete-loading="batchDeleting"
            @add="handleOpenDialog('create')"
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

    <FaDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="500px"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      @cancel="handleCloseDialog"
      @confirm="handleSubmit"
    >
      <FaForm
        :key="formRenderKey"
        scrollbar
        max-height="70vh"
        ref="dataFormRef"
        v-model="formData"
        :items="formItems"
        :rules="rules"
        label-suffix=":"
        :label-width="120"
        label-position="right"
        :span="24"
        :gutter="16"
        :show-reset="false"
        :show-submit="false"
      />
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox, ElTag, ElProgress } from "element-plus";
import { useTable } from "@/hooks/core/useTable";
import { useCrudDialog } from "@/hooks/core/useCrudDialog";
import { useCrudForm } from "@/hooks/core/useCrudForm";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { FormItem } from "@/components/forms/fa-form/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import { TrainAPI, type TrainEvalTable, type TrainEvalForm, type TablePageQuery, type TrainModelRepoTable, type TrainModelVersionTable } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

defineOptions({ name: "TrainEval", inheritAttrs: false });

const route = useRoute();
const router = useRouter();
const { hasAuth } = useAuth();
const modelRepoId = Number(route.query.model_repo_id || 0);
const modelVersionId = Number(route.query.model_id || 0);
let presetVersionId = modelVersionId || 0;

const datasets = ref<any[]>([]);
const modelRepos = ref<TrainModelRepoTable[]>([]);
const versionOptions = ref<TrainModelVersionTable[]>([]);
const versionLookup = reactive<Record<number, { name?: string; version?: string }>>({});
AnnotationAPI.listDataset({ page_no: 1, page_size: 100 })
  .then(r => { datasets.value = r.data?.data?.items || []; })
  .catch(() => {});
TrainAPI.listModelRepos({ page_no: 1, page_size: 100 })
  .then(r => { modelRepos.value = r.data?.data?.items || []; })
  .catch(() => {});

function getModelName(modelId?: number) {
  const v = versionLookup[modelId || 0];
  if (!v) return `#${modelId}`;
  return v.name ? `${v.name} v${v.version}` : `v${v.version}`;
}

async function loadVersionsForRepo(repoId: number) {
  versionOptions.value = [];
  formData.value.model_id = undefined;
  if (!repoId) return;
  try {
    const r = await TrainAPI.listModelVersions(repoId);
    versionOptions.value = r.data?.data || [];
    versionOptions.value.forEach(v => { if (v.id) versionLookup[v.id] = { name: v.name, version: v.version }; });
    if (presetVersionId && versionOptions.value.some(v => v.id === presetVersionId)) {
      formData.value.model_id = presetVersionId;
      presetVersionId = 0;
    }
  } catch {
    /* */
  }
}

function buildVersionLookup(rows: TrainEvalTable[]) {
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
    running: { type: "warning", text: "评估中" },
    success: { type: "success", text: "已完成" },
    failed: { type: "danger", text: "失败" },
    cancelled: { type: "info", text: "已取消" },
  };
  const c = map[s || ""] || { type: "info" as const, text: s || "—" };
  return h(ElTag, { type: c.type }, () => c.text);
}
function progressCell(row: TrainEvalTable) {
  return h(ElProgress, {
    percentage: row.progress || 0,
    "stroke-width": 14,
    "text-inside": true,
    status: row.status === "failed" ? "exception" : row.status === "success" ? "success" : undefined,
  });
}
function metricsCell(row: TrainEvalTable) {
  const m = row.metrics as any;
  if (!m) return h("span", { style: "color:var(--el-text-color-placeholder)" }, "—");
  const parts = ["precision", "recall", "map50", "map5095"].filter(k => m[k] != null).map(k => `${k}=${Number(m[k]).toFixed(4)}`);
  return h("span", { style: "font-family:monospace;font-size:12px" }, parts.join(" "));
}

function buildRowActions(
  row: TrainEvalTable,
  ctx: { onStart: (id: number) => void; onStop: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    {
      key: "detail",
      label: "详情",
      artType: "view",
      icon: "ri:eye-line",
      perm: "module_train:eval:query",
      run: () => router.push(`/train/eval/${row.id}`),
    },
  ];
  if (row.status === "pending") {
    actions.unshift({
      key: "start",
      label: "开始评估",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_train:eval:create",
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
      perm: "module_train:eval:create",
      run: () => ctx.onStop(row.id!),
    });
  }
  actions.push({
    key: "delete",
    label: "删除",
    artType: "delete",
    icon: "ri:delete-bin-4-line",
    perm: "module_train:eval:delete",
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
      { label: "评估中", value: "running" },
      { label: "已完成", value: "success" },
      { label: "失败", value: "failed" },
      { label: "已取消", value: "cancelled" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainEvalTable>();

async function startEval(id: number) {
  try {
    await ElMessageBox.confirm("确定开始评估？", "提示", { type: "info" });
    await TrainAPI.startEval(id);
    ElMessage.success("评估已开始");
    await refreshData();
  } catch {
    // cancel
  }
}
async function stopEval(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该评估？", "提示", { type: "warning" });
    await TrainAPI.stopEval(id);
    ElMessage.success("评估已停止");
    await refreshData();
  } catch {
    // cancel
  }
}
async function deleteEvalRow(id: number) {
  try {
    await confirmDelete();
    await TrainAPI.deleteEval([id]);
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
    await TrainAPI.deleteEval(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

const { dialogVisible } = useCrudDialog();
const formData = ref<TrainEvalForm>({
  model_repo_id: modelRepoId || undefined,
  model_id: modelVersionId || undefined,
  eval_dataset_id: undefined,
  hyperparams: { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6, device: "0" },
});
const initialFormData: TrainEvalForm = {
  model_repo_id: modelRepoId || undefined,
  model_id: modelVersionId || undefined,
  eval_dataset_id: undefined,
  hyperparams: { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6, device: "0" },
};

watch(
  () => formData.value.model_repo_id,
  (repoId) => {
    loadVersionsForRepo(repoId || 0);
  },
  { immediate: true }
);

const rules = reactive({
  model_repo_id: [{ required: true, message: "请选择模型仓库", trigger: "change" }],
  model_id: [{ required: true, message: "请选择模型版本", trigger: "change" }],
  eval_dataset_id: [{ required: true, message: "请选择评估数据集", trigger: "change" }],
});

const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<TrainEvalForm>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: formRenderKey,
  createApi: async (form) => {
    await TrainAPI.createEval({ ...form });
  },
  titles: { create: "创建评估" },
  onCreateSuccess: async () => { await refreshCreate(); },
});

const formItems = computed<FormItem[]>(() => [
  {
    label: "模型仓库",
    key: "model_repo_id",
    type: "select",
    span: 24,
    props: { placeholder: "请选择模型仓库", filterable: true, options: modelRepos.value.map(r => ({ label: r.name, value: r.id })) },
  },
  {
    label: "模型版本",
    key: "model_id",
    type: "select",
    span: 24,
    props: { placeholder: "请选择模型版本", filterable: true, clearable: true, options: versionOptions.value.map(v => ({ label: `${v.name} v${v.version}`, value: v.id })) },
  },
  {
    label: "评估数据集",
    key: "eval_dataset_id",
    type: "select",
    span: 24,
    props: { placeholder: "请选择数据集", filterable: true, options: datasets.value.map(d => ({ label: d.name, value: d.id })) },
  },
  { label: "imgsz", key: "hyperparams.imgsz", type: "number", span: 12, props: { min: 32, step: 32, style: { width: "100%" } } },
  { label: "batch", key: "hyperparams.batch", type: "number", span: 12, props: { min: 1, max: 128, style: { width: "100%" } } },
  { label: "conf", key: "hyperparams.conf", type: "number", span: 12, props: { min: 0.001, max: 1, step: 0.01, precision: 3, style: { width: "100%" } } },
  { label: "iou", key: "hyperparams.iou", type: "number", span: 12, props: { min: 0.1, max: 1, step: 0.05, precision: 2, style: { width: "100%" } } },
  { label: "GPU 设备", key: "hyperparams.device", type: "input", span: 24, props: { placeholder: "如: 0" } },
]);

const opCtx = {
  onStart: startEval,
  onStop: stopEval,
  onDelete: deleteEvalRow,
};

const { columns, columnChecks, data, loading, pagination, searchParams, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listEval,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainEvalTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "model_version", label: "模型版本", minWidth: 160, formatter: (row: TrainEvalTable) => getModelName(row.model_id) },
      { prop: "framework", label: "框架", width: 100, formatter: (row: TrainEvalTable) => h(ElTag, { type: row.framework === "ultralytics" ? "success" : "primary" }, () => row.framework === "ultralytics" ? "YOLO" : "PaddleX") },
      { prop: "eval_dataset_id", label: "评估数据集ID", width: 110 },
      { prop: "status", label: "状态", width: 100, formatter: (row: TrainEvalTable) => statusTag(row.status) },
      { prop: "progress", label: "进度", width: 180, formatter: (row: TrainEvalTable) => progressCell(row) },
      { prop: "metrics", label: "评估指标", minWidth: 220, formatter: (row: TrainEvalTable) => metricsCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 220,
        fixed: "right",
        align: "right",
        formatter: (row: TrainEvalTable) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
  hooks: { onSuccess: (rows) => buildVersionLookup(rows as TrainEvalTable[]) },
});

function handleSearch(params: { name?: string; framework?: string; status?: string }) {
  const q: Record<string, unknown> = { ...cleanEmptyArrayParams(params) };
  if (modelRepoId) q.model_repo_id = modelRepoId;
  replaceSearchParams(q);
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, framework: undefined, status: undefined };
  void resetSearchParams();
}
</script>
