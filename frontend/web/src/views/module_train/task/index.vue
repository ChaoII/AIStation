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
            :perm-create="['module_train:task:create']"
            :perm-delete="['module_train:task:delete']"
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
      width="680px"
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
      >
        <template #framework>
          <ElRadioGroup v-model="formData.framework" @change="onFrameworkChange">
            <ElRadio value="ultralytics">Ultralytics</ElRadio>
            <ElRadio value="pytorch-ocr-det">PyTorch OCR (det)</ElRadio>
            <ElRadio value="pytorch-ocr-rec">PyTorch OCR (rec)</ElRadio>
          </ElRadioGroup>
        </template>
        <template #hyperparams>
          <ElDivider content-position="left">超参数配置</ElDivider>
          <ElRow :gutter="16">
            <ElCol v-if="isOcrFramework(formData.framework)" :span="12">
              <ElFormItem label="模型大小">
                <ElSelect v-model="hpForm.model_size" style="width:100%">
                  <ElOption label="tiny" value="tiny" />
                  <ElOption label="small" value="small" />
                  <ElOption label="medium" value="medium" />
                </ElSelect>
              </ElFormItem>
            </ElCol>
            <ElCol v-else :span="12">
              <ElFormItem label="模型">
                <ElSelect v-model="hpForm.model" style="width:100%">
                  <ElOptionGroup v-for="g in modelGroups" :key="g" :label="g">
                    <ElOption v-for="opt in modelOptions.filter(o => o.group === g)" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </ElOptionGroup>
                </ElSelect>
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="Epochs">
                <ElInputNumber v-model="hpForm.epochs" :min="1" :max="1000" style="width:100%" />
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="Batch Size">
                <ElInputNumber v-model="hpForm.batch" :min="1" :max="512" style="width:100%" />
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="Learning Rate">
                <ElInputNumber
                  v-if="isOcrFramework(formData.framework)"
                  v-model="hpForm.lr"
                  :min="0.0001" :max="1" :step="0.001" :precision="4" style="width:100%"
                />
                <ElInputNumber
                  v-else
                  v-model="hpForm.lr0"
                  :min="0.0001" :max="1" :step="0.001" :precision="4" style="width:100%"
                />
              </ElFormItem>
            </ElCol>
            <ElCol v-if="!isOcrFramework(formData.framework)" :span="12">
              <ElFormItem label="Optimizer">
                <ElSelect v-model="hpForm.optimizer" style="width:100%">
                  <ElOption label="AdamW" value="AdamW" />
                  <ElOption label="SGD" value="SGD" />
                  <ElOption label="Adam" value="Adam" />
                </ElSelect>
              </ElFormItem>
            </ElCol>
            <ElCol v-if="!isOcrFramework(formData.framework)" :span="12">
              <ElFormItem label="Image Size">
                <ElInputNumber v-model="hpForm.imgsz" :min="32" :max="4096" :step="32" style="width:100%" />
              </ElFormItem>
            </ElCol>
            <ElCol v-if="!isOcrFramework(formData.framework)" :span="12">
              <ElFormItem label="Workers">
                <ElInputNumber v-model="hpForm.workers" :min="0" :max="32" style="width:100%" />
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="GPU 设备">
                <ElInput v-model="hpForm.device" placeholder="如: 0" />
              </ElFormItem>
            </ElCol>
            <ElCol v-if="isClassificationTask && !isOcrFramework(formData.framework)" :span="12">
              <ElFormItem label="多标签分类">
                <ElSwitch v-model="hpForm.multi_label" />
              </ElFormItem>
            </ElCol>
          </ElRow>
          <ElCollapse v-if="!isOcrFramework(formData.framework)" class="hp-advanced-collapse">
            <ElCollapseItem title="高级参数" name="advanced">
              <ElRow :gutter="16">
                <ElCol :span="12"><ElFormItem label="LR Factor (lrf)"><ElInputNumber v-model="hpForm.lrf" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Momentum"><ElInputNumber v-model="hpForm.momentum" :min="0" :max="1" :step="0.001" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Weight Decay"><ElInputNumber v-model="hpForm.weight_decay" :min="0" :max="1" :step="0.0001" :precision="4" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Patience"><ElInputNumber v-model="hpForm.patience" :min="0" :max="1000" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Seed"><ElInputNumber v-model="hpForm.seed" :min="0" :max="999999" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Hue"><ElInputNumber v-model="hpForm.hsv_h" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Saturation"><ElInputNumber v-model="hpForm.hsv_s" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Value"><ElInputNumber v-model="hpForm.hsv_v" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Flip LR"><ElInputNumber v-model="hpForm.fliplr" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Flip UD"><ElInputNumber v-model="hpForm.flipud" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Mosaic"><ElInputNumber v-model="hpForm.mosaic" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="MixUp"><ElInputNumber v-model="hpForm.mixup" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
              </ElRow>
            </ElCollapseItem>
          </ElCollapse>
          <ElDivider content-position="left">Docker 命令预览</ElDivider>
          <pre class="docker-cmd-pre">{{ dockerCmdPreview }}</pre>
        </template>
      </FaForm>
    </FaDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox, ElProgress, ElTag } from "element-plus";
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
import { TrainAPI, type TrainTaskTable, type TrainTaskForm, type TablePageQuery } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

defineOptions({ name: "TrainTask", inheritAttrs: false });

const route = useRoute();
const router = useRouter();
const { hasAuth } = useAuth();
let routeBaseModelId = Number(route.query.base_model_id || 0);
const routeFramework = String(route.query.framework || "");

const datasets = ref<any[]>([]);
const annoTasks = ref<any[]>([]);
AnnotationAPI.listDataset({ page_no: 1, page_size: 100 })
  .then(r => { datasets.value = r.data?.data?.items || []; })
  .catch(() => {});

const MODEL_FAMILIES = [
  { label: "YOLOv8", prefix: "yolov8", sizes: ["n", "s", "m", "l", "x"] },
  { label: "YOLO11", prefix: "yolo11", sizes: ["n", "s", "m", "l", "x"] },
  { label: "YOLO26", prefix: "yolo26", sizes: ["n", "s", "m", "l", "x"] },
];

function annoTaskTypeLabel(t: string) {
  return ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" } as any)[t] || t;
}

function isOcrFramework(fw: string | undefined) {
  return fw === "pytorch-ocr-det" || fw === "pytorch-ocr-rec";
}

const modelOptions = computed(() => {
  const activeTask = annoTasks.value.find((t: any) => t.id === formData.value.annotation_task_id);
  const taskType = activeTask?.task_type || "detection";
  const isObb = taskType === "rotated_detection";
  const isCls = taskType === "classification" || taskType === "cls";
  const opts: { label: string; value: string; group: string }[] = [];
  for (const fam of MODEL_FAMILIES) {
    for (const sz of fam.sizes) {
      const base = `${fam.prefix}${sz}`;
      if (!isCls) opts.push({ label: `${fam.label}${sz.toUpperCase()}`, value: `${base}.pt`, group: fam.label });
      if (isObb) opts.push({ label: `${fam.label}${sz.toUpperCase()}-OBB`, value: `${base}-obb.pt`, group: `${fam.label} OBB` });
      if (isCls) opts.push({ label: `${fam.label}${sz.toUpperCase()}-CLS`, value: `${base}-cls.pt`, group: `${fam.label} CLS` });
    }
  }
  return opts;
});
const modelGroups = computed(() => [...new Set(modelOptions.value.map(o => o.group))]);

const isClassificationTask = computed(() => {
  const activeTask = annoTasks.value.find((t: any) => t.id === formData.value.annotation_task_id);
  return activeTask?.task_type === "classification" || activeTask?.task_type === "cls";
});

async function onDatasetChange(datasetId: number) {
  formData.value.annotation_task_id = undefined;
  annoTasks.value = [];
  if (!datasetId) return;
  try {
    const r = await AnnotationAPI.listDataset({ page_no: 1, page_size: 100 });
    const ds = r.data?.data?.items?.find((d: any) => d.id === datasetId);
    annoTasks.value = ds?.tasks || [];
  } catch {}
}

function statusTag(s?: string) {
  const map: Record<string, { type: "info" | "success" | "warning" | "danger"; text: string }> = {
    pending: { type: "info", text: "待开始" },
    running: { type: "warning", text: "训练中" },
    success: { type: "success", text: "已完成" },
    failed: { type: "danger", text: "失败" },
    cancelled: { type: "info", text: "已取消" },
  };
  const c = map[s || ""] || { type: "info" as const, text: s || "—" };
  return h(ElTag, { type: c.type }, () => c.text);
}
function progressCell(row: TrainTaskTable) {
  const status = row.status;
  return h(ElProgress, {
    percentage: row.progress || 0,
    "stroke-width": 14,
    "text-inside": true,
    status: status === "failed" ? "exception" : status === "success" ? "success" : undefined,
  });
}

function buildRowActions(
  row: TrainTaskTable,
  ctx: { onStart: (id: number) => void; onStop: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    {
      key: "detail",
      label: "详情",
      artType: "view",
      icon: "ri:eye-line",
      perm: "module_train:task:query",
      run: () => router.push(`/train/task/${row.id}`),
    },
  ];
  if (row.status === "pending") {
    actions.unshift({
      key: "start",
      label: "开始训练",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_train:task:update",
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
      perm: "module_train:task:update",
      run: () => ctx.onStop(row.id!),
    });
  }
  actions.push({
    key: "delete",
    label: "删除",
    artType: "delete",
    icon: "ri:delete-bin-4-line",
    perm: "module_train:task:delete",
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
  { label: "任务名称", key: "name", type: "input", placeholder: "请输入任务名称", clearable: true, span: 6 },
  {
    label: "框架",
    key: "framework",
    type: "select",
    props: { placeholder: "请选择框架", clearable: true, options: [
      { label: "Ultralytics", value: "ultralytics" },
      { label: "PyTorch OCR (det)", value: "pytorch-ocr-det" },
      { label: "PyTorch OCR (rec)", value: "pytorch-ocr-rec" },
    ] },
    span: 6,
  },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: { placeholder: "请选择状态", clearable: true, options: [
      { label: "待开始", value: "pending" },
      { label: "训练中", value: "running" },
      { label: "已完成", value: "success" },
      { label: "失败", value: "failed" },
      { label: "已取消", value: "cancelled" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainTaskTable>();

async function startTask(id: number) {
  try {
    const row = (data.value as TrainTaskTable[]).find(r => r.id === id);
    await ElMessageBox.confirm(`确定开始训练任务「${row?.name || id}」？`, "提示", { type: "info" });
    await TrainAPI.startTask(id);
    ElMessage.success("训练已开始");
    await refreshData();
  } catch {
    // cancel
  }
}
async function stopTask(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(id);
    ElMessage.success("训练已停止");
    await refreshData();
  } catch {
    // cancel
  }
}
async function deleteTaskRow(id: number) {
  try {
    await confirmDelete();
    await TrainAPI.deleteTask([id]);
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
    await TrainAPI.deleteTask(ids);
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
const formData = ref<TrainTaskForm>({
  id: undefined, name: undefined, framework: "ultralytics", dataset_id: undefined, annotation_task_id: undefined,
});
const initialFormData: TrainTaskForm = {
  id: undefined, name: undefined, framework: "ultralytics", dataset_id: undefined, annotation_task_id: undefined,
};

const hpForm = reactive<Record<string, any>>({
  model: "yolo11n.pt", epochs: 100, batch: 16, lr0: 0.01, optimizer: "AdamW",
  imgsz: 640, workers: 4, device: "0", trainRatio: 80,
  lrf: 0.01, momentum: 0.937, weight_decay: 0.0005, patience: 100, seed: 0,
  hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4, fliplr: 0.5, flipud: 0.0, mosaic: 1.0, mixup: 0.0,
  multi_label: false,
});

function onFrameworkChange(fw?: string | number | boolean | undefined) {
  const val = String(fw ?? formData.value.framework ?? "");
  Object.keys(hpForm).forEach(k => delete hpForm[k]);
  if (val === "pytorch-ocr-det") {
    Object.assign(hpForm, { model_size: "tiny", epochs: 100, batch: 8, lr: 0.001, device: "0" });
  } else if (val === "pytorch-ocr-rec") {
    Object.assign(hpForm, { model_size: "tiny", epochs: 100, batch: 128, lr: 0.001, device: "0" });
  } else {
    Object.assign(hpForm, { model: "yolo11n.pt", epochs: 100, batch: 16, lr0: 0.01, optimizer: "AdamW", imgsz: 640, workers: 4, device: "0", trainRatio: 80, lrf: 0.01, momentum: 0.937, weight_decay: 0.0005, patience: 100, seed: 0, hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4, fliplr: 0.5, flipud: 0.0, mosaic: 1.0, mixup: 0.0, multi_label: false });
  }
}

function buildHyperparams(): Record<string, any> {
  if (isOcrFramework(formData.value.framework)) {
    return { model_size: hpForm.model_size || "tiny", epochs: hpForm.epochs, batch: hpForm.batch, lr: hpForm.lr, device: hpForm.device };
  }
  const hp: Record<string, any> = { ...hpForm, lr0: hpForm.lr0 ?? 0.01, train_ratio: (hpForm.trainRatio || 80) / 100 };
  if (!isClassificationTask.value) delete hp.multi_label;
  return hp;
}

const tempDir = ref("${TEMP_DIR}");
TrainAPI.getTempDir().then(res => { if (res?.data?.data?.tempdir) tempDir.value = res.data.data.tempdir; }).catch(() => {});

const dockerCmdPreview = computed(() => {
  const dataMount = `${tempDir.value}/train_output/{task_id}/data`;
  const outputMount = `${tempDir.value}/train_output/{task_id}`;
  const cacheMount = `${tempDir.value}/train_output/.models_cache`;
  if (formData.value.framework === "pytorch-ocr-det") {
    return `docker run --gpus all \\\n  -v ${dataMount}:/data \\\n  -v ${outputMount}:/output \\\n  -v ${cacheMount}:/models \\\n  aistation-ocr:latest \\\n  train-det \\\n    --data /data \\\n    --output /output \\\n    --device ${hpForm.device ?? "0"} \\\n    --epochs ${hpForm.epochs ?? 100} \\\n    --batch ${hpForm.batch ?? 8} \\\n    --lr ${hpForm.lr ?? 0.001} \\\n    --model-size ${hpForm.model_size ?? "tiny"}`;
  }
  if (formData.value.framework === "pytorch-ocr-rec") {
    return `docker run --gpus all \\\n  -v ${dataMount}:/data \\\n  -v ${outputMount}:/output \\\n  -v ${cacheMount}:/models \\\n  aistation-ocr:latest \\\n  train-rec \\\n    --data /data \\\n    --output /output \\\n    --device ${hpForm.device ?? "0"} \\\n    --epochs ${hpForm.epochs ?? 100} \\\n    --batch ${hpForm.batch ?? 128} \\\n    --lr ${hpForm.lr ?? 0.001} \\\n    --model-size ${hpForm.model_size ?? "tiny"}`;
  }
  return `docker run --gpus all \\\n  -v ${dataMount}:/data \\\n  -v ${outputMount}:/output \\\n  -v ${cacheMount}:/models \\\n  ultralytics/ultralytics:latest \\\n  yolo train \\\n    model=/models/${hpForm.model} \\\n    data=/data/dataset.yaml \\\n    epochs=${hpForm.epochs} \\\n    batch=${hpForm.batch} \\\n    lr0=${hpForm.lr0} \\\n    imgsz=${hpForm.imgsz} \\\n    workers=${hpForm.workers} \\\n    optimizer=${hpForm.optimizer} \\\n    project=/output \\\n    name=exp`;
});

const rules = reactive({
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  dataset_id: [{ required: true, message: "请选择数据集", trigger: "change" }],
});

const dataFormRef = ref<InstanceType<typeof FaForm> | null>(null);
const formRenderKey = ref(0);

const { submitLoading, handleCloseDialog, handleOpenDialog, handleSubmit } = useCrudForm<TrainTaskForm>({
  formData,
  initialFormData,
  dialogVisible,
  dataFormRef,
  formRenderKey: formRenderKey,
  createApi: async (form) => {
    await TrainAPI.createTask({
      ...form,
      hyperparams: buildHyperparams(),
      base_model_id: routeBaseModelId || undefined,
    });
  },
  titles: { create: "新建训练任务" },
  onCreateSuccess: async () => { routeBaseModelId = 0; await refreshCreate(); },
});

onMounted(() => {
  if (routeBaseModelId) {
    const extra: Record<string, unknown> = {};
    if (routeFramework && ["ultralytics", "pytorch-ocr-det", "pytorch-ocr-rec"].includes(routeFramework)) extra.framework = routeFramework;
    handleOpenDialog("create", undefined, extra);
    if (routeFramework && ["ultralytics", "pytorch-ocr-det", "pytorch-ocr-rec"].includes(routeFramework)) onFrameworkChange();
  }
});

const formItems = computed<FormItem[]>(() => [
  { label: "任务名称", key: "name", type: "input", span: 24, props: { placeholder: "如: 缺陷检测v3" } },
  { label: "框架", key: "framework", type: "radio", span: 24 },
  {
    label: "选择数据集",
    key: "dataset_id",
    type: "select",
    span: 24,
    props: { placeholder: "请选择标注数据集", filterable: true, options: datasets.value.map(d => ({ label: d.name, value: d.id })) },
  },
  {
    label: "标注任务",
    key: "annotation_task_id",
    type: "select",
    span: 24,
    props: { placeholder: "选择标注任务（可选）", filterable: true, clearable: true, options: annoTasks.value.map((t: any) => ({ label: `${t.name}（${annoTaskTypeLabel(t.task_type)}）`, value: t.id })) },
  },
  { label: "超参数", key: "hyperparams", type: "slot", span: 24 },
]);

const opCtx = {
  onStart: startTask,
  onStop: stopTask,
  onDelete: deleteTaskRow,
};

const { columns, columnChecks, data, loading, pagination, searchParams, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listTask,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainTaskTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "任务名称", minWidth: 160, showOverflowTooltip: true },
      {
        prop: "framework",
        label: "框架",
        width: 100,
        formatter: (row: TrainTaskTable) => h(ElTag, { type: row.framework === "ultralytics" ? "success" : "primary" }, () => row.framework === "ultralytics" ? "YOLO" : isOcrFramework(row.framework) ? "OCR" : "PaddleX"),
      },
      { prop: "dataset_id", label: "数据集ID", width: 90 },
      { prop: "status", label: "状态", width: 100, formatter: (row: TrainTaskTable) => statusTag(row.status) },
      { prop: "progress", label: "进度", width: 180, formatter: (row: TrainTaskTable) => progressCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 220,
        fixed: "right",
        align: "right",
        formatter: (row: TrainTaskTable) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
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

<style scoped>
.docker-cmd-pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  font-family: "Cascadia Code", "Fira Code", monospace;
  white-space: pre-wrap;
  overflow-x: auto;
  margin: 0;
}
</style>
