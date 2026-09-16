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
          :perm-delete="['module_train:model:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
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
              label="仓库名称"
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
                  {{ frameworkLabel(scope.row.framework) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'version_count')?.show"
              key="version_count"
              label="版本数"
              prop="version_count"
              width="90"
              align="center"
            />
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
                <el-button size="small" link type="primary" @click="openVersions(scope.row)">
                  版本
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  link
                  icon="edit"
                  @click="handleEditRepo(scope.row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:delete']"
                  size="small"
                  link
                  icon="delete"
                  type="danger"
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
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
        <el-form-item label="来源数据集" prop="annotation_dataset_id">
          <el-select
            v-model="formData.annotation_dataset_id"
            filterable
            style="width: 100%"
            placeholder="请选择标注数据集"
            @visible-change="(v: boolean) => v && loadDatasets()"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="模型描述（可选）"
          />
        </el-form-item>
        <el-form-item v-if="dialogVisible.type === 'update'" label="状态" prop="status">
          <el-select v-model="formData.status" style="width: 100%">
            <el-option label="草稿" value="draft" />
            <el-option label="已发布" value="released" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <ModelExportDialog
      v-model:visible="exportDialogVisible"
      :model-id="exportModelId"
      :model-name="exportModelName"
      @done="refreshList"
    />

    <el-drawer v-model="versionsVisible" :title="`版本 - ${versionsRepoName}`" size="760px">
      <el-table v-loading="versionsLoading" :data="versions" border size="small">
        <el-table-column label="版本" prop="version" width="80" align="center" />
        <el-table-column label="框架" prop="framework" width="110" />
        <el-table-column label="状态" prop="status" width="100" />
        <el-table-column label="创建时间" prop="created_time" min-width="170" />
        <el-table-column label="操作" min-width="320" align="center">
          <template #default="{ row }">
            <el-button size="small" link @click="handleTrain(row)">训练</el-button>
            <el-button size="small" link @click="handleEval(row)">评估</el-button>
            <el-button size="small" link @click="handlePredict(row)">预测</el-button>
            <el-button size="small" link @click="handleExport(row)">导出</el-button>
            <el-button size="small" link @click="handleDeploy(row)">部署</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!versionsLoading && versions.length === 0" description="暂无版本" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import ModelExportDialog from "@/components/ModelExportDialog/index.vue";
import { cachedOptions } from "@/composables/useOptions";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const router = useRouter();
const route = useRoute();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

// 从任务详情"查看模型"进入：定位到对应模型仓库
onMounted(() => {
  const q = route.query.model_id || route.query.model_repo_id;
  if (q) {
    const id = Number(q);
    if (id) {
      setTimeout(() => {
        const rows = (contentRef.value as any)?.pageData || [];
        const hit = rows.find((r: any) => r.id === id || r.repo_id === id);
        ElMessage.info(hit ? `已定位到模型 ${hit.name || `#${id}`}` : `模型 #${id} 不在当前页`);
      }, 600);
    }
  }
});

const submitLoading = ref(false);
const dataFormRef = ref();

const datasets = ref<any[]>([]);
let datasetsLoaded = false;
async function loadDatasets() {
  if (datasetsLoaded) return;
  datasetsLoaded = true;
  try {
    datasets.value = await cachedOptions(
      "annotation:datasets",
      async () => (await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    datasetsLoaded = false;
  }
}

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
  { prop: "name", label: "仓库名称", show: true },
  { prop: "framework", label: "框架", show: true },
  { prop: "version_count", label: "版本数", show: true },
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
  indexAction: async (params) => {
    const res = await TrainAPI.getModelRepos(params);
    const items = res.data?.data?.items || [];
    return {
      total: res.data?.data?.total ?? items.length,
      list: items,
    };
  },
  deleteAction: async (ids) => {
    await TrainAPI.deleteModelRepos(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: "警告",
    message: "确认删除所选模型? 删除后无法恢复。",
    type: "warning",
  },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const exportDialogVisible = ref(false);

const versionsVisible = ref(false);
const versionsLoading = ref(false);
const versions = ref<any[]>([]);
const versionsRepoName = ref("");

async function openVersions(repo: any) {
  versionsVisible.value = true;
  versionsRepoName.value = repo.name;
  versionsLoading.value = true;
  try {
    const res = await TrainAPI.getModelVersions(repo.id);
    versions.value = res.data?.data || [];
  } finally {
    versionsLoading.value = false;
  }
}
const exportModelId = ref(0);
const exportModelName = ref("");

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  framework: "ultralytics" as string,
  annotation_dataset_id: undefined as number | undefined,
  description: undefined as string | undefined,
  status: undefined as string | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  framework: "ultralytics" as string,
  annotation_dataset_id: undefined as number | undefined,
  description: undefined as string | undefined,
  status: undefined as string | undefined,
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

function frameworkLabel(fw?: string) {
  return (
    (
      {
        ultralytics: "Ultralytics",
        paddlex: "PaddleX",
      } as any
    )[fw || ""] ||
    fw ||
    "—"
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
  loadDatasets();
  if (id && type === "update") {
    dialogVisible.title = "编辑模型仓库";
    const res = await TrainAPI.getModelDetail(id);
    Object.assign(formData, res.data.data);
  } else {
    dialogVisible.title = "新建模型仓库";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

function handleEditRepo(row: any) {
  dialogVisible.type = "update";
  dialogVisible.title = "编辑模型仓库";
  Object.assign(formData, {
    id: row.id,
    name: row.name,
    framework: row.framework,
    annotation_dataset_id: row.annotation_dataset_id,
    description: row.description,
    status: row.status,
  });
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        const payload = {
          name: formData.name,
          framework: formData.framework,
          annotation_dataset_id: formData.annotation_dataset_id,
          description: formData.description,
          status: formData.status,
        };
        if (id) {
          await TrainAPI.updateModelRepo(id, payload);
        } else {
          await TrainAPI.createModelRepo(payload);
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

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

function handleTrain(row: any) {
  router.push(`/train/task?model_id=${row.id}&framework=${row.framework}`);
}

function handleEval(row: any) {
  router.push(`/train/eval?model_id=${row.id}`);
}

function handlePredict(row: any) {
  router.push({
    path: "/train/predict",
    query: { model_id: String(row.id), model_repo_id: String(row.repo_id || 0), autoCreate: "1" },
  });
}

function handleDeploy(row: any) {
  // Create a deploy record, show API Key, then navigate to deploy page
  TrainAPI.createDeploy(
    {
      model_id: row.id,
      name: `${row.name} v${row.version}`,
      device: "0",
      hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640 },
    },
    true
  )
    .then((r) => {
      const d = r.data?.data;
      if (d?.api_key) {
        // Show API Key in a brief alert, then navigate
        ElMessage.success(`API Key: ${d.api_key}（已复制到剪贴板）`);
        navigator.clipboard.writeText(d.api_key).catch(() => {});
      } else {
        ElMessage.success("部署已创建");
      }
      router.push("/train/deploy");
    })
    .catch((e: any) => {
      // 该请求带 _silent，拦截器不会提示，错误必须在此处展示
      ElMessage.error(e?.msg || e?.response?.data?.msg || e?.message || "创建部署失败");
    });
}

function handleExport(row: any) {
  exportModelId.value = row.id;
  exportModelName.value = row.name;
  exportDialogVisible.value = true;
}
</script>

<style scoped>
.text-gray-400 {
  color: #909399;
}
</style>
