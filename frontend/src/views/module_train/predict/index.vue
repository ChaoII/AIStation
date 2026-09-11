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
              <el-empty :image-size="80" description="暂无预测任务" />
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
              v-if="contentCols.find((col) => col.prop === 'model_version')?.show"
              key="model_version"
              label="模型版本"
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
              v-if="contentCols.find((col) => col.prop === 'source_type')?.show"
              key="source_type"
              label="图片来源"
              prop="source_type"
              width="120"
            >
              <template #default="scope">
                {{ scope.row.source_type === "dataset" ? "数据集" : "上传图片" }}
              </template>
            </el-table-column>
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
                  开始预测
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
                  停止
                </el-button>
                <el-button
                  v-hasPerm="['module_train:predict:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="router.push('/train/predict/' + scope.row.id)"
                >
                  详情
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
                  下载
                </el-button>
                <el-popconfirm
                  title="确定删除该预测？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
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

    <!-- Create Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      title="创建预测任务"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px">
        <el-form-item label="模型版本" required>
          <el-select
            v-model="createForm.modelId"
            filterable
            style="width: 100%"
            placeholder="选择模型版本"
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
          <el-form-item label="任务类型">
            <el-select v-model="createForm.hyperparams.mode" style="width: 100%">
              <el-option label="文本检测 (det)" value="det" />
              <el-option label="文本识别 (rec)" value="rec" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型规格">
            <el-select v-model="createForm.hyperparams.model_size" style="width: 100%">
              <el-option label="tiny（轻量）" value="tiny" />
              <el-option label="small（推荐）" value="small" />
              <el-option label="medium（高精度）" value="medium" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item label="图片来源">
          <el-radio-group v-model="createForm.sourceType">
            <el-radio value="dataset">从数据集</el-radio>
            <el-radio value="upload">上传图片</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'dataset'" label="数据集" required>
          <el-select
            v-model="createForm.sourceDatasetId"
            filterable
            style="width: 100%"
            placeholder="选择数据集"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'upload'" label="图片" required>
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
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
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
  const [mRes, dsRes] = await Promise.all([
    TrainAPI.getModelList(),
    AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 }),
  ]);
  models.value = mRes.data?.data?.items || [];
  datasets.value = dsRes.data?.data?.items || [];
  refreshList();
});

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
        pending: "待开始",
        running: "预测中",
        success: "已完成",
        failed: "失败",
        cancelled: "已取消",
      } as any
    )[s] || s
  );
}

function onUploadChange(_file: any, fileList: any[]) {
  pendingFiles.value = fileList.map((f) => f.raw).filter(Boolean);
}

async function handleCreate() {
  if (!createForm.modelId) {
    ElMessage.warning("请选择模型版本");
    return;
  }
  if (createForm.sourceType === "dataset" && !createForm.sourceDatasetId) {
    ElMessage.warning("请选择数据集");
    return;
  }
  if (createForm.sourceType === "upload" && pendingFiles.value.length === 0) {
    ElMessage.warning("请上传图片");
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
      model_repo_id: models.value.find((m: any) => m.id === createForm.modelId)?.id || 0,
      source_type: createForm.sourceType,
      source_dataset_id: createForm.sourceDatasetId,
      source_images: sourceImages,
      hyperparams: createForm.hyperparams,
    });
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
    await ElMessageBox.confirm("确定开始预测？", "提示", { type: "info" });
    await TrainAPI.startPredict(id);
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

async function handleStop(id: number) {
  try {
    await ElMessageBox.confirm("确定停止预测？", "提示", { type: "warning" });
    await TrainAPI.stopPredict(id);
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
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "待开始", value: "pending" },
        { label: "预测中", value: "running" },
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
  { prop: "model_version", label: "模型版本", show: true },
  { prop: "framework", label: "框架", show: true },
  { prop: "source_type", label: "图片来源", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "progress", label: "进度", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
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
      const params = { page_no: 1, page_size: 200 };
      const res = await TrainAPI.getPredictList(params);
      const fresh = (res.data?.data?.items || res.data?.data || []) as any[];
      const old = contentRef.value.pageData as any[];
      for (const f of fresh) {
        const o = old.find((x: any) => x.id === f.id);
        if (o) {
          o.progress = f.progress;
          o.status = f.status;
        }
      }
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
