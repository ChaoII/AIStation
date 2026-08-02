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
      :disabled-search="false"
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
            :perm-create="['module_train:model:create']"
            :perm-delete="['module_train:model:delete']"
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
      width="560px"
      :form-mode="dialogVisible.type"
      :confirm-loading="submitLoading"
      @cancel="handleCloseDialog"
      @confirm="handleSubmit"
    >
      <FaForm
        :key="formRenderKey"
        scrollbar
        max-height="75vh"
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
      >
        <template #framework>
          <ElRadioGroup v-model="formData.framework">
            <ElRadio value="ultralytics">Ultralytics</ElRadio>
            <ElRadio value="paddlex">PaddleX</ElRadio>
          </ElRadioGroup>
        </template>
        <template #status>
          <ElSelect v-model="formData.status" style="width: 100%">
            <ElOption label="草稿" value="draft" />
            <ElOption label="已发布" value="released" />
            <ElOption label="已归档" value="archived" />
          </ElSelect>
        </template>
      </FaForm>
    </FaDialog>

    <ModelExportDialog ref="exportDialogRef" :model-id="exportModelId" :model-name="exportModelName" @done="refreshData" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElTag } from "element-plus";
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
import ModelExportDialog from "@/components/model-export-dialog/index.vue";
import { TrainAPI, type TrainModelTable, type TrainModelForm, type TablePageQuery } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

defineOptions({ name: "TrainModelRepo", inheritAttrs: false });

const router = useRouter();
const { hasAuth } = useAuth();

const datasets = ref<any[]>([]);
AnnotationAPI.listDataset({ page_no: 1, page_size: 100 })
  .then(r => { datasets.value = r.data?.data?.items || []; })
  .catch(() => {});

function frameworkTag(fw?: string) {
  return h(ElTag, { type: fw === "ultralytics" ? "success" : "primary" }, () =>
    fw === "ultralytics" ? "YOLO" : "PaddleX"
  );
}
function statusTag(s?: string) {
  const map: Record<string, { type: "info" | "success" | "warning"; text: string }> = {
    draft: { type: "info", text: "草稿" },
    released: { type: "success", text: "已发布" },
    archived: { type: "warning", text: "已归档" },
  };
  const c = map[s || ""] || { type: "info" as const, text: s || "—" };
  return h(ElTag, { type: c.type }, () => c.text);
}
function metricsCell(row: TrainModelTable) {
  const m = row.metrics as any;
  if (!m) return h("span", { style: "color:var(--el-text-color-placeholder)" }, "—");
  const map50 = m.map50 ?? m.mAP;
  if (map50 == null) return h("span", { style: "color:var(--el-text-color-placeholder)" }, "—");
  return h("span", { style: "font-family:monospace;font-size:12px" }, `mAP@50 ${(Number(map50) * 100).toFixed(1)}%`);
}

function buildRowActions(
  row: TrainModelTable,
  ctx: { onEdit: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const all: TableOperationAction[] = [
    {
      key: "train",
      label: "训练",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_train:task:create",
      run: () => router.push(`/train/task/create?model_id=${row.id}&framework=${row.framework}`),
    },
    {
      key: "eval",
      label: "评估",
      artType: "view",
      icon: "ri:bar-chart-box-line",
      perm: "module_train:eval:create",
      run: () => router.push(`/train/eval?model_repo_id=${row.id}`),
    },
    {
      key: "export",
      label: "导出",
      artType: "view",
      icon: "ri:download-2-line",
      perm: "module_train:model:query",
      run: () => openExport(row),
    },
    {
      key: "deploy",
      label: "部署",
      artType: "view",
      icon: "ri:rocket-2-line",
      iconColor: "var(--el-color-success)",
      perm: "module_train:model:query",
      run: () => handleDeploy(row),
    },
    {
      key: "edit",
      label: "编辑",
      artType: "edit",
      icon: "ri:edit-2-line",
      perm: "module_train:model:update",
      run: () => ctx.onEdit(row.id!),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      icon: "ri:delete-bin-4-line",
      perm: "module_train:model:delete",
      run: () => ctx.onDelete(row.id!),
    },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; framework?: string }>({ name: undefined, framework: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "模型名称", key: "name", type: "input", placeholder: "请输入模型名称", clearable: true, span: 6 },
  {
    label: "框架",
    key: "framework",
    type: "select",
    props: {
      placeholder: "请选择框架",
      clearable: true,
      options: [
        { label: "Ultralytics", value: "ultralytics" },
        { label: "PaddleX", value: "paddlex" },
      ],
    },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedRows, selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainModelTable>();

async function deleteModelRow(id: number) {
  try {
    await confirmDelete();
    await TrainAPI.deleteModel([id]);
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
    await TrainAPI.deleteModel(ids);
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
const formData = ref<TrainModelForm>({
  id: undefined,
  name: undefined,
  framework: "ultralytics",
  annotation_dataset_id: undefined,
  description: undefined,
  status: "draft",
});
const initialFormData: TrainModelForm = {
  id: undefined,
  name: undefined,
  framework: "ultralytics",
  annotation_dataset_id: undefined,
  description: undefined,
  status: "draft",
};

const rules = reactive({
  name: [{ required: true, message: "请输入模型名称", trigger: "blur" }],
  framework: [{ required: true, message: "请选择框架", trigger: "change" }],
});

const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<TrainModelForm>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: formRenderKey,
  detailApi: TrainAPI.detailModel,
  createApi: TrainAPI.createModel,
  updateApi: TrainAPI.updateModel,
  titles: { create: "新建模型", update: "编辑模型", detail: "模型详情" },
  onCreateSuccess: async () => { await refreshCreate(); },
  onUpdateSuccess: async () => { await refreshUpdate(); },
});

const formItems = computed<FormItem[]>(() => [
  { label: "模型名称", key: "name", type: "input", span: 24, props: { placeholder: "请输入模型名称" } },
  {
    label: "框架",
    key: "framework",
    type: "radio",
    span: 24,
    props: { options: [
      { label: "Ultralytics", value: "ultralytics" },
      { label: "PaddleX", value: "paddlex" },
    ] },
  },
  {
    label: "来源数据集",
    key: "annotation_dataset_id",
    type: "select",
    span: 24,
    props: { placeholder: "请选择数据集", filterable: true, clearable: true, options: datasets.value.map(d => ({ label: d.name, value: d.id })) },
  },
  {
    label: "状态",
    key: "status",
    type: "select",
    span: 24,
    props: { placeholder: "请选择状态", options: [
      { label: "草稿", value: "draft" },
      { label: "已发布", value: "released" },
      { label: "已归档", value: "archived" },
    ] },
  },
  {
    label: "描述",
    key: "description",
    type: "input",
    span: 24,
    props: { type: "textarea", rows: 3, placeholder: "请输入描述" },
  },
]);

const opCtx = {
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteModelRow,
};

const { columns, columnChecks, data, loading, pagination, searchParams, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listModel,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainModelTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "模型名称", minWidth: 140, showOverflowTooltip: true },
      { prop: "framework", label: "框架", width: 100, formatter: (row: TrainModelTable) => frameworkTag(row.framework) },
      { prop: "version", label: "版本", width: 80, showOverflowTooltip: true },
      { prop: "map50", label: "mAP50", width: 90, align: "center", formatter: (row: any) => (row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-") },
      { prop: "metrics", label: "最新指标", minWidth: 120, formatter: (row: TrainModelTable) => metricsCell(row) },
      { prop: "status", label: "状态", width: 100, formatter: (row: TrainModelTable) => statusTag(row.status) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 260,
        fixed: "right",
        align: "right",
        formatter: (row: TrainModelTable) =>
          renderTableOperationCell(buildRowActions(row, opCtx), {
            wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1",
          }),
      },
    ],
  },
});

const exportDialogRef = ref<InstanceType<typeof ModelExportDialog> | null>(null);
const exportModelId = ref(0);
const exportModelName = ref("");
function openExport(row: TrainModelTable) {
  exportModelId.value = row.id!;
  exportModelName.value = row.name || "";
  exportDialogRef.value?.open();
}

function handleDeploy(row: TrainModelTable) {
  TrainAPI.createDeploy({
    model_id: row.id,
    name: `${row.name} v${row.version}`,
    device: "0",
    hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640 },
  }).then(r => {
    const d = r.data?.data;
    if (d?.api_key) {
      ElMessage.success("部署已创建");
      navigator.clipboard.writeText(d.api_key).catch(() => {});
    }
    router.push("/train/deploy");
  }).catch(e => {
    ElMessage.error(e?.msg || "创建部署失败");
  });
}

function handleSearch(params: { name?: string; framework?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, framework: undefined };
  void resetSearchParams();
}
</script>
