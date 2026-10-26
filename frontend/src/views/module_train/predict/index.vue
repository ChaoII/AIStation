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
          :perm-create="['module_train:predict:create']"
          @add="showCreateDialog = true"
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
              <el-empty :image-size="80" :description="t('train.predictNoData')" />
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
              min-width="150"
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
              v-if="contentCols.find((col) => col.prop === 'source_type')?.show"
              key="source_type"
              :label="t('train.sourceType')"
              prop="source_type"
              width="120"
            >
              <template #default="scope">
                {{
                  scope.row.source_type === "dataset" ? t("train.dataset") : t("train.uploadImage")
                }}
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
                  v-hasPerm="['module_train:predict:create']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleStart(scope.row.id)"
                >
                  {{ t("train.startPredict") }}
                </el-button>
                <el-button
                  v-if="scope.row.status === 'running'"
                  v-hasPerm="['module_train:predict:create']"
                  size="small"
                  type="danger"
                  link
                  icon="VideoPause"
                  @click="handleStop(scope.row.id)"
                >
                  {{ t("train.stop") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_train:predict:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="router.push('/train/predict/' + scope.row.id)"
                >
                  {{ t("train.detail") }}
                </el-button>
                <el-button
                  v-if="scope.row.result_zip_path"
                  v-hasPerm="['module_train:predict:query']"
                  size="small"
                  link
                  type="primary"
                  icon="Download"
                  @click="downloadZip(scope.row.result_zip_path)"
                >
                  {{ t("train.download") }}
                </el-button>
                <el-popconfirm
                  :title="t('train.predictDeleteConfirm')"
                  :confirm-button-text="t('train.delete')"
                  :cancel-button-text="t('train.cancel')"
                  width="180"
                  @confirm="handleDelete([scope.row.id])"
                >
                  <template #reference>
                    <el-button
                      v-hasPerm="['module_train:predict:delete']"
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

    <!-- Create Dialog -->
    <EnhancedDialog
      v-model="showCreateDialog"
      :title="t('train.predictCreateTitle')"
      append-to-body
      width="600px"
    >
      <el-form label-width="100px">
        <el-form-item :label="t('train.modelVersion')" required>
          <el-select
            v-model="createForm.modelId"
            filterable
            style="width: 100%"
            :placeholder="t('train.selectModelVersion')"
            @change="onPredictModelChange"
          >
            <el-option
              v-for="m in models"
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
        <el-form-item :label="t('train.sourceType')">
          <el-radio-group v-model="createForm.sourceType">
            <el-radio value="dataset">{{ t("train.fromDataset") }}</el-radio>
            <el-radio value="upload">{{ t("train.uploadImage") }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="createForm.sourceType === 'dataset'"
          :label="t('train.dataset')"
          required
        >
          <el-select
            v-model="createForm.sourceDatasetId"
            filterable
            style="width: 100%"
            :placeholder="t('train.selectDataset')"
            @visible-change="(v: boolean) => v && loadDatasets()"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'upload'" :label="t('train.image')" required>
          <el-upload
            ref="uploadRef"
            list-type="picture-card"
            :auto-upload="false"
            multiple
            @change="onUploadChange"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
        <el-form-item label="conf">
          <el-input-number
            v-model="createForm.hyperparams.conf"
            :min="0.01"
            :max="1"
            :step="0.05"
          />
        </el-form-item>
        <el-form-item label="iou">
          <el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="imgsz">
          <el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">{{ t("train.cancel") }}</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">
          {{ t("train.create") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { cachedOptions } from "@/composables/useOptions";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import PageSearch from "@/components/CURD/PageSearch.vue";
import { Plus } from "@element-plus/icons-vue";
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
const route = useRoute();
const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const uploadRef = ref<any>(null);

const showCreateDialog = ref(false);
const creating = ref(false);
const models = ref<any[]>([]);
const datasets = ref<any[]>([]);
const pendingFiles = ref<File[]>([]);

const selectedModelFramework = ref<string>("");
function onPredictModelChange(modelId: number | null) {
  const m = models.value.find((x: any) => x.id === modelId);
  selectedModelFramework.value = m?.framework || "";
}
const createForm = reactive({
  modelId: null as number | null,
  sourceType: "dataset",
  sourceDatasetId: null as number | null,
  hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640, device: "0", mode: "det", model_size: "tiny" },
});

onMounted(async () => {
  // 先加载模型版本（自动开窗预填依赖它）
  try {
    models.value = await cachedOptions(
      "train:models",
      async () =>
        (await TrainAPI.getModelList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    /* 模型列表加载失败不阻塞页面与自动开窗 */
  }

  if (route.query.autoCreate === "1") {
    const modelId = Number(route.query.model_id || 0);
    if (modelId && models.value.some((m: any) => m.id === modelId)) {
      createForm.modelId = modelId;
      onPredictModelChange(modelId);
      showCreateDialog.value = true;
    }
    router.replace({ query: {} });
  }
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

function getModelName(modelId: number) {
  const m = models.value.find((x: any) => x.id === modelId);
  return m ? `${m.name} v${m.version}` : `#${modelId}`;
}

function statusTag(s: string) {
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
        running: t("train.predictStatusRunning"),
        success: t("train.statusSuccess"),
        failed: t("train.statusFailed"),
        cancelled: t("train.statusCancelled"),
      } as any
    )[s] || s
  );
}

function onUploadChange(_file: any, fileList: any[]) {
  pendingFiles.value = fileList.map((f) => f.raw).filter(Boolean);
}

async function handleCreate() {
  if (!createForm.modelId) {
    ElMessage.warning(t("train.warnSelectModelVersion"));
    return;
  }
  if (createForm.sourceType === "dataset" && !createForm.sourceDatasetId) {
    ElMessage.warning(t("train.warnSelectDataset"));
    return;
  }
  if (createForm.sourceType === "upload" && pendingFiles.value.length === 0) {
    ElMessage.warning(t("train.warnUploadImage"));
    return;
  }

  creating.value = true;
  try {
    let sourceImages: string[] | undefined;
    if (createForm.sourceType === "upload") {
      const r = await TrainAPI.uploadPredictImages(pendingFiles.value);
      sourceImages = r.data?.data;
    }

    await TrainAPI.createPredict({
      model_id: createForm.modelId,
      model_repo_id: models.value.find((m: any) => m.id === createForm.modelId)?.repo_id || 0,
      source_type: createForm.sourceType,
      source_dataset_id: createForm.sourceDatasetId,
      source_images: sourceImages,
      hyperparams: createForm.hyperparams,
    });
    ElMessage.success(t("train.saveSuccess"));
    showCreateDialog.value = false;
    createForm.modelId = null;
    createForm.sourceType = "dataset";
    createForm.sourceDatasetId = null;
    createForm.hyperparams = {
      conf: 0.25,
      iou: 0.45,
      imgsz: 640,
      device: "0",
      mode: "det",
      model_size: "tiny",
    };
    selectedModelFramework.value = "";
    pendingFiles.value = [];
    if (uploadRef.value) uploadRef.value.uploadFiles = [];
    refreshList();
  } finally {
    creating.value = false;
  }
}

async function handleStart(id: number) {
  try {
    await ElMessageBox.confirm(t("train.startPredictConfirm"), t("train.tipTitle"), {
      type: "info",
    });
    await TrainAPI.startPredict(id);
    ElMessage.success(t("train.started"));
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

async function handleStop(id: number) {
  try {
    await ElMessageBox.confirm(t("train.stopPredictConfirm"), t("train.tipTitle"), {
      type: "warning",
    });
    await TrainAPI.stopPredict(id);
    ElMessage.success(t("train.stopped"));
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

function downloadZip(url: string) {
  window.open(url, "_blank");
}

async function handleDelete(ids: number[]) {
  await TrainAPI.deletePredict(ids);
  ElMessage.success(t("train.deleteSuccess"));
  refreshList();
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_train:predict",
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
        { label: t("train.predictStatusRunning"), value: "running" },
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
  { prop: "source_type", label: t("train.sourceType"), show: true },
  { prop: "status", label: t("train.status"), show: true },
  { prop: "progress", label: t("train.progress"), show: true },
  { prop: "created_time", label: t("train.createdTime"), show: true },
  { prop: "operation", label: t("train.action"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_train:predict",
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
    const r = await TrainAPI.getPredictList(params);
    const items = r.data?.data?.items || [];
    return {
      total: r.data?.data?.total ?? items.length,
      list: items,
    };
  },
});

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
      const res = await TrainAPI.getPredictList(params, { silent: true });
      const fresh = (res.data?.data?.items || res.data?.data || []) as any[];
      const old = contentRef.value.pageData as any[];
      const merged = old.map((x: any) => {
        const f = fresh.find((y: any) => y.id === x.id);
        return f ? { ...x, progress: f.progress, status: f.status } : x;
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

onMounted(() => startPoll());
onBeforeUnmount(() => stopPoll());
</script>
