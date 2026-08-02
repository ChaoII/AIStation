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
            :perm-create="['module_annotation:dataset:create']"
            :perm-delete="['module_annotation:dataset:delete']"
            :delete-loading="batchDeleting"
            @add="handleOpenDialog('create')"
            @delete="handleBatchDelete"
          />
          <ElButton type="warning" size="default" style="margin-left: 4px" @click="openImport">X-AnyLabeling 导入</ElButton>
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
      width="550px"
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
        :label-width="100"
        label-position="right"
        :span="24"
        :gutter="16"
        :show-reset="false"
        :show-submit="false"
      />
    </FaDialog>

    <ElDialog v-model="uploadVisible" title="上传图片" width="500px" :close-on-click-modal="false">
      <ElAlert title="支持 JPG / PNG / BMP 格式，可多选文件" type="info" :closable="false" show-icon style="margin-bottom: 12px" />
      <ElUpload
        ref="uploadRef"
        :auto-upload="false"
        multiple
        drag
        accept="image/jpeg,image/png,image/bmp"
        :file-list="fileList"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        list-type="picture-card"
      >
        <ElIcon size="32"><Plus /></ElIcon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
      </ElUpload>
      <template #footer>
        <ElButton @click="uploadVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="uploadLoading" @click="handleUploadSubmit">开始上传</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="importDialogVisible" title="导入 x-anylabeling 标注" width="500px">
      <ElForm label-width="100px">
        <ElFormItem label="目标数据集" required>
          <ElSelect v-model="importDatasetId" filterable placeholder="选择数据集" style="width:100%">
            <ElOption v-for="ds in datasetOptions" :key="ds.id" :label="ds.name" :value="ds.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="ZIP 文件" required>
          <ElUpload ref="importUploadRef" :auto-upload="false" accept=".zip" :limit="1" :on-change="onImportFileChange">
            <ElButton size="small" type="primary">选择 ZIP 文件</ElButton>
            <template #tip><div style="font-size:12px;color:#909399;margin-top:4px">包含图片和同名 .json 标注文件的 ZIP 压缩包</div></template>
          </ElUpload>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="importDialogVisible = false">取消</ElButton>
        <ElButton type="warning" :loading="importing" @click="handleImportSubmit">导入</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="exportDialogVisible" title="导出数据集" width="500px" :close-on-click-modal="!exporting" :close-on-press-escape="!exporting" :show-close="!exporting">
      <ElForm label-width="120px">
        <ElFormItem label="数据集"><span>{{ exportDatasetName }}</span></ElFormItem>
        <ElFormItem label="标注任务" required>
          <ElSelect v-model="exportTaskId" placeholder="请选择标注任务" filterable style="width:100%" @change="onTaskChange">
            <ElOption v-for="t in exportRowTasks" :key="t.id" :value="t.id" :label="`${t.name}（${taskTypeLabel(t.task_type)}）`" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="导出格式" required>
          <ElSelect v-model="exportFormat" style="width:100%">
            <ElOption v-for="opt in filteredExportFormats" :key="opt.value" :value="opt.value" :label="opt.label" />
          </ElSelect>
          <div v-if="exportFormat === 'paddle-ocr'" style="margin-top:8px">
            <ElCheckbox v-model="ocrExportDet" label="导出检测数据集 (det)" border size="small" style="margin-right:8px" />
            <ElCheckbox v-model="ocrExportRec" label="导出识别数据集 (rec)" border size="small" />
          </div>
        </ElFormItem>
        <ElFormItem v-if="isYoloOrPaddleFormat" label="训练集比例">
          <ElSlider v-model="trainRatio" :min="50" :max="95" :step="5" show-input style="width:200px" />
          <span style="margin-left:8px;font-size:12px;color:#909399">剩余 {{ 100 - trainRatio }}% 为验证集</span>
        </ElFormItem>
        <ElAlert type="info" :closable="false" show-icon><template #title>将导出该数据集所有已标注图片和标注文件，打包为 ZIP 下载</template></ElAlert>
      </ElForm>
      <template #footer>
        <ElButton @click="exportDialogVisible = false" :disabled="exporting">取消</ElButton>
        <ElButton type="warning" :loading="exporting" @click="handleExportSubmit">{{ exporting ? "导出中..." : "导出并下载" }}</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElTag } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
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
import { AnnotationAPI, type AnnotationDataset } from "@/api/module_annotation";

defineOptions({ name: "AnnotationDataset", inheritAttrs: false });

const router = useRouter();
const { hasAuth } = useAuth();

function taskTagType(t: string) {
  return ({ detection: "primary", rotated_detection: "warning", segmentation: "success", keypoint: "danger", ocr: "info", classification: "info" } as any)[t] || "info";
}
function taskTagColor(t: string) {
  return ({ detection: "#409eff", rotated_detection: "#e6a23c", segmentation: "#67c23a", keypoint: "#f56c6c", ocr: "#909399", classification: "#b37feb" } as any)[t] || "#909399";
}
function taskTypeLabel(t: string) {
  return ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" } as any)[t] || t;
}

function tasksCell(row: AnnotationDataset) {
  const tasks = (row as any).tasks;
  if (!tasks?.length) return h("span", { style: "color:var(--el-text-color-placeholder);font-size:12px" }, "—");
  return h("span", { style: "display:flex;flex-wrap:wrap;gap:4px" }, tasks.map((t: any) =>
    h(ElTag, { key: t.id, size: "small", type: taskTagType(t.task_type), style: { cursor: "pointer" } }, () =>
      `${t.name} ${t.progress ?? 0}%`
    )
  ));
}

function buildRowActions(
  row: AnnotationDataset,
  ctx: { onUpload: (id: number) => void; onExport: (row: AnnotationDataset) => void; onEdit: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const all: TableOperationAction[] = [
    { key: "upload", label: "上传", artType: "view", icon: "ri:upload-2-line", iconColor: "var(--el-color-success)", perm: "module_annotation:dataset:upload", run: () => ctx.onUpload(row.id!) },
    { key: "export", label: "导出", artType: "view", icon: "ri:download-2-line", iconColor: "var(--el-color-warning)", run: () => ctx.onExport(row) },
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_annotation:dataset:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_annotation:dataset:delete", run: () => ctx.onDelete(row.id!) },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string }>({ name: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "数据集名称", key: "name", type: "input", placeholder: "请输入数据集名称", clearable: true, span: 8 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<AnnotationDataset>();

async function deleteDatasetRow(id: number) {
  try {
    await confirmDelete();
    await AnnotationAPI.deleteDataset([id]);
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
    await AnnotationAPI.deleteDataset(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

// ─── 创建/编辑 ───
const { dialogVisible } = useCrudDialog();
const formData = ref<any>({ id: undefined, name: undefined, description: undefined });
const initialFormData = { id: undefined, name: undefined, description: undefined };
const rules = reactive({
  name: [{ required: true, message: "请输入数据集名称", trigger: "blur" }],
});
const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<any>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: formRenderKey,
  createApi: AnnotationAPI.createDataset,
  updateApi: AnnotationAPI.updateDataset,
  titles: { create: "新建数据集", update: "编辑数据集" },
  onCreateSuccess: async () => { await refreshCreate(); },
  onUpdateSuccess: async () => { await refreshUpdate(); },
});

const formItems = computed<FormItem[]>(() => [
  { label: "数据集名称", key: "name", type: "input", span: 24, props: { placeholder: "请输入数据集名称", maxlength: 100 } },
  { label: "描述", key: "description", type: "input", span: 24, props: { type: "textarea", rows: 3, maxlength: 500, placeholder: "请输入描述" } },
]);

// ─── 上传 ───
const uploadVisible = ref(false);
const uploadLoading = ref(false);
const uploadDatasetId = ref(0);
const fileList = ref<any[]>([]);
const uploadRef = ref<any>(null);

function handleOpenUpload(id: number) {
  uploadDatasetId.value = id;
  fileList.value = [];
  uploadVisible.value = true;
}
function handleFileChange(_file: any, files: any[]) { fileList.value = files; }
function handleFileRemove(_file: any, files: any[]) { fileList.value = files; }
async function handleUploadSubmit() {
  if (!fileList.value.length) { ElMessage.warning("请选择图片"); return; }
  uploadLoading.value = true;
  try {
    const formData = new FormData();
    fileList.value.forEach(f => formData.append("files", f.raw));
    await AnnotationAPI.uploadImages(uploadDatasetId.value, formData);
    ElMessage.success("上传成功");
    uploadVisible.value = false;
    await refreshData();
  } catch (e: any) {
    ElMessage.error(e?.msg || "上传失败");
  } finally { uploadLoading.value = false; }
}

// ─── x-anylabeling 导入 ───
const importDialogVisible = ref(false);
const importing = ref(false);
const importDatasetId = ref<number | undefined>();
const importFile = ref<File | null>(null);
const importUploadRef = ref<any>(null);
const datasetOptions = ref<any[]>([]);

function openImport() {
  importDatasetId.value = undefined;
  importFile.value = null;
  importDialogVisible.value = true;
}
function onImportFileChange(file: any) {
  importFile.value = file.raw || null;
}
async function handleImportSubmit() {
  if (!importDatasetId.value) { ElMessage.warning("请选择目标数据集"); return; }
  if (!importFile.value) { ElMessage.warning("请选择 ZIP 文件"); return; }
  importing.value = true;
  try {
    const r = await AnnotationAPI.importXAnyLabeling(importDatasetId.value, importFile.value);
    ElMessage.success(`导入完成：${r.data?.data?.imported ?? 0} 张图片`);
    importDialogVisible.value = false;
    await refreshData();
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
  } finally { importing.value = false; }
}

// ─── 导出 ───
const exportDialogVisible = ref(false);
const exporting = ref(false);
const exportDatasetId = ref(0);
const exportDatasetName = ref("");
const exportRowTasks = ref<any[]>([]);
const exportTaskId = ref<number | undefined>();
const exportFormat = ref("ultralytics");
const ocrExportDet = ref(true);
const ocrExportRec = ref(true);
const trainRatio = ref(80);

const exportFormats = [
  { value: "ultralytics", label: "YOLO (Ultralytics)" },
  { value: "paddlex", label: "PaddleX (检测/分割)" },
  { value: "paddle-ocr", label: "PaddleOCR" },
  { value: "x-anylabeling", label: "x-anylabeling (LabelMe JSON)" },
];
const isYoloOrPaddleFormat = computed(() => ["ultralytics", "paddlex"].includes(exportFormat.value));
const filteredExportFormats = computed(() =>
  exportFormat.value === "x-anylabeling" ? exportFormats : exportFormats.filter(f => f.value !== "paddle-ocr" || exportRowTasks.value.some(t => t.task_type === "ocr"))
);

function handleOpenExport(row: AnnotationDataset) {
  exportDatasetId.value = row.id!;
  exportDatasetName.value = row.name || "";
  exportRowTasks.value = (row as any).tasks || [];
  exportTaskId.value = exportRowTasks.value[0]?.id;
  exportFormat.value = "ultralytics";
  exportDialogVisible.value = true;
}
function onTaskChange(id: number) {
  const t = exportRowTasks.value.find(x => x.id === id);
  exportFormat.value = t?.task_type === "ocr" ? "paddle-ocr" : "ultralytics";
}
async function handleExportSubmit() {
  if (!exportTaskId.value) { ElMessage.warning("请选择标注任务"); return; }
  exporting.value = true;
  try {
    const { TrainAPI } = await import("@/api/module_train");
    const r = await TrainAPI.exportDataset({
      dataset_id: exportDatasetId.value,
      annotation_task_id: exportTaskId.value,
      format: exportFormat.value,
      ocr_rec: ocrExportRec.value,
      train_ratio: trainRatio.value / 100,
    });
    if (r.data?.data?.download_url) window.open(r.data.data.download_url, "_blank");
    ElMessage.success("导出成功，开始下载");
    exportDialogVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.msg || "导出失败");
  } finally { exporting.value = false; }
}

const opCtx = {
  onUpload: handleOpenUpload,
  onExport: handleOpenExport,
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteDatasetRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: AnnotationAPI.listDataset,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<AnnotationDataset>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "数据集名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "description", label: "描述", minWidth: 180, showOverflowTooltip: true },
      { prop: "image_count", label: "图片数", width: 90, align: "center", formatter: (row: AnnotationDataset) => h(ElTag, { type: "primary", effect: "plain", size: "small" }, () => String(row.image_count ?? 0)) },
      { prop: "tasks", label: "关联标注任务", minWidth: 300, formatter: (row: AnnotationDataset) => tasksCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 200,
        fixed: "right",
        align: "right",
        formatter: (row: AnnotationDataset) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined };
  void resetSearchParams();
}
</script>
