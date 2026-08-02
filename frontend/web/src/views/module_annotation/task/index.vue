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
            :perm-create="['module_annotation:task:create']"
            :perm-delete="['module_annotation:task:delete']"
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
      width="600px"
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
        :label-width="110"
        label-position="right"
        :span="24"
        :gutter="16"
        :show-reset="false"
        :show-submit="false"
      >
        <template #classification_mode>
          <ElRadioGroup v-model="formData.classification_mode">
            <ElRadio value="single">单标签（每张图一个类别）</ElRadio>
            <ElRadio value="multi">多标签（每张图多个类别）</ElRadio>
          </ElRadioGroup>
        </template>
      </FaForm>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElTag, ElProgress } from "element-plus";
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
import { AnnotationAPI } from "@/api/module_annotation";
import UserAPI from "@/api/module_system/user";

defineOptions({ name: "AnnotationTask", inheritAttrs: false });

const router = useRouter();
const { hasAuth } = useAuth();

const datasetOptions = ref<any[]>([]);
const userOptions = ref<any[]>([]);

Promise.all([
  AnnotationAPI.listDataset({ page_no: 1, page_size: 100 }),
  UserAPI.listUser({ page_no: 1, page_size: 100 }),
]).then(([ds, us]) => {
  datasetOptions.value = ds.data?.data?.items || [];
  userOptions.value = us.data?.data?.items || [];
}).catch(() => {});

function annotationTypeLabel(type: string) {
  return ({ detection: "目标检测", rotated_detection: "旋转框检测", segmentation: "多边形分割", keypoint: "关键点", ocr: "OCR文本", classification: "图像分类" } as any)[type] || type;
}
function annotationTypeTag(type: string) {
  const map: Record<string, "success" | "warning" | "danger" | "info" | "primary"> = {
    detection: "primary", rotated_detection: "warning", segmentation: "danger", keypoint: "warning", ocr: "info", classification: "info",
  };
  return map[type] || "info";
}
function statusTag(s?: string) {
  if (s === "completed") return h(ElTag, { type: "success", size: "small" }, () => "已完成");
  if (s === "in_progress") return h(ElTag, { type: "primary", size: "small" }, () => "进行中");
  return h(ElTag, { type: "info", size: "small" }, () => "待开始");
}
function progressCell(row: any) {
  return h(ElProgress, { percentage: row.progress || 0, "stroke-width": 14, "text-inside": true, status: row.progress >= 100 ? "success" : undefined });
}
function assigneesCell(row: any) {
  const names = row.assignees || [];
  if (!names.length) return h("span", { style: "color:var(--el-text-color-placeholder)" }, "—");
  return h("span", {}, names.map((n: string) => h(ElTag, { key: n, size: "small", style: "margin-right:3px;margin-bottom:2px" }, () => n)));
}

function buildRowActions(
  row: any,
  ctx: { onEnter: (id: number) => void; onEdit: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const all: TableOperationAction[] = [
    { key: "enter", label: "进入标注", artType: "view", icon: "ri:edit-box-line", iconColor: "var(--el-color-success)", perm: "module_annotation:task:workbench", run: () => ctx.onEnter(row.id!) },
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_annotation:task:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_annotation:task:delete", run: () => ctx.onDelete(row.id!) },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; status?: string }>({ name: undefined, status: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "任务名称", key: "name", type: "input", placeholder: "请输入任务名称", clearable: true, span: 6 },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: { placeholder: "请选择状态", clearable: true, options: [
      { label: "待开始", value: "pending" },
      { label: "进行中", value: "in_progress" },
      { label: "已完成", value: "completed" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteTaskRow(id: number) {
  try {
    await confirmDelete();
    await AnnotationAPI.deleteTask([id]);
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
    await AnnotationAPI.deleteTask(ids);
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
const formData = ref<any>({
  id: undefined, name: undefined, dataset_id: undefined, task_type: "detection",
  assignees: [] as number[], description: undefined, classification_mode: undefined,
});
const initialFormData = {
  id: undefined, name: undefined, dataset_id: undefined, task_type: "detection",
  assignees: [] as number[], description: undefined, classification_mode: undefined,
};
const rules = reactive({
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  dataset_id: [{ required: true, message: "请选择数据集", trigger: "change" }],
  task_type: [{ required: true, message: "请选择标注类型", trigger: "change" }],
});
const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<any>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: formRenderKey,
  createApi: async (form) => {
    await AnnotationAPI.createTask({
      dataset_id: form.dataset_id,
      name: form.name,
      task_type: form.task_type,
      assignees: form.assignees || [],
      classes: [],
      classification_mode: form.classification_mode,
    });
  },
  updateApi: async (id, form) => {
    await AnnotationAPI.updateTask(id, { name: form.name, task_type: form.task_type, assignees: form.assignees || [] });
  },
  titles: { create: "新增任务", update: "编辑任务" },
  onCreateSuccess: async () => { await refreshCreate(); },
  onUpdateSuccess: async () => { await refreshUpdate(); },
});

const formItems = computed<FormItem[]>(() => [
  { label: "任务名称", key: "name", type: "input", span: 24, props: { placeholder: "请输入任务名称" } },
  { label: "选择数据集", key: "dataset_id", type: "select", span: 24, props: { placeholder: "请选择数据集", filterable: true, options: datasetOptions.value.map(d => ({ label: d.name, value: d.id })) } },
  {
    label: "标注类型",
    key: "task_type",
    type: "select",
    span: 24,
    props: { placeholder: "请选择标注类型", options: [
      { label: "目标检测", value: "detection" },
      { label: "旋转框检测", value: "rotated_detection" },
      { label: "多边形分割", value: "segmentation" },
      { label: "关键点", value: "keypoint" },
      { label: "OCR文本", value: "ocr" },
      { label: "图像分类", value: "classification" },
    ] },
  },
  {
    label: "分类模式",
    key: "classification_mode",
    type: "slot",
    span: 24,
    show: formData.value.task_type === "classification",
  },
  {
    label: "标注员",
    key: "assignees",
    type: "select",
    span: 24,
    props: { placeholder: "请选择标注员", multiple: true, filterable: true, options: userOptions.value.map(u => ({ label: u.name, value: u.id })) },
  },
  { label: "备注", key: "description", type: "input", span: 24, props: { type: "textarea", rows: 3, placeholder: "可选备注信息" } },
]);

const opCtx = {
  onEnter: (id: number) => router.push(`/annotation/workbench/${id}`),
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteTaskRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: AnnotationAPI.listTask,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "任务名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "dataset_name", label: "数据集", minWidth: 140, showOverflowTooltip: true },
      { prop: "task_type", label: "标注类型", width: 120, align: "center", formatter: (row: any) => h(ElTag, { type: annotationTypeTag(row.task_type), size: "small", effect: "plain" }, () => annotationTypeLabel(row.task_type)) },
      { prop: "progress", label: "进度", width: 180, formatter: (row: any) => progressCell(row) },
      { prop: "assignees", label: "标注员", minWidth: 140, formatter: (row: any) => assigneesCell(row) },
      { prop: "status", label: "状态", width: 100, align: "center", formatter: (row: any) => statusTag(row.status) },
      { prop: "created_time", label: "创建时间", minWidth: 170, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 200,
        fixed: "right",
        align: "right",
        formatter: (row: any) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; status?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, status: undefined };
  void resetSearchParams();
}
</script>
