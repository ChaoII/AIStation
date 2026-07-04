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
              min-width="200"
            >
              <template #default="scope">
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
      width="560px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="100px"
        size="default"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="任务名称" prop="name">
              <el-input v-model="formData.name" placeholder="如: 缺陷检测v3" />
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
        <el-form-item label="框架" prop="framework">
          <el-radio-group v-model="formData.framework">
            <el-radio value="ultralytics">Ultralytics (YOLO)</el-radio>
            <el-radio value="paddlex">PaddleX</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="超参数 (JSON)" prop="hyperparams">
          <el-input
            v-model="formData.hyperparams"
            type="textarea"
            :rows="6"
            placeholder='{"epochs":100,"batch":16,"lr":0.01,"model":"yolo11n.pt"}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          开始训练
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
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
  hyperparams: "{}" as string,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  dataset_id: undefined as number | undefined,
  framework: "ultralytics" as string,
  hyperparams: "{}" as string,
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

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
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
    Object.assign(formData, res.data.data);
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
        const hp = JSON.parse(formData.hyperparams || "{}");
        await TrainAPI.createTask({
          name: formData.name,
          dataset_id: formData.dataset_id,
          framework: formData.framework,
          hyperparams: hp,
        });
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        ElMessage.success("训练任务已创建");
      } catch (e: any) {
        if (e instanceof SyntaxError) {
          ElMessage.error("超参数 JSON 格式错误");
        }
      } finally {
        submitLoading.value = false;
      }
    }
  });
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
</script>
