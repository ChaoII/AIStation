<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_train:task:create']"
          @add="handleOpenDialog('create')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              fixed
              label="序号"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="任务名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'framework')?.show"
              key="framework"
              label="框架"
              prop="framework"
              width="100"
            >
              <template #default="scope">
                <el-tag
                  :type="scope.row.framework === 'ultralytics' ? 'success' : 'primary'"
                  size="small"
                >
                  {{ scope.row.framework === "ultralytics" ? "YOLO" : "PaddleX" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'dataset_id')?.show"
              key="dataset_id"
              label="数据集ID"
              prop="dataset_id"
              width="90"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              prop="status"
              width="110"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'progress')?.show"
              key="progress"
              label="进度"
              prop="progress"
              width="180"
            >
              <template #default="scope">
                <el-progress
                  :percentage="scope.row.progress || 0"
                  :stroke-width="14"
                  :text-inside="true"
                  :status="
                    scope.row.status === 'failed'
                      ? 'exception'
                      : scope.row.status === 'success'
                        ? 'success'
                        : undefined
                  "
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              label="创建时间"
              prop="created_time"
              min-width="170"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="220"
            >
              <template #default="scope">
                <el-button
                  v-if="scope.row.status === 'pending'"
                  v-hasPerm="['module_train:task:update']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleStart(scope.row)"
                >
                  开始训练
                </el-button>
                <el-button
                  v-if="scope.row.status === 'running'"
                  v-hasPerm="['module_train:task:update']"
                  size="small"
                  type="danger"
                  link
                  icon="VideoPause"
                  @click="handleStop(scope.row.id)"
                >
                  停止
                </el-button>
                <el-button
                  v-hasPerm="['module_train:task:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="router.push('/train/task/' + scope.row.id)"
                >
                  详情
                </el-button>
                <el-popconfirm
                  title="确定删除该任务？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="handleDelete(scope.row.id)"
                  width="180"
                >
                  <template #reference>
                    <el-button
                      v-hasPerm="['module_train:task:delete']"
                      size="small"
                      type="danger"
                      link
                      icon="Delete"
                    >
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="680px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="120px"
        size="default"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="任务名称" prop="name">
              <el-input v-model="formData.name" placeholder="如: 缺陷检测v3" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="框架" prop="framework">
              <el-radio-group
                v-model="formData.framework"
                @change="(v: any) => onFrameworkChange(String(v))"
              >
                <el-radio value="ultralytics">Ultralytics</el-radio>
                <el-radio value="paddlex">PaddleX</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="选择数据集" prop="dataset_id">
          <el-select
            v-model="formData.dataset_id"
            filterable
            style="width: 100%"
            placeholder="请选择标注数据集"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-divider>超参数配置</el-divider>

        <!-- Ultralytics hyperparams -->
        <template v-if="formData.framework === 'ultralytics'">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="模型" prop="hpModel">
                <el-select v-model="hpForm.model" style="width: 100%">
                  <el-option label="YOLO11n" value="yolo11n.pt" />
                  <el-option label="YOLO11s" value="yolo11s.pt" />
                  <el-option label="YOLO11m" value="yolo11m.pt" />
                  <el-option label="YOLO11l" value="yolo11l.pt" />
                  <el-option label="YOLO11x" value="yolo11x.pt" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Epochs">
                <el-input-number v-model="hpForm.epochs" :min="1" :max="1000" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="Batch Size">
                <el-input-number v-model="hpForm.batch" :min="1" :max="512" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Learning Rate">
                <el-input-number
                  v-model="hpForm.lr"
                  :min="0.0001"
                  :max="1"
                  :step="0.001"
                  :precision="4"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="Optimizer">
                <el-select v-model="hpForm.optimizer" style="width: 100%">
                  <el-option label="AdamW" value="AdamW" />
                  <el-option label="SGD" value="SGD" />
                  <el-option label="Adam" value="Adam" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Image Size">
                <el-input-number
                  v-model="hpForm.imgsz"
                  :min="32"
                  :max="4096"
                  :step="32"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="Workers">
                <el-input-number v-model="hpForm.workers" :min="0" :max="32" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="GPU 设备">
                <el-input v-model="hpForm.device" placeholder="如: 0" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- PaddleX hyperparams -->
        <template v-else>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="模型" prop="hpModel">
                <el-select v-model="hpForm.model" style="width: 100%">
                  <el-option label="PP-YOLOE" value="PP-YOLOE" />
                  <el-option label="PP-YOLO" value="PP-YOLO" />
                  <el-option label="PP-PicoDet" value="PP-PicoDet" />
                  <el-option label="RT-DETR" value="RT-DETR" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Epochs">
                <el-input-number v-model="hpForm.epochs" :min="1" :max="1000" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="Batch Size">
                <el-input-number v-model="hpForm.batch" :min="1" :max="512" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Learning Rate">
                <el-input-number
                  v-model="hpForm.lr"
                  :min="0.0001"
                  :max="1"
                  :step="0.001"
                  :precision="4"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="GPU 设备">
                <el-input v-model="hpForm.device" placeholder="如: 0" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="预训练权重">
                <el-switch v-model="hpForm.pretrained" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          创建任务
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const router = useRouter();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();

const datasets = ref<any[]>([]);
(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
})();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_train:task",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "任务名称",
      type: "input",
      attrs: { placeholder: "请输入任务名称", clearable: true },
    },
    {
      prop: "framework",
      label: "框架",
      type: "select",
      options: [
        { label: "Ultralytics", value: "ultralytics" },
        { label: "PaddleX", value: "paddlex" },
      ],
      attrs: { placeholder: "请选择框架", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "待开始", value: "pending" },
        { label: "训练中", value: "running" },
        { label: "已完成", value: "success" },
        { label: "失败", value: "failed" },
        { label: "已取消", value: "cancelled" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "任务名称", show: true },
  { prop: "framework", label: "框架", show: true },
  { prop: "dataset_id", label: "数据集ID", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "progress", label: "进度", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_train:task",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async () => {
    const res = await TrainAPI.getTaskList();
    return {
      total: (res.data?.data || []).length,
      list: res.data?.data || [],
    };
  },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  dataset_id: undefined as number | undefined,
  framework: "ultralytics" as string,
});

const defaultHpUltra = () => ({
  model: "yolo11n.pt",
  epochs: 100,
  batch: 16,
  lr: 0.01,
  optimizer: "AdamW",
  imgsz: 640,
  workers: 4,
  device: "0",
});

const defaultHpPaddle = () => ({
  model: "PP-YOLOE",
  epochs: 100,
  batch: 16,
  lr: 0.01,
  device: "0",
  pretrained: true,
});

const hpForm = reactive<Record<string, any>>(defaultHpUltra());

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  dataset_id: undefined as number | undefined,
  framework: "ultralytics" as string,
};

const rules = reactive({
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  dataset_id: [{ required: true, message: "请选择数据集", trigger: "change" }],
});

function statusTag(s: string): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  return (
    (
      {
        pending: "info",
        running: "warning",
        success: "success",
        failed: "danger",
        cancelled: "info",
      } as Record<string, "info" | "warning" | "success" | "danger">
    )[s] || "info"
  );
}

function statusLabel(s: string) {
  return (
    {
      pending: "待开始",
      running: "训练中",
      success: "已完成",
      failed: "失败",
      cancelled: "已取消",
    }[s] || s
  );
}

function onFrameworkChange(fw: string) {
  Object.keys(hpForm).forEach((k) => delete hpForm[k]);
  if (fw === "ultralytics") {
    Object.assign(hpForm, defaultHpUltra());
  } else {
    Object.assign(hpForm, defaultHpPaddle());
  }
}

function buildHyperparams(): Record<string, any> {
  if (formData.framework === "ultralytics") {
    return {
      model: hpForm.model,
      epochs: hpForm.epochs,
      batch: hpForm.batch,
      lr: hpForm.lr,
      optimizer: hpForm.optimizer,
      imgsz: hpForm.imgsz,
      workers: hpForm.workers,
      device: hpForm.device,
    };
  }
  return {
    model: hpForm.model,
    epochs: hpForm.epochs,
    batch: hpForm.batch,
    lr: hpForm.lr,
    device: hpForm.device,
    pretrained: hpForm.pretrained,
  };
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  onFrameworkChange("ultralytics");
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑训练任务";
    const res = await TrainAPI.getTaskDetail(id);
    const data = res.data.data;
    Object.assign(formData, {
      id: data.id,
      name: data.name,
      dataset_id: data.dataset_id,
      framework: data.framework,
    });
    onFrameworkChange(data.framework);
    if (data.hyperparams) {
      Object.assign(hpForm, data.hyperparams);
    }
  } else {
    dialogVisible.title = "新建训练任务";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      try {
        await TrainAPI.createTask({
          name: formData.name,
          dataset_id: formData.dataset_id,
          framework: formData.framework,
          hyperparams: buildHyperparams(),
        });
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        ElMessage.success("训练任务已创建");
      } catch (e: any) {
        ElMessage.error(e?.msg || "创建失败");
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function handleStart(row: any) {
  try {
    await ElMessageBox.confirm(`确定开始训练任务「${row.name}」？`, "提示", { type: "info" });
    ElMessage.info("开始训练功能需要调度器支持");
  } catch {
    //
  }
}

async function handleStop(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该训练任务？", "提示", { type: "warning" });
    await TrainAPI.stopTask(id);
    ElMessage.success("训练已停止");
    refreshList();
  } catch {
    //
  }
}

async function handleDelete(id: number) {
  await TrainAPI.deleteTask([id]);
  ElMessage.success("已删除");
  refreshList();
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPoll() {
  stopPoll();
  pollTimer = setInterval(() => {
    refreshList();
  }, 5000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(() => startPoll());
onBeforeUnmount(() => stopPoll());
</script>
