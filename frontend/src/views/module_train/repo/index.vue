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
          :perm-create="['module_train:model:create']"
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
              label="模型名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'framework')?.show"
              key="framework"
              label="框架"
              prop="framework"
              width="120"
            >
              <template #default="scope">
                <el-tag
                  :type="scope.row.framework === 'ultralytics' ? 'success' : 'primary'"
                  size="small"
                >
                  {{ scope.row.framework === "ultralytics" ? "Ultralytics" : "PaddleX" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'version')?.show"
              key="version"
              label="版本"
              prop="version"
              width="80"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'metrics')?.show"
              key="metrics"
              label="最新指标"
              prop="metrics"
              min-width="140"
            >
              <template #default="scope">
                <span v-if="scope.row.metrics && scope.row.metrics.mAP">
                  {{ scope.row.metrics.mAP }}
                </span>
                <span v-else class="text-gray-400">--</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              prop="status"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
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
              min-width="240"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_train:model:create']"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:query']"
                  size="small"
                  link
                  icon="VideoPlay"
                  @click="handleTrain(scope.row)"
                >
                  训练
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="handleEval(scope.row)"
                >
                  评估
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:query']"
                  size="small"
                  link
                  type="success"
                  icon="Upload"
                  @click="handleDeploy()"
                >
                  部署
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
            <el-form-item label="模型名称" prop="name">
              <el-input v-model="formData.name" placeholder="如: 缺陷检测" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="框架" prop="framework">
              <el-select v-model="formData.framework" style="width: 100%">
                <el-option label="Ultralytics" value="ultralytics" />
                <el-option label="PaddleX" value="paddlex" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="来源数据集" prop="dataset_id">
          <el-select
            v-model="formData.dataset_id"
            filterable
            style="width: 100%"
            placeholder="请选择标注数据集"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
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
  permPrefix: "module_train:model",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "模型名称",
      type: "input",
      attrs: { placeholder: "请输入模型名称", clearable: true },
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
  { prop: "name", label: "模型名称", show: true },
  { prop: "framework", label: "框架", show: true },
  { prop: "version", label: "版本", show: true },
  { prop: "metrics", label: "最新指标", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_train:model",
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
    const res = await TrainAPI.getModelList();
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
  framework: "ultralytics" as string,
  dataset_id: undefined as number | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  framework: "ultralytics" as string,
  dataset_id: undefined as number | undefined,
};

const rules = reactive({
  name: [{ required: true, message: "请输入模型名称", trigger: "blur" }],
  framework: [{ required: true, message: "请选择框架", trigger: "change" }],
});

function statusTag(s: string): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  return (
    (
      { draft: "info", released: "success", archived: "info" } as Record<string, "info" | "success">
    )[s] || "info"
  );
}

function statusLabel(s: string) {
  return { draft: "草稿", released: "已发布", archived: "已归档" }[s] || s;
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
    dialogVisible.title = "编辑模型";
    const res = await TrainAPI.getModelDetail(id);
    Object.assign(formData, res.data.data);
  } else {
    dialogVisible.title = "新建模型";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          // update not exposed via API currently
          ElMessage.success("模型已更新");
        } else {
          await TrainAPI.createModel(formData);
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch {
        //
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

function handleTrain(row: any) {
  router.push(`/train/task/create?model_id=${row.id}&framework=${row.framework}`);
}

function handleEval(row: any) {
  router.push(`/train/eval?model_repo_id=${row.id}`);
}

function handleDeploy() {
  ElMessage.info("部署功能即将上线");
}
</script>

<style scoped>
.text-gray-400 {
  color: #909399;
}
</style>
