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
          :perm-create="['module_train:eval:create']"
          @add="handleOpenCreateDialog"
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
              <el-empty :image-size="80" :description="t('train.evalNoData')" />
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
              :label="t('train.serial')"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'model_version')?.show"
              key="model_version"
              :label="t('train.modelVersion')"
              prop="model_version"
              min-width="160"
              show-overflow-tooltip
            >
              <template #default="scope">
                {{ getModelName(scope.row.model_id) }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'framework')?.show"
              key="framework"
              :label="t('train.framework')"
              prop="framework"
              width="100"
            >
              <template #default="scope">
                <el-tag
                  :type="scope.row.framework === 'ultralytics' ? 'success' : 'primary'"
                  size="small"
                >
                  {{
                    scope.row.framework === "ultralytics"
                      ? "YOLO"
                      : scope.row.framework === "paddlex"
                        ? "PaddleX"
                        : "TorchKiln"
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'eval_dataset_id')?.show"
              key="eval_dataset_id"
              :label="t('train.evalDataset')"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="scope">
                {{ scope.row.eval_dataset_name || `#${scope.row.eval_dataset_id}` }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('train.status')"
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
              :label="t('train.progress')"
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
              v-if="contentCols.find((col) => col.prop === 'metrics')?.show"
              key="metrics"
              :label="t('train.evalMetrics')"
              prop="metrics"
              min-width="280"
            >
              <template #default="scope">
                <div v-if="scope.row.metrics" style="display: flex; flex-wrap: wrap; gap: 4px">
                  <el-tag
                    v-for="(v, k) in scope.row.metrics"
                    :key="k"
                    size="small"
                    class="metric-mono-tag"
                  >
                    {{ k }}: {{ typeof v === "number" ? v.toFixed(4) : v }}
                  </el-tag>
                </div>
                <span v-else style="color: var(--el-text-color-secondary)">--</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('train.createdTime')"
              prop="created_time"
              min-width="170"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('train.action')"
              align="center"
              min-width="240"
            >
              <template #default="scope">
                <el-button
                  v-if="scope.row.status === 'pending'"
                  v-hasPerm="['module_train:eval:create']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleStartEval(scope.row.id)"
                >
                  {{ t("train.startEval") }}
                </el-button>
                <el-button
                  v-if="scope.row.status === 'running'"
                  v-hasPerm="['module_train:eval:create']"
                  size="small"
                  type="danger"
                  link
                  icon="VideoPause"
                  @click="handleStopEval(scope.row.id)"
                >
                  {{ t("train.stop") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_train:eval:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="router.push('/train/eval/' + scope.row.id)"
                >
                  {{ t("train.detail") }}
                </el-button>
                <el-popconfirm
                  :title="t('train.evalDeleteConfirm')"
                  :confirm-button-text="t('train.delete')"
                  :cancel-button-text="t('train.cancel')"
                  width="180"
                  @confirm="handleDeleteEval([scope.row.id])"
                >
                  <template #reference>
                    <el-button
                      v-hasPerm="['module_train:eval:delete']"
                      size="small"
                      type="danger"
                      link
                      icon="Delete"
                    >
                      {{ t("train.delete") }}
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
      v-model="createDialogVisible"
      :title="t('train.evalCreateTitle')"
      append-to-body
      width="500px"
    >
      <el-form label-width="100px">
        <el-form-item :label="t('train.modelVersion')">
          <el-select
            v-model="createForm.modelId"
            filterable
            style="width: 100%"
            @change="onEvalModelChange"
          >
            <el-option
              v-for="m in modelVersions"
              :key="m.id"
              :label="`${m.name} v${m.version}`"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <template v-if="selectedModelFramework === 'paddlex'">
          <el-form-item :label="t('train.taskType')">
            <el-select v-model="createForm.hyperparams.mode" style="width: 100%">
              <el-option :label="t('train.taskTypeDet')" value="det" />
              <el-option :label="t('train.taskTypeRec')" value="rec" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('train.modelSize')">
            <el-select v-model="createForm.hyperparams.model_size" style="width: 100%">
              <el-option :label="t('train.modelSizeTiny')" value="tiny" />
              <el-option :label="t('train.modelSizeSmall')" value="small" />
              <el-option :label="t('train.modelSizeMedium')" value="medium" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item :label="t('train.evalDataset')">
          <el-select
            v-model="createForm.evalDatasetId"
            filterable
            style="width: 100%"
            @visible-change="(v: boolean) => v && loadDatasets()"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="imgsz">
          <el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" />
        </el-form-item>
        <el-form-item label="batch">
          <el-input-number v-model="createForm.hyperparams.batch" :min="1" :max="128" />
        </el-form-item>
        <el-form-item label="conf">
          <el-input-number
            v-model="createForm.hyperparams.conf"
            :min="0.001"
            :max="1"
            :step="0.01"
          />
        </el-form-item>
        <el-form-item label="iou">
          <el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item :label="t('train.gpuDevice')">
          <el-select
            v-model="createForm.hyperparams.device"
            :placeholder="t('train.selectDevice')"
            style="width: 100%"
          >
            <el-option
              v-for="n in deviceOptions"
              :key="n"
              :label="n === 'cpu' ? 'CPU' : `GPU ${n}`"
              :value="n"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">{{ t("train.cancel") }}</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateEval">
          {{ t("train.create") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { cachedOptions } from "@/composables/useOptions";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import PageSearch from "@/components/CURD/PageSearch.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
// 从 repo 页"评估"进入时携带 model_id（版本行 id）；兼容旧的 model_repo_id 参数
const modelRepoId = Number(route.query.model_id || route.query.model_repo_id || 0);

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const creating = ref(false);
const datasets = ref<any[]>([]);

const createDialogVisible = ref(false);
const modelVersions = ref<any[]>([]);
const selectedModelFramework = ref<string>("");
function onEvalModelChange(modelId: number | null) {
  const m = modelVersions.value.find((x: any) => x.id === modelId);
  selectedModelFramework.value = m?.framework || "";
}
const deviceOptions = ["0", "1", "2", "3", "4", "5", "6", "7", "cpu"];
const createForm = reactive({
  modelId: null as number | null,
  evalDatasetId: null as number | null,
  hyperparams: {
    imgsz: 640,
    batch: 16,
    conf: 0.001,
    iou: 0.6,
    device: "0",
    mode: "det",
    model_size: "tiny",
  },
});

let datasetsLoaded = false;
async function loadDatasets() {
  if (datasetsLoaded) return;
  datasetsLoaded = true;
  try {
    datasets.value = await cachedOptions(
      "annotation:datasets",
      async () =>
        (await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    datasetsLoaded = false;
  }
}

async function loadModelVersions() {
  try {
    modelVersions.value = await cachedOptions(
      "train:models",
      async () =>
        (await TrainAPI.getModelList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    /* 模型列表加载失败不阻塞页面与自动开窗 */
  }
}
loadModelVersions();

function getModelName(modelId: number) {
  const m = modelVersions.value.find((x: any) => x.id === modelId);
  return m ? `${m.name} v${m.version}` : `#${modelId}`;
}

function statusTag(s: string): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  return (
    (
      {
        pending: "info",
        running: "warning",
        success: "success",
        failed: "danger",
        cancelled: "info",
      } as any
    )[s] || "info"
  );
}
function statusLabel(s: string) {
  return (
    (
      {
        pending: t("train.statusPending"),
        running: t("train.evalStatusRunning"),
        success: t("train.statusSuccess"),
        failed: t("train.statusFailed"),
        cancelled: t("train.statusCancelled"),
      } as any
    )[s] || s
  );
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_train:eval",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("train.modelName"),
      type: "input",
      attrs: { placeholder: t("train.modelNamePlaceholder"), clearable: true },
    },
    {
      prop: "framework",
      label: t("train.framework"),
      type: "select",
      options: [{ label: t("train.torchKilnSelf"), value: "torchkiln" }],
      attrs: {
        placeholder: t("train.frameworkPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "status",
      label: t("train.status"),
      type: "select",
      options: [
        { label: t("train.statusPending"), value: "pending" },
        { label: t("train.evalStatusRunning"), value: "running" },
        { label: t("train.statusSuccess"), value: "success" },
        { label: t("train.statusFailed"), value: "failed" },
        { label: t("train.statusCancelled"), value: "cancelled" },
      ],
      attrs: {
        placeholder: t("train.statusPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
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
  { prop: "selection", label: t("train.selection"), show: true },
  { prop: "index", label: t("train.serial"), show: true },
  { prop: "model_version", label: t("train.modelVersion"), show: true },
  { prop: "framework", label: t("train.framework"), show: true },
  { prop: "eval_dataset_id", label: t("train.evalDatasetId"), show: true },
  { prop: "status", label: t("train.status"), show: true },
  { prop: "progress", label: t("train.progress"), show: true },
  { prop: "metrics", label: t("train.evalMetrics"), show: true },
  { prop: "created_time", label: t("train.createdTime"), show: true },
  { prop: "operation", label: t("train.action"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_train:eval",
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
    const r = await TrainAPI.getEvalList(params);
    const items = r.data?.data?.items || [];
    return {
      total: r.data?.data?.total ?? items.length,
      list: items,
    };
  },
});

function handleOpenCreateDialog() {
  loadDatasets();
  const curModel =
    modelVersions.value.find((m: any) => m.id === modelRepoId) ||
    modelVersions.value.find((m: any) => m.repo_id === modelRepoId);
  createForm.modelId = curModel?.id || null;
  createForm.evalDatasetId = curModel?.annotation_dataset_id || null;
  createForm.hyperparams = {
    imgsz: 640,
    batch: 16,
    conf: 0.001,
    iou: 0.6,
    device: "0",
    mode: "det",
    model_size: "tiny",
  };
  selectedModelFramework.value = curModel?.framework || "";
  createDialogVisible.value = true;
}

async function handleCreateEval() {
  if (!createForm.modelId || !createForm.evalDatasetId) {
    ElMessage.warning(t("train.warnSelectModelDataset"));
    return;
  }
  creating.value = true;
  try {
    // 关联所选版本的 id 与其所属仓库 id，而非路由缺省值 0
    const sel = modelVersions.value.find((m: any) => m.id === createForm.modelId);
    await TrainAPI.createEval({
      model_id: createForm.modelId,
      model_repo_id: sel?.repo_id ?? 0,
      eval_dataset_id: createForm.evalDatasetId,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success(t("train.saveSuccess"));
    createDialogVisible.value = false;
    createForm.modelId = null;
    createForm.evalDatasetId = null;
    createForm.hyperparams = {
      imgsz: 640,
      batch: 16,
      conf: 0.001,
      iou: 0.6,
      device: "0",
      mode: "det",
      model_size: "tiny",
    };
    refreshList();
  } finally {
    creating.value = false;
  }
}

async function handleStartEval(id: number) {
  try {
    await ElMessageBox.confirm(t("train.startEvalConfirm"), t("train.tipTitle"), { type: "info" });
    await TrainAPI.startEval(id);
    ElMessage.success(t("train.started"));
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

async function handleStopEval(id: number) {
  try {
    await ElMessageBox.confirm(t("train.stopEvalConfirm"), t("train.tipTitle"), {
      type: "warning",
    });
    await TrainAPI.stopEval(id);
    ElMessage.success(t("train.stopped"));
    refreshList();
  } catch {
    //
  }
}

async function handleDeleteEval(ids: number[]) {
  await TrainAPI.deleteEval(ids);
  ElMessage.success(t("train.deleteSuccess"));
  refreshList();
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    if (!contentRef.value?.pageData) return;
    try {
      // 只拉当前页用于刷新状态（后端 page_size 上限 100），并静默避免弹错
      const pg = (contentRef.value as any)?.pagination;
      const params = {
        page_no: pg?.currentPage ?? 1,
        page_size: pg?.pageSize ?? 10,
        ...(((contentRef.value as any)?.getFilterParams?.() as Record<string, any>) || {}),
      };
      const res = await TrainAPI.getEvalList(params, { silent: true });
      const fresh = (res.data?.data?.items || res.data?.data || []) as any[];
      const old = contentRef.value.pageData as any[];
      const merged = old.map((x: any) => {
        const f = fresh.find((y: any) => y.id === x.id);
        return f ? { ...x, progress: f.progress, status: f.status, metrics: f.metrics } : x;
      });
      contentRef.value.pageData = merged;
    } catch {
      /* ignore poll errors */
    }
  }, 5000);
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(async () => {
  startPoll();
  if (route.query.autoCreate === "1") {
    await loadModelVersions();
    handleOpenCreateDialog();
    router.replace({ query: {} });
  }
});
onBeforeUnmount(() => stopPoll());
</script>

<style scoped>
/* 指标名标签：等宽小字（替代内联 style） */
.metric-mono-tag {
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
}
</style>
