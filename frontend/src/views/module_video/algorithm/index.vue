<template>
  <div class="app-container">
    <PageSearch
      ref="algoSearchRef"
      :search-config="algoSearchConfig"
      @query-click="handleAlgoQuery"
      @reset-click="handleAlgoReset"
    />

    <PageContent ref="algoContentRef" :content-config="algoContentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_video:algorithm:create']"
          :perm-delete="['module_video:algorithm:delete']"
          :perm-patch="['module_video:algorithm:patch']"
          @add="handleOpenAlgoDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
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
              <el-empty :image-size="80" :description="t('video.common.noData')" />
            </template>
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'index')?.show"
              type="index"
              fixed
              :label="t('video.common.sequence')"
              min-width="60"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('video.algo.algorithmName')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'code')?.show"
              key="code"
              :label="t('video.algo.code')"
              prop="code"
              width="140"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'version')?.show"
              key="version"
              :label="t('video.algo.version')"
              prop="version"
              width="90"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'algorithm_type')?.show"
              key="algorithm_type"
              :label="t('video.algo.algorithmType')"
              prop="algorithm_type"
              width="120"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('video.common.status')"
              prop="status"
              width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status ? 'success' : 'info'" size="small">
                  {{ scope.row.status ? t("video.common.enabled") : t("video.common.disabled") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('video.common.operation')"
              align="center"
              min-width="300"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:algorithm:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenAlgoDialog('update', scope.row.id)"
                >
                  {{ t("video.common.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:algorithm:update']"
                  type="success"
                  size="small"
                  link
                  :icon="RefreshRight"
                  @click="handleHotUpdate(scope.row)"
                >
                  {{ t("video.algo.hotUpdate") }}
                </el-button>
                <span v-hasPerm="['module_video:algorithm:update']" class="rollback-trigger">
                  <el-tooltip
                    :disabled="canRollback(scope.row)"
                    :content="t('video.algo.noRollback')"
                    placement="top"
                  >
                    <span>
                      <el-button
                        type="warning"
                        size="small"
                        link
                        :icon="RefreshLeft"
                        :disabled="!canRollback(scope.row)"
                        @click="handleRollback(scope.row)"
                      >
                        {{ t("video.algo.rollback") }}
                      </el-button>
                    </span>
                  </el-tooltip>
                </span>
                <el-button
                  v-hasPerm="['module_video:algorithm:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleAlgoDelete(scope.row.id)"
                >
                  {{ t("video.common.delete") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="algoDialogVisible.visible"
      :title="algoDialogVisible.title"
      append-to-body
      width="760px"
      @close="handleCloseAlgoDialog"
    >
      <el-form ref="algoFormRef" :model="algoForm" label-width="110px" size="default">
        <div class="form-section">
          <div class="form-section-title">{{ t("video.algo.basicInfo") }}</div>
          <el-form-item :label="t('video.algo.algorithmName')" prop="name">
            <el-input v-model="algoForm.name" :placeholder="t('video.algo.enterName')" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('video.algo.code')" prop="code">
                <el-input v-model="algoForm.code" :placeholder="t('video.algo.uniqueCode')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('video.algo.algorithmType')" prop="algorithm_type">
                <el-select
                  v-model="algoForm.algorithm_type"
                  style="width: 100%"
                  @change="onAlgoTypeChange"
                >
                  <el-option
                    v-for="(label, val) in algoTypeOpts"
                    :key="val"
                    :label="label"
                    :value="val"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="t('video.algo.version')" prop="version">
            <el-input v-model="algoForm.version" placeholder="1.0.0" style="width: 200px" />
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">{{ t("video.algo.modelFiles") }}</div>
          <el-form-item :label="t('video.algo.modelFile')" prop="model_path">
            <div class="file-upload-row">
              <el-input
                v-model="algoForm.model_path"
                :placeholder="t('video.algo.modelPathOrUpload')"
                class="file-path-input"
              />
              <el-upload
                accept=".onnx,.engine,.pt,.pth,.trt,.rknn,.om"
                :auto-upload="false"
                :show-file-list="false"
                @change="handleModelUpload"
              >
                <el-button size="default">
                  <el-icon><Upload /></el-icon>
                  {{ t("video.algo.upload") }}
                </el-button>
              </el-upload>
            </div>
          </el-form-item>
          <el-form-item :label="t('video.algo.pluginPath')" prop="plugin_path">
            <el-input
              v-model="algoForm.plugin_path"
              :placeholder="t('video.algo.pluginPathHint')"
            />
          </el-form-item>
          <el-form-item :label="t('video.algo.configFile')">
            <div class="config-toolbar">
              <el-upload
                accept=".json,.yaml,.yml"
                :auto-upload="false"
                :show-file-list="false"
                @change="handleConfigUpload"
              >
                <el-button size="small" type="primary">
                  <el-icon><Upload /></el-icon>
                  {{ t("video.algo.uploadConfig") }}
                </el-button>
              </el-upload>
              <el-button size="small" @click="loadConfigTemplate">
                <el-icon><Document /></el-icon>
                {{ t("video.algo.loadTemplate") }}
              </el-button>
              <el-button size="small" @click="formatConfigJson">
                <el-icon><Checked /></el-icon>
                {{ t("video.algo.format") }}
              </el-button>
            </div>
          </el-form-item>
          <el-form-item :label="t('video.algo.configContent')">
            <div class="form-section-title">{{ t("video.algo.runtimeEnv") }}</div>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item :label="t('video.algo.inferenceEngine')">
                  <el-select v-model="algoForm.runtimeEngine" style="width: 100%">
                    <el-option label="PyTorch" value="pytorch" />
                    <el-option label="TensorRT" value="tensorrt" />
                    <el-option label="ONNX Runtime" value="onnx" />
                    <el-option label="OpenVINO" value="openvino" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('video.algo.runtimeDevice')">
                  <el-select v-model="algoForm.runtimeDevice" style="width: 100%">
                    <el-option label="CPU" value="cpu" />
                    <el-option label="GPU 0" value="0" />
                    <el-option label="GPU 1" value="1" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <div class="form-section-title">{{ t("video.algo.paramConfig") }}</div>
            <el-form-item v-for="(meta, key) in paramsMeta" :key="key" :label="meta.label || key">
              <template v-if="meta.type === 'bool'">
                <el-switch v-model="algoForm.params[key]" />
              </template>
              <template v-else-if="meta.type === 'select'">
                <el-select v-model="algoForm.params[key]" style="width: 100%">
                  <el-option
                    v-for="o in meta.options || []"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </el-select>
              </template>
              <template v-else-if="meta.type === 'multi-select'">
                <el-select v-model="algoForm.params[key]" multiple style="width: 100%">
                  <el-option
                    v-for="o in meta.options || []"
                    :key="o.value"
                    :label="o.label"
                    :value="o.value"
                  />
                </el-select>
              </template>
              <template v-else-if="meta.type === 'float' || meta.type === 'int'">
                <el-input-number
                  v-model="algoForm.params[key]"
                  :min="meta.min"
                  :max="meta.max"
                  :step="meta.step"
                  controls-position="right"
                  style="width: 220px"
                />
                <span v-if="meta.unit" class="param-unit">{{ meta.unit }}</span>
              </template>
              <template v-else>
                <el-input v-model="algoForm.params[key]" style="width: 260px" />
              </template>
              <div v-if="meta.hint" class="param-hint">{{ meta.hint }}</div>
            </el-form-item>

            <div class="code-editor-wrap">
              <CodeEditor
                v-model="algoForm.configJson"
                language="json"
                :theme="codeTheme"
                height="360px"
                border
              />
            </div>
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">{{ t("video.algo.other") }}</div>
          <el-form-item :label="t('video.common.status')" prop="status">
            <el-switch v-model="algoForm.status" />
          </el-form-item>
          <el-form-item :label="t('video.common.description')" prop="description">
            <el-input
              v-model="algoForm.description"
              type="textarea"
              :rows="2"
              :placeholder="t('video.common.optionalRemark')"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseAlgoDialog">{{ t("video.common.cancel") }}</el-button>
        <el-button type="primary" :loading="algoSubmitLoading" @click="handleSubmitAlgo">
          {{ t("video.common.save") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeMount } from "vue";
import { Upload, Document, Checked, RefreshLeft, RefreshRight } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import request from "@/utils/request";
import {
  getAlgorithmList,
  createAlgorithm,
  updateAlgorithm,
  deleteAlgorithm,
  hotUpdateAlgorithm,
  rollbackAlgorithm,
  retryDispatchAlgorithm,
  type AlgorithmDispatchResult,
} from "@/api/module_video/algorithm";
import { configTemplates, algoTypeLabels, paramMetaTemplates } from "@/config/algoTemplates";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import CodeEditor from "@/components/CodeEditor/index.vue";
import { useSettingsStore } from "@/store";
import { ThemeMode } from "@/enums/settings/theme.enum";

const settingsStore = useSettingsStore();
const { t } = useI18n();

const algoSubmitLoading = ref(false);
const algoFormRef = ref();
const algoTypeOpts = algoTypeLabels;
const codeTheme = computed(() => (settingsStore.theme === ThemeMode.DARK ? "one-dark" : "default"));
const algoDialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});
const algoSearchRef = ref();
const algoContentRef = ref();
const refreshAlgoList = () => algoContentRef.value?.fetchPageData?.();

const algoSearchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:algorithm",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("video.algo.algorithmName"),
      type: "input",
      attrs: { placeholder: t("video.algo.enterName"), clearable: true },
    },
    {
      prop: "algorithm_type",
      label: t("video.algo.algorithmType"),
      type: "select",
      options: [
        { label: t("video.algo.invasion"), value: "INTRUSION" },
        { label: t("video.algo.lineCrossing"), value: "LINE_CROSSING" },
        { label: t("video.algo.faceDetect"), value: "FACE_DETECT" },
        { label: t("video.algo.crowdCount"), value: "CROWD_COUNT" },
        { label: t("video.algo.fireSmoke"), value: "FIRE_SMOKE" },
        { label: t("video.algo.vehicleDetect"), value: "VEHICLE_DETECT" },
        { label: t("video.algo.behaviorAnalysis"), value: "BEHAVIOR_ANALYSIS" },
        { label: t("video.algo.objectLeft"), value: "OBJECT_LEFT" },
      ],
      attrs: {
        placeholder: t("video.algo.selectAlgorithmType"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const algoCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "name", label: t("video.algo.algorithmName"), show: true },
  { prop: "code", label: t("video.algo.code"), show: true },
  { prop: "version", label: t("video.algo.version"), show: true },
  { prop: "algorithm_type", label: t("video.algo.algorithmType"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
]);

interface TablePageQuery extends Record<string, any> {
  page_no: number;
  page_size: number;
}

const algoContentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:algorithm",
  pk: "id",
  cols: algoCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAlgorithmList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteAlgorithm(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: t("video.common.warning"),
    message: t("video.common.deleteConfirmMsg"),
    type: "warning",
  },
});

function handleAlgoDelete(id: number) {
  algoContentRef.value?.handleDelete(id);
}
function handleAlgoQuery() {
  algoContentRef.value?.fetchPageData({ page_no: 1 });
}
function handleAlgoReset() {
  algoContentRef.value?.fetchPageData({ page_no: 1 });
}

/** 是否存在可回滚的历史版本（后端以 previous_model_path/previous_version 判断） */
function canRollback(row: any): boolean {
  return Boolean(row?.previous_version || row?.previous_model_path);
}

/** HTML 转义，避免后端错误信息里的特殊字符破坏提示结构 */
function escapeHtml(text: unknown): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return String(text ?? "").replace(/[&<>"']/g, (c) => map[c]);
}

/** 汇总展示下发结果：成功/失败任务数，失败时可一键重试失败任务 */
async function showDispatchResult(
  action: string,
  result: AlgorithmDispatchResult | undefined,
  row: any
) {
  const succeeded = result?.succeeded?.length ?? 0;
  const failed = result?.failed ?? [];
  if (failed.length === 0) {
    ElMessage.success(t("video.algo.dispatchDone", { action, succeeded }));
    return;
  }
  const items = failed
    .map(
      (f) =>
        `<li style="margin-bottom:4px"><span style="color:var(--el-color-danger)">${t("video.algo.taskPrefix", { id: f.task_id })}</span>：${escapeHtml(f.error)}</li>`
    )
    .join("");
  try {
    await ElMessageBox.confirm(
      `<div style="max-height:300px;overflow:auto">
        <p style="margin:0 0 6px">${t("video.algo.dispatchSummary", { succeeded, failed: failed.length })}</p>
        <ul style="padding-left:18px;margin:0">${items}</ul>
      </div>`,
      t("video.algo.result", { action }),
      {
        confirmButtonText: t("video.algo.retryFailed"),
        cancelButtonText: t("video.algo.close"),
        type: "warning",
        dangerouslyUseHTMLString: true,
      }
    );
  } catch {
    // 用户选择关闭：保留失败清单（后端已 ERROR 日志记录），不阻断操作
    return;
  }
  try {
    const retryRes = await retryDispatchAlgorithm(
      row.id,
      failed.map((f) => f.task_id)
    );
    refreshAlgoList();
    await showDispatchResult(
      `${action}${t("video.algo.retrySuffix")}`,
      retryRes.data.data as AlgorithmDispatchResult,
      row
    );
  } catch (e: any) {
    ElMessage.error(
      e?.response?.data?.msg || e?.message || e?.msg || t("video.algo.retryDispatchFail")
    );
  }
}

async function handleHotUpdate(row: any) {
  try {
    await ElMessageBox.confirm(
      t("video.algo.hotUpdateConfirm", { name: row.name }),
      t("video.algo.hotUpdateConfirmTitle"),
      {
        type: "warning",
        confirmButtonText: t("video.algo.confirmDispatch"),
        cancelButtonText: t("video.common.cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const res = await hotUpdateAlgorithm(row.id);
    await showDispatchResult(
      t("video.algo.hotUpdate"),
      res.data.data as AlgorithmDispatchResult,
      row
    );
    refreshAlgoList();
  } catch (e: any) {
    ElMessage.error(
      e?.response?.data?.msg || e?.message || e?.msg || t("video.algo.hotUpdateFail")
    );
  }
}

async function handleRollback(row: any) {
  if (!canRollback(row)) return;
  try {
    await ElMessageBox.confirm(
      t("video.algo.rollbackConfirm", {
        name: row.name,
        version: row.previous_version || t("video.algo.unknownVersion"),
      }),
      t("video.algo.rollbackConfirmTitle"),
      {
        type: "warning",
        confirmButtonText: t("video.algo.confirmRollback"),
        cancelButtonText: t("video.common.cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const res = await rollbackAlgorithm(row.id);
    await showDispatchResult(
      t("video.algo.rollback"),
      res.data.data as AlgorithmDispatchResult,
      row
    );
    refreshAlgoList();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || e?.msg || t("video.algo.rollbackFail"));
  }
}

const algoForm = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  code: undefined as string | undefined,
  version: "1.0.0",
  algorithm_type: "INTRUSION",
  model_path: undefined as string | undefined,
  plugin_path: undefined as string | undefined,
  configJson: JSON.stringify(configTemplates.INTRUSION, null, 2),
  runtimeEngine: "pytorch",
  runtimeDevice: "cpu",
  params: {} as Record<string, any>,
  status: true,
  description: undefined as string | undefined,
});

const initialAlgoForm = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  code: undefined as string | undefined,
  version: "1.0.0" as const,
  algorithm_type: "INTRUSION" as const,
  model_path: undefined as string | undefined,
  plugin_path: undefined as string | undefined,
  configJson: JSON.stringify(configTemplates.INTRUSION, null, 2),
  runtimeEngine: "pytorch" as const,
  runtimeDevice: "cpu" as const,
  params: {} as Record<string, any>,
  status: true,
  description: undefined as string | undefined,
};

const paramsMeta = computed(() => paramMetaTemplates[algoForm.algorithm_type] || {});
function syncParamsFromConfig() {
  try {
    const cfg = JSON.parse(algoForm.configJson);
    const tmpl = configTemplates[algoForm.algorithm_type]?.params || {};
    const meta = paramsMeta.value;
    const out: Record<string, any> = {};
    for (const key of Object.keys(meta)) {
      const src = cfg.params?.[key] !== undefined ? cfg.params[key] : meta[key]?.default;
      out[key] = src;
    }
    algoForm.params = out;
  } catch {
    algoForm.params = {};
  }
}
function settingsParamsIntoConfig() {
  try {
    const cfg = JSON.parse(algoForm.configJson);
    cfg.params = { ...(cfg.params || {}), ...algoForm.params };
    algoForm.configJson = JSON.stringify(cfg, null, 2);
  } catch {
    /* 忽略 */
  }
}

async function resetAlgoForm() {
  if (algoFormRef.value) {
    algoFormRef.value.resetFields();
    algoFormRef.value.clearValidate();
  }
  Object.assign(algoForm, initialAlgoForm);
}

function loadConfigTemplate() {
  const tmpl = configTemplates[algoForm.algorithm_type];
  if (tmpl) {
    algoForm.configJson = JSON.stringify(tmpl, null, 2);
  }
  syncParamsFromConfig();
}

function onAlgoTypeChange() {
  loadConfigTemplate();
}

async function handleModelUpload(uploadFile: any) {
  const file = uploadFile.raw;
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await request({
      url: "/video/algorithm/model/upload",
      method: "post",
      data: fd,
      headers: { "Content-Type": "multipart/form-data", _silent: "true" },
    });
    const mp = res?.data?.data?.model_path;
    if (mp) {
      algoForm.model_path = mp;
      ElMessage.success(t("video.algo.modelUploaded", { name: file.name }));
    } else {
      ElMessage.error(t("video.algo.uploadFail"));
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.msg || t("video.algo.uploadFail"));
  }
}

function formatConfigJson() {
  try {
    const parsed = JSON.parse(algoForm.configJson);
    algoForm.configJson = JSON.stringify(parsed, null, 2);
  } catch {
    /* noop */
  }
}

function handleConfigUpload(uploadFile: any) {
  const file = uploadFile.raw;
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const content = e.target?.result as string;
    if (!content) return;
    try {
      JSON.parse(content);
      algoForm.configJson = content;
    } catch {
      algoForm.configJson = content;
    }
  };
  reader.readAsText(file);
}

async function handleCloseAlgoDialog() {
  algoDialogVisible.visible = false;
  await resetAlgoForm();
}

async function handleOpenAlgoDialog(type: "create" | "update", id?: number) {
  algoDialogVisible.type = type;
  if (id && type === "update") {
    algoDialogVisible.title = t("video.algo.editAlgorithm");
    const res = await getAlgorithmList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      algoForm.id = item.id;
      algoForm.name = item.name;
      algoForm.code = item.code;
      algoForm.version = item.version;
      algoForm.algorithm_type = item.algorithm_type;
      algoForm.model_path = item.model_path;
      algoForm.plugin_path = item.plugin_path;
      algoForm.status = item.status;
      algoForm.description = item.description;
      // Reconstruct configJson from stored fields
      const config: any = { algorithm_type: item.algorithm_type, version: item.version };
      config.model = { format: item.model_file_config?.format || "onnx" };
      if (item.model_file_config?.encrypt) config.model.encrypt = item.model_file_config.encrypt;
      config.runtime = item.runtime_config || configTemplates[item.algorithm_type]?.runtime;
      config.params = item.preset_params || configTemplates[item.algorithm_type]?.params;
      config.output = item.output_schema || configTemplates[item.algorithm_type]?.output;
      algoForm.configJson = JSON.stringify(config, null, 2);
      algoForm.runtimeEngine = config.runtime?.engine || "pytorch";
      algoForm.runtimeDevice = config.runtime?.device || "cpu";
      syncParamsFromConfig();
    }
  } else {
    algoDialogVisible.title = t("video.algo.addAlgorithm");
    algoForm.id = undefined;
    loadConfigTemplate();
  }
  algoDialogVisible.visible = true;
}

async function handleSubmitAlgo() {
  algoSubmitLoading.value = true;
  const id = algoForm.id;
  try {
    let config: any = {};
    try {
      config = JSON.parse(algoForm.configJson);
    } catch {
      config = {};
    }
    // 运行环境可视化字段写入 runtime
    config.runtime = {
      ...(config.runtime || {}),
      engine: algoForm.runtimeEngine,
      device: algoForm.runtimeDevice,
    };
    // 参数动态表单写回 config.params
    config.params = { ...(config.params || {}), ...algoForm.params };
    const payload: any = {
      name: algoForm.name,
      code: algoForm.code,
      version: algoForm.version,
      algorithm_type: algoForm.algorithm_type,
      model_path: algoForm.model_path || null,
      plugin_path: algoForm.plugin_path || null,
      model_file_config: config.model || {},
      runtime_config: config.runtime || {},
      preset_params: config.params || {},
      output_schema: config.output || {},
      status: algoForm.status,
      description: algoForm.description || "",
    };
    if (id) {
      await updateAlgorithm(id, payload);
    } else {
      await createAlgorithm(payload);
    }
    ElMessage.success(t("video.common.saveSuccess"));
    algoDialogVisible.visible = false;
    await resetAlgoForm();
    refreshAlgoList();
  } catch {
    //
  } finally {
    algoSubmitLoading.value = false;
  }
}

onBeforeMount(async () => {
  refreshAlgoList();
});
</script>

<style scoped lang="scss">
.form-section {
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.form-section:last-child {
  padding-bottom: 0;
  margin-bottom: 0;
  border-bottom: none;
}
.form-section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.form-section-desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}
.config-value {
  min-width: 40px;
  font-size: var(--el-font-size-small);
  font-weight: 500;
  color: var(--el-color-primary);
  text-align: right;
}
.config-unit {
  margin-left: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.config-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.file-upload-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.file-path-input {
  flex: 1;
}

.code-editor-wrap {
  width: 100%;
  overflow: hidden;
  border-radius: 4px;
}

.rollback-trigger {
  display: inline-flex;
  align-items: center;
}
.param-unit {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.param-hint {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
