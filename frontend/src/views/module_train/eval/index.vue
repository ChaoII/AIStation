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
              <el-empty :image-size="80" description="暂无评估记录" />
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
              v-if="contentCols.find((col) => col.prop === 'eval_dataset_id')?.show"
              key="eval_dataset_id"
              label="评估数据集"
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
              v-if="contentCols.find((col) => col.prop === 'metrics')?.show"
              key="metrics"
              label="评估指标"
              prop="metrics"
              min-width="280"
            >
              <template #default="scope">
                <div v-if="scope.row.metrics" style="display: flex; flex-wrap: wrap; gap: 4px">
                  <el-tag
                    v-for="(v, k) in scope.row.metrics"
                    :key="k"
                    size="small"
                    style="font-family: monospace; font-size: 12px"
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
                  v-hasPerm="['module_train:eval:create']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleStartEval(scope.row.id)"
                >
                  开始评估
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
                  停止
                </el-button>
                <el-button
                  v-hasPerm="['module_train:eval:query']"
                  size="small"
                  link
                  icon="Search"
                  @click="router.push('/train/eval/' + scope.row.id)"
                >
                  详情
                </el-button>
                <el-popconfirm
                  title="确定删除该评估？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
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

    <el-dialog v-model="createDialogVisible" title="创建评估" width="500px">
      <el-form label-width="100px">
        <el-form-item label="模型版本">
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
        <el-form-item label="评估数据集">
          <el-select v-model="createForm.evalDatasetId" filterable style="width: 100%">
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
        <el-form-item label="GPU 设备">
          <el-input v-model="createForm.hyperparams.device" placeholder="如: 0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreateEval">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useCrudList } from "@/components/CURD/useCrudList";
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

(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
})();

async function loadModelVersions() {
  const r = await TrainAPI.getModelList({ page_no: 1, page_size: 100 });
  modelVersions.value = r.data?.data?.items || [];
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
        pending: "待开始",
        running: "评估中",
        success: "已完成",
        failed: "失败",
        cancelled: "已取消",
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
        { label: "评估中", value: "running" },
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
  { prop: "eval_dataset_id", label: "评估数据集ID", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "progress", label: "进度", show: true },
  { prop: "metrics", label: "评估指标", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
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
    ElMessage.warning("请选择模型版本和评估数据集");
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
    await ElMessageBox.confirm("确定开始评估？", "提示", { type: "info" });
    await TrainAPI.startEval(id);
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

async function handleStopEval(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该评估？", "提示", { type: "warning" });
    await TrainAPI.stopEval(id);
    refreshList();
  } catch {
    //
  }
}

async function handleDeleteEval(ids: number[]) {
  await TrainAPI.deleteEval(ids);
  refreshList();
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    if (!contentRef.value?.pageData) return;
    try {
      const params = { page_no: 1, page_size: 200 };
      const res = await TrainAPI.getEvalList(params);
      const fresh = (res.data?.data?.items || res.data?.data || []) as any[];
      const old = contentRef.value.pageData as any[];
      for (const f of fresh) {
        const o = old.find((x: any) => x.id === f.id);
        if (o) {
          o.progress = f.progress;
          o.status = f.status;
          o.metrics = f.metrics;
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
