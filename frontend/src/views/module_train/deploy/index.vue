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
          :perm-create="['module_train:model:update']"
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
              <el-empty :image-size="80" :description="t('train.deployNoData')" />
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
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('train.deployName')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'model_name')?.show"
              key="model_name"
              :label="t('train.model')"
              prop="model_name"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'model_version')?.show"
              key="model_version"
              :label="t('train.version')"
              prop="model_version"
              width="80"
            />
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
              v-if="contentCols.find((col) => col.prop === 'api_url')?.show"
              key="api_url"
              label="API URL"
              prop="api_url"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="scope">
                <span v-if="scope.row.api_url" class="api-url-cell">
                  {{ scope.row.api_url }}
                </span>
                <span v-else style="color: var(--el-text-color-secondary)">--</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'host_port')?.show"
              key="host_port"
              :label="t('train.port')"
              prop="host_port"
              width="80"
            />
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
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleDeploy(scope.row)"
                >
                  {{ t("train.deploy") }}
                </el-button>
                <el-button
                  v-if="scope.row.status === 'running'"
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  type="danger"
                  link
                  icon="VideoPause"
                  @click="handleStop(scope.row.id)"
                >
                  {{ t("train.stop") }}
                </el-button>
                <el-button
                  v-if="scope.row.status === 'running'"
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  link
                  icon="Key"
                  @click="handleRenewKey(scope.row.id)"
                >
                  {{ t("train.renewKey") }}
                </el-button>
                <el-button
                  v-if="scope.row.api_url"
                  size="small"
                  link
                  type="primary"
                  icon="Link"
                  @click="copyApiUrl(scope.row)"
                >
                  {{ t("train.copyUrl") }}
                </el-button>
                <el-button
                  size="small"
                  link
                  type="info"
                  icon="Document"
                  @click="deployLogRef.open(scope.row)"
                >
                  {{ t("train.detail") }}
                </el-button>
                <el-button
                  v-if="scope.row.status === 'failed' || scope.row.status === 'stopped'"
                  v-hasPerm="['module_train:model:update']"
                  size="small"
                  link
                  type="primary"
                  icon="VideoPlay"
                  @click="handleDeploy(scope.row)"
                >
                  {{ t("train.redeploy") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_train:model:delete']"
                  size="small"
                  type="danger"
                  link
                  icon="Delete"
                  @click="handleDelete([scope.row.id])"
                >
                  {{ t("train.delete") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="showCreateDialog"
      :title="t('train.deployCreateTitle')"
      append-to-body
      width="560px"
    >
      <el-form label-width="120px">
        <el-form-item :label="t('train.selectModel')" required>
          <el-select
            v-model="createForm.modelId"
            filterable
            style="width: 100%"
            :placeholder="t('train.selectModelVersion')"
            @change="onDeployModelChange"
          >
            <el-option
              v-for="m in models"
              :key="m.id"
              :label="`${m.name} v${m.version}`"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="needsRecModel" :label="t('train.recModel')" required>
          <el-select
            v-model="createForm.recModelId"
            filterable
            style="width: 100%"
            :placeholder="t('train.selectRecModel')"
          >
            <el-option
              v-for="m in recModels"
              :key="m.id"
              :label="`${m.name} v${m.version}`"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('train.deployName')">
          <el-input v-model="createForm.name" :placeholder="t('train.deployNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('train.gpuDevice')">
          <el-select
            v-model="createForm.device"
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
        <el-form-item :label="t('train.port')">
          <el-input-number
            v-model="createForm.hostPort"
            :min="9001"
            :max="9999"
            :placeholder="t('train.portPlaceholder')"
          />
        </el-form-item>
        <el-divider>{{ t("train.inferenceParams") }}</el-divider>
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

    <el-dialog
      v-model="showKeyDialog"
      :title="t('train.deploySuccess')"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-alert
        type="success"
        :title="t('train.apiKeyGenerated')"
        :description="
          t('train.deployApiUrlDesc', { url: keyInfo.apiUrl || t('train.deployPending') })
        "
        show-icon
        style="margin-bottom: 16px"
      />
      <div style="margin-bottom: 8px; font-weight: 600">
        {{ t("train.apiKeyHint") }}
      </div>
      <el-input v-model="keyInfo.apiKey" readonly style="font-family: monospace">
        <template #append>
          <el-button @click="copyText(keyInfo.apiKey)">{{ t("train.copy") }}</el-button>
        </template>
      </el-input>
      <div class="key-warning">
        <el-icon><WarningFilled /></el-icon>
        {{ t("train.keyOnceWarning") }}
      </div>
      <template #footer>
        <el-button type="primary" @click="onKeyDialogClose">
          {{ t("train.savedGoManage") }}
        </el-button>
      </template>
    </el-dialog>

    <DeployLogDrawer ref="deployLogRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { WarningFilled, Link } from "@element-plus/icons-vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { cachedOptions } from "@/composables/useOptions";
import DeployLogDrawer from "@/components/Train/DeployLogDrawer.vue";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const router = useRouter();
const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const deployLogRef = ref();

const models = ref<any[]>([]);
const creating = ref(false);
const showCreateDialog = ref(false);
const showKeyDialog = ref(false);
const keyInfo = reactive({ apiKey: "", apiUrl: "" });

const deviceOptions = ["0", "1", "2", "3", "4", "5", "6", "7", "cpu"];
const createForm = reactive({
  modelId: null as number | null,
  recModelId: null as number | null,
  name: "",
  device: "0",
  hostPort: null as number | null,
  hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640 },
});

const selectedDeployFramework = ref("");
function onDeployModelChange(modelId: number | null) {
  const m = models.value.find((x: any) => x.id === modelId);
  selectedDeployFramework.value = m?.framework || "";
  createForm.recModelId = null;
}
// OCR（paddlex）需要 det+rec 双模型
const needsRecModel = computed(() => ["paddlex"].includes(selectedDeployFramework.value));
const recModels = computed(() => models.value.filter((m: any) => m.framework === "paddlex"));

function statusTag(s: string) {
  return (
    (
      {
        pending: "info",
        deploying: "warning",
        running: "success",
        stopped: "info",
        failed: "danger",
      } as any
    )[s] || "info"
  );
}
function statusLabel(s: string) {
  return (
    (
      {
        pending: t("train.deployStatusPending"),
        deploying: t("train.deployStatusDeploying"),
        running: t("train.deployStatusRunning"),
        stopped: t("train.deployStatusStopped"),
        failed: t("train.deployStatusFailed"),
      } as any
    )[s] || s
  );
}

const searchConfig = reactive<ISearchConfig>({
  colon: true,
  isExpandable: false,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("train.deployName"),
      type: "input",
      attrs: { placeholder: t("train.deployNameSearchPlaceholder"), clearable: true },
    },
    {
      prop: "status",
      label: t("train.status"),
      type: "select",
      options: [
        { label: t("train.deployStatusPending"), value: "pending" },
        { label: t("train.deployStatusDeploying"), value: "deploying" },
        { label: t("train.deployStatusRunning"), value: "running" },
        { label: t("train.deployStatusStopped"), value: "stopped" },
        { label: t("train.deployStatusFailed"), value: "failed" },
      ],
      attrs: {
        placeholder: t("train.statusPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("train.selection"), show: true },
  { prop: "index", label: t("train.serial"), show: true },
  { prop: "name", label: t("train.deployName"), show: true },
  { prop: "model_name", label: t("train.model"), show: true },
  { prop: "model_version", label: t("train.version"), show: true },
  { prop: "framework", label: t("train.framework"), show: true },
  { prop: "api_url", label: "API URL", show: true },
  { prop: "host_port", label: t("train.port"), show: true },
  { prop: "status", label: t("train.status"), show: true },
  { prop: "created_time", label: t("train.createdTime"), show: true },
  { prop: "operation", label: t("train.action"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const r = await TrainAPI.getDeployList(params);
    const items = r.data?.data?.items || [];
    return { total: r.data?.data?.total ?? items.length, list: items };
  },
});

// 模型下拉仅在打开新建部署弹窗时懒加载（带缓存）
let modelsLoaded = false;
async function loadModels() {
  if (modelsLoaded) return;
  modelsLoaded = true;
  try {
    models.value = await cachedOptions(
      "train:models",
      async () =>
        (await TrainAPI.getModelList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    modelsLoaded = false;
  }
}
watch(showCreateDialog, (v) => {
  if (v) loadModels();
});

async function handleCreate() {
  if (!createForm.modelId) {
    ElMessage.warning(t("train.warnSelectModel"));
    return;
  }
  if (needsRecModel.value && !createForm.recModelId) {
    ElMessage.warning(t("train.warnOcrRec"));
    return;
  }
  creating.value = true;
  try {
    const hp: Record<string, any> = { ...createForm.hyperparams };
    if (needsRecModel.value && createForm.recModelId) {
      const rec = models.value.find((m: any) => m.id === createForm.recModelId);
      if (rec?.storage_path) hp.rec_model_path = rec.storage_path;
    }
    const r = await TrainAPI.createDeploy({
      model_id: createForm.modelId,
      name: createForm.name || undefined,
      device: createForm.device || "0",
      host_port: createForm.hostPort || undefined,
      hyperparams: hp,
    });
    ElMessage.success(t("train.saveSuccess"));
    const d = r.data?.data;
    keyInfo.apiKey = d?.api_key || "";
    keyInfo.apiUrl = d?.api_url || "";
    showCreateDialog.value = false;
    showKeyDialog.value = true;
    // 自动启动部署（否则需手动点"部署"）
    if (d?.id) {
      TrainAPI.startDeploy(d.id)
        .then(() => {
          keyInfo.apiUrl = keyInfo.apiUrl || `http://127.0.0.1:${d.host_port || ""}`;
        })
        .catch(() => {})
        .finally(() => refreshList());
    }
    createForm.modelId = null;
    createForm.recModelId = null;
    createForm.name = "";
    createForm.device = "0";
    createForm.hostPort = null;
    createForm.hyperparams = { conf: 0.25, iou: 0.45, imgsz: 640 };
    refreshList();
  } catch {
    /* */
  } finally {
    creating.value = false;
  }
}

function onKeyDialogClose() {
  showKeyDialog.value = false;
  router.push("/train/deploy");
}

async function handleDeploy(row: any) {
  try {
    await TrainAPI.startDeploy(row.id);
    ElMessage.success(t("train.started"));
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  }
}

async function handleStop(id: number) {
  try {
    await ElMessageBox.confirm(t("train.stopConfirmMsg"), t("train.tipTitle"), {
      type: "warning",
      confirmButtonText: t("train.stop"),
      cancelButtonText: t("train.cancel"),
    });
    await TrainAPI.stopDeploy(id);
    ElMessage.success(t("train.stopped"));
    refreshList();
  } catch {
    /* */
  }
}

async function handleRenewKey(id: number) {
  try {
    const r = await TrainAPI.renewDeployKey(id);
    const newKey = r.data?.data?.api_key;
    if (newKey) {
      keyInfo.apiKey = newKey;
      showKeyDialog.value = true;
    }
    refreshList();
  } catch {
    /* */
  }
}

function copyApiUrl(row: any) {
  if (row.api_url) copyText(row.api_url);
}

function copyText(text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => ElMessage.success(t("train.copied")))
    .catch(() => ElMessage.warning(t("train.copyFailed")));
}

async function handleDelete(ids: number[]) {
  try {
    await ElMessageBox.confirm(t("train.deleteConfirmMsg"), t("train.tipTitle"), {
      type: "warning",
      confirmButtonText: t("train.delete"),
      cancelButtonText: t("train.cancel"),
    });
    await TrainAPI.deleteDeploy(ids);
    ElMessage.success(t("train.deleteSuccess"));
    refreshList();
  } catch {
    /* */
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function startPoll() {
  stopPoll();
  pollTimer = setInterval(async () => {
    if (!contentRef.value?.pageData) return;
    try {
      // 只拉当前页刷新状态（静默避免弹错），并整体替换 pageData 触发行重渲染
      const pg = (contentRef.value as any)?.pagination;
      const params = {
        page_no: pg?.currentPage ?? 1,
        page_size: pg?.pageSize ?? 10,
        ...(((contentRef.value as any)?.getFilterParams?.() as Record<string, any>) || {}),
      };
      const res = await TrainAPI.getDeployList(params, { silent: true });
      const fresh = (res.data?.data?.items || res.data?.data || []) as any[];
      const old = contentRef.value.pageData as any[];
      const merged = old.map((x: any) => {
        const f = fresh.find((y: any) => y.id === x.id);
        return f ? { ...x, status: f.status, api_url: f.api_url } : x;
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

<style scoped>
/* API 地址单元格：等宽小字（替代内联 style） */
.api-url-cell {
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
}

/* 密钥提示（替代内联 style，颜色改用主题变量） */
.key-warning {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
