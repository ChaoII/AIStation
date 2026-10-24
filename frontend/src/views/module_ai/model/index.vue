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
          :perm-create="['module_ai:model:create']"
          :perm-delete="['module_ai:model:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <span class="batch-ac">
            <el-badge :value="modelSelIds.length" :hidden="!modelSelIds.length" class="batch-badge">
              <el-button size="small" :disabled="!modelSelIds.length" @click="batchEnable(true)">
                {{ t("ai_model.modelBatchEnable") }}
              </el-button>
            </el-badge>
            <el-badge :value="modelSelIds.length" :hidden="!modelSelIds.length" class="batch-badge">
              <el-button size="small" :disabled="!modelSelIds.length" @click="batchEnable(false)">
                {{ t("ai_model.modelBatchDisable") }}
              </el-button>
            </el-badge>
          </span>
          <el-tag size="small" type="info" effect="plain" class="summary-tag">
            {{
              t("ai_model.modelSummary", {
                total: modelSummary.total,
                enabled: modelSummary.enabled,
                disabled: modelSummary.disabled,
              })
            }}
          </el-tag>
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>
      <template #table="{ data, loading, tableRef }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onModelSel"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_model.modelEmpty')" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column
              :label="t('ai_model.modelConfigName')"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('ai_model.modelModel')"
              prop="model"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_model.modelUsage')" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ usageLabel(row.usage) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_model.modelContextWindow')" width="120" align="center">
              <template #default="{ row }">
                <span v-if="row.context_window">{{ row.context_window }}</span>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_model.modelBaseUrl')"
              prop="base_url"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column label="Key" prop="api_key_masked" width="140" />
            <el-table-column
              :label="t('ai_model.modelTemperature')"
              prop="temperature"
              width="80"
              align="center"
            />
            <el-table-column :label="t('ai_model.modelDefault')" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" type="success" size="small">
                  {{ t("ai_model.modelDefault") }}
                </el-tag>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_model.modelEnabled')" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? t("ai_model.modelEnabled") : t("ai_model.modelDisabled") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_model.modelAction')"
              fixed="right"
              min-width="200"
              align="center"
            >
              <template #default="scope">
                <el-button
                  icon="View"
                  size="small"
                  link
                  type="primary"
                  @click="openDetail(scope.row)"
                >
                  {{ t("ai_model.modelDetail") }}
                </el-button>
                <el-button
                  icon="Connection"
                  size="small"
                  link
                  type="primary"
                  @click="handleTest(scope.row)"
                >
                  {{ t("ai_model.modelTest") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:model:update']"
                  icon="edit"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("ai_model.modelEdit") }}
                </el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => onMoreCmd(scope.row, cmd)">
                  <el-button size="small" link type="primary" icon="MoreFilled" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        command="default"
                        icon="Star"
                        :disabled="scope.row.is_default"
                      >
                        {{ t("ai_model.modelSetDefault") }}
                      </el-dropdown-item>
                      <el-dropdown-item
                        v-if="perm('module_ai:model:delete')"
                        command="delete"
                        icon="delete"
                        divided
                        style="color: var(--el-color-danger)"
                      >
                        {{ t("ai_model.modelDelete") }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
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
      width="640px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px">
        <el-form-item
          :label="t('ai_model.modelConfigName')"
          prop="name"
          :rules="[
            { required: true, message: t('ai_model.modelConfigNameRequired'), trigger: 'blur' },
          ]"
        >
          <el-input
            v-model="formData.name"
            :placeholder="t('ai_model.modelConfigNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_model.modelUsage')">
          <el-select v-model="formData.usage" style="width: 100%">
            <el-option :label="t('ai_model.modelUsageChat')" value="chat" />
            <el-option :label="t('ai_model.modelUsageAssistant')" value="assistant" />
            <el-option :label="t('ai_model.modelUsageQuery')" value="query" />
            <el-option :label="t('ai_model.modelUsageEmbedding')" value="embedding" />
            <el-option :label="t('ai_model.modelUsageRerank')" value="rerank" />
            <el-option :label="t('ai_model.modelUsageTts')" value="tts" />
            <el-option :label="t('ai_model.modelUsageAsr')" value="asr" />
          </el-select>
          <!-- 后端 NL2SQL 运行时优先选 usage=='query' 的模型；没有它就永远落到 chat/通用模型 -->
          <el-text type="info" size="small">{{ t("ai_model.modelUsageFallback") }}</el-text>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('ai_model.modelContextWindow')">
              <el-input-number
                v-model="formData.context_window"
                :min="0"
                :step="1024"
                :controls="false"
                style="width: 100%"
                :placeholder="t('ai_model.modelContextWindowPlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('ai_model.modelCapabilities')">
              <el-input v-model="formData.capabilities_text" placeholder="chat,tool,vision" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('ai_model.modelProvider')">
          <el-select
            v-model="formData.provider_id"
            clearable
            :placeholder="t('ai_model.modelProviderPlaceholder')"
            style="width: 100%"
            @change="onProviderChange"
          >
            <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_model.modelModelName')" prop="model" required>
          <el-input
            v-model="formData.model"
            :placeholder="t('ai_model.modelModelNamePlaceholder')"
          />
          <el-button
            text
            type="primary"
            :icon="Refresh"
            style="margin-left: 8px"
            :disabled="!formData.provider_id"
            :loading="pulling"
            @click="pullRemoteModels"
          >
            {{ t("ai_model.modelImportFromProvider") }}
          </el-button>
        </el-form-item>
        <el-form-item v-if="remoteModels.length" :label="t('ai_model.modelSelectModel')">
          <el-select
            v-model="formData.model"
            filterable
            :placeholder="t('ai_model.modelSelectModelPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="m in remoteModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_model.modelBaseUrl')" prop="base_url" required>
          <el-input
            v-model="formData.base_url"
            :placeholder="t('ai_model.modelBaseUrlPlaceholder')"
          />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="formData.api_key"
            type="password"
            show-password
            :placeholder="
              dialogVisible.type === 'update' ? t('ai_model.modelApiKeyPlaceholderEdit') : 'sk-...'
            "
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('ai_model.modelTemperature')">
              <el-input-number v-model="formData.temperature" :min="0" :max="2" :step="0.1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('ai_model.modelMaxTokens')">
              <el-input-number v-model="formData.max_tokens" :min="64" :max="32768" :step="128" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('ai_model.modelEnabled')">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
        <el-form-item :label="t('ai_model.modelSetDefault')">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item :label="t('ai_model.modelDescription')">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('ai_model.modelCustomHeaders')">
          <div class="header-builder">
            <div v-for="(h, i) in formData.headerFields" :key="i" class="header-row">
              <el-input v-model="h.key" :placeholder="t('ai_model.modelHeaderNamePlaceholder')" />
              <el-input v-model="h.value" :placeholder="t('ai_model.modelValuePlaceholder')" />
              <el-button
                text
                type="danger"
                :icon="Delete"
                @click="formData.headerFields.splice(i, 1)"
              />
            </div>
            <el-button
              text
              type="primary"
              :icon="Plus"
              @click="formData.headerFields.push({ key: '', value: '' })"
            >
              {{ t("ai_model.modelAddHeader") }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :loading="testing" @click="handleTestForm">
          {{ t("ai_model.modelTestConnection") }}
        </el-button>
        <el-button @click="handleCloseDialog">{{ t("ai_model.modelCancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ t("ai_model.modelSave") }}
        </el-button>
      </template>
    </EnhancedDialog>

    <!-- 模型配置详情抽屉 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || t('ai_model.modelModelConfigTitle')"
      size="480px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item :label="t('ai_model.modelConfigName')">
          {{ detail.name }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelModel')">
          {{ detail.model }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelUsage')">
          <el-tag size="small" effect="plain">{{ usageLabel(detail.usage) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelCapabilities')">
          <span v-if="(detail.capabilities || []).length">
            <el-tag
              v-for="c in detail.capabilities"
              :key="c"
              size="small"
              type="info"
              class="cap-tag"
            >
              {{ c }}
            </el-tag>
          </span>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelContextWindow')">
          {{ detail.context_window || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelBaseUrl')">
          {{ detail.base_url }}
        </el-descriptions-item>
        <el-descriptions-item label="API Key">
          {{ detail.api_key_masked || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelTemperature')">
          {{ detail.temperature }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelMaxTokens')">
          {{ detail.max_tokens }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelSetDefault')">
          <el-tag v-if="detail.is_default" type="success" size="small">
            {{ t("ai_model.modelDefault") }}
          </el-tag>
          <span v-else class="muted">{{ t("ai_model.modelNo") }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelEnabled')">
          <el-tag :type="detail.enabled ? 'success' : 'info'" size="small">
            {{ detail.enabled ? t("ai_model.modelEnabled") : t("ai_model.modelDisabled") }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelDescription')">
          {{ detail.description || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_model.modelCreatedTime')">
          {{ detail.created_time }}
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, Delete, Plus } from "@element-plus/icons-vue";
import {
  getAiModelList,
  createAiModel,
  updateAiModel,
  deleteAiModel,
  setDefaultAiModel,
  batchModelStatus,
  testAiModel,
} from "@/api/module_ai/model";
import { getAiProviderList, getAiProviderRemoteModels } from "@/api/module_ai/provider";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { usePerm } from "@/composables/usePerm";
import { useI18n } from "vue-i18n";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const { t } = useI18n();
const perm = usePerm();
const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:model",
  colon: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("ai_model.modelConfigName"),
      type: "input",
      attrs: {
        placeholder: t("ai_model.modelConfigName"),
        clearable: true,
        style: { width: "200px" },
      },
    },
    {
      prop: "model",
      label: t("ai_model.modelModelName"),
      type: "input",
      attrs: {
        placeholder: t("ai_model.modelModelName"),
        clearable: true,
        style: { width: "200px" },
      },
    },
  ],
});

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_ai:model",
  pk: "id",
  cols: [] as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAiModelList(params as TablePageQuery);
    const list = res.data?.data || [];
    const name = (params as any)?.name;
    const model = (params as any)?.model;
    if (!name && !model) return { total: list.length, list };
    const filtered = list.filter(
      (x: any) =>
        (!name || (x.name || "").includes(name)) && (!model || (x.model || "").includes(model))
    );
    return { total: filtered.length, list: filtered };
  },
  deleteAction: async (ids) => {
    await deleteAiModel(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const emptyForm = () => ({
  id: undefined as number | undefined,
  name: "",
  model: "",
  usage: "chat",
  provider_id: undefined as number | undefined,
  capabilities_text: "",
  context_window: undefined as number | undefined,
  base_url: "",
  api_key: "",
  temperature: 0.3,
  max_tokens: 2048,
  enabled: true,
  is_default: false,
  extra_headers_text: "",
  headerFields: [] as { key: string; value: string }[],
  description: undefined as string | undefined,
});
const formData = reactive<any>(emptyForm());
const providers = ref<any[]>([]);
const remoteModels = ref<string[]>([]);
const pulling = ref(false);

const detailVisible = ref(false);
const detail = ref<any>(null);
function openDetail(row: any) {
  detail.value = row;
  detailVisible.value = true;
}
function usageLabel(u: string) {
  const map: Record<string, string> = {
    chat: t("ai_model.modelUsageChat"),
    assistant: t("ai_model.modelUsageAssistant"),
    query: t("ai_model.modelUsageLabelQuery"),
    embedding: t("ai_model.modelUsageLabelEmbedding"),
    rerank: t("ai_model.modelUsageLabelRerank"),
    asr: t("ai_model.modelUsageLabelAsr"),
    tts: t("ai_model.modelUsageLabelTts"),
  };
  return map[u] || u;
}

async function loadProviders() {
  try {
    const res = await getAiProviderList();
    providers.value = (res.data?.data || []) as any[];
  } catch {
    providers.value = [];
  }
}

function onProviderChange(id: number | undefined) {
  remoteModels.value = [];
  if (!id) return;
  const p = providers.value.find((x) => x.id === id);
  // 已有基址则不覆盖，仅首次带出
  if (p && !formData.base_url) formData.base_url = p.base_url || "";
}

async function pullRemoteModels() {
  if (!formData.provider_id) {
    ElMessage.warning(t("ai_model.modelProviderRequired"));
    return;
  }
  pulling.value = true;
  try {
    const res = await getAiProviderRemoteModels(formData.provider_id);
    remoteModels.value = (res.data?.data || []) as string[];
    if (remoteModels.value.length) {
      ElMessage.success(t("ai_model.modelImportedRemote", { count: remoteModels.value.length }));
    } else {
      ElMessage.warning(t("ai_model.modelNoRemoteModels"));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelPullFailed"));
  } finally {
    pulling.value = false;
  }
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  Object.assign(formData, emptyForm());
  if (id && type === "update") {
    dialogVisible.title = t("ai_model.modelEditTitle");
    const res = await getAiModelList();
    const item = (res.data?.data || []).find((x: any) => x.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id,
        name: item.name,
        model: item.model,
        usage: item.usage || "chat",
        provider_id: item.provider_id || undefined,
        capabilities_text: (item.capabilities || []).join(","),
        context_window: item.context_window,
        base_url: item.base_url,
        api_key: "",
        temperature: item.temperature,
        max_tokens: item.max_tokens,
        enabled: item.enabled,
        is_default: item.is_default,
        headerFields: Object.entries(item.extra_headers || {}).map(([k, v]) => ({
          key: k,
          value: String(v),
        })),
        description: item.description,
      });
    }
  } else {
    dialogVisible.title = t("ai_model.modelCreateTitle");
  }
  remoteModels.value = [];
  dialogVisible.visible = true;
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  Object.assign(formData, emptyForm());
}

async function handleSubmit() {
  if (!formData.name || !formData.model || !formData.base_url) {
    ElMessage.warning(t("ai_model.modelRequiredFields"));
    return;
  }
  submitLoading.value = true;
  try {
    const extraHeaders = buildObjectFromRows(formData.headerFields);
    const payload: any = {
      name: formData.name,
      provider: "openai_compatible",
      provider_id: formData.provider_id || undefined,
      usage: formData.usage,
      capabilities: formData.capabilities_text
        ? formData.capabilities_text
            .split(",")
            .map((s: string) => s.trim())
            .filter(Boolean)
        : null,
      context_window: formData.context_window,
      model: formData.model,
      base_url: formData.base_url,
      temperature: formData.temperature,
      max_tokens: formData.max_tokens,
      enabled: formData.enabled,
      is_default: formData.is_default,
      extra_headers: extraHeaders,
      description: formData.description,
    };
    if (formData.api_key) payload.api_key = formData.api_key;
    if (formData.id) await updateAiModel(formData.id, payload);
    else await createAiModel(payload);
    dialogVisible.visible = false;
    refreshList();
    ElMessage.success(t("ai_model.modelSaveSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelSaveFailed"));
  } finally {
    submitLoading.value = false;
  }
}

async function handleSetDefault(id: number) {
  try {
    await setDefaultAiModel(id);
    ElMessage.success(t("ai_model.modelSetDefaultSuccess"));
    refreshList();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelSetDefaultFailed"));
  }
}

function onMoreCmd(row: any, cmd: string) {
  if (cmd === "default") {
    handleSetDefault(row.id);
  } else if (cmd === "delete") {
    handleRowDelete(row.id);
  }
}

async function handleTest(row: any) {
  try {
    const res = await testAiModel({ id: row.id });
    ElMessage.success(
      t("ai_model.modelConnectionSuccess", { reply: res.data?.data?.reply || "ok" })
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelConnectionFailed"));
  }
}

const testing = ref(false);
const modelSelIds = ref<number[]>([]);
function onModelSel(sel: any[]) {
  modelSelIds.value = sel.map((s: any) => s.id);
}
async function batchEnable(enabled: boolean) {
  if (!modelSelIds.value.length) return;
  try {
    const r = await batchModelStatus(modelSelIds.value, enabled);
    ElMessage.success(
      t("ai_model.modelBatchResult", {
        action: enabled ? t("ai_model.modelEnabledAction") : t("ai_model.modelDisabledAction"),
        count: r.data?.data?.count || 0,
      })
    );
    refreshList();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelOperationFailed"));
  }
}

function buildObjectFromRows(
  rows: { key: string; value: string }[]
): Record<string, string> | undefined {
  const out: Record<string, string> = {};
  for (const r of rows || []) {
    const k = (r.key || "").trim();
    if (!k) continue;
    out[k] = r.value;
  }
  return Object.keys(out).length ? out : undefined;
}

// 弹窗内测试：有 Key 用当前表单值；编辑态未改 Key 则用已保存配置
async function handleTestForm() {
  const payload: any = {
    base_url: formData.base_url,
    model: formData.model,
    usage: formData.usage,
    extra_headers: buildObjectFromRows(formData.headerFields),
  };
  if (formData.api_key) payload.api_key = formData.api_key;
  else if (formData.id) payload.id = formData.id;
  else {
    ElMessage.warning(t("ai_model.modelApiKeyRequired"));
    return;
  }
  testing.value = true;
  try {
    const res = await testAiModel(payload);
    ElMessage.success(
      t("ai_model.modelConnectionSuccess", { reply: res.data?.data?.reply || "ok" })
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_model.modelConnectionFailed"));
  } finally {
    testing.value = false;
  }
}

onMounted(() => {
  loadProviders();
  loadModelSummary();
});

const modelSummary = ref({ total: 0, enabled: 0, disabled: 0 });
async function loadModelSummary() {
  try {
    const r = await getAiModelList({ page_no: 1, page_size: 999 });
    const list = r.data?.data || [];
    modelSummary.value = {
      total: list.length,
      enabled: list.filter((m: any) => m.enabled).length,
      disabled: list.filter((m: any) => !m.enabled).length,
    };
  } catch {
    /* 忽略 */
  }
}
</script>

<style scoped>
.muted {
  color: var(--el-text-color-placeholder);
}
.cap-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}
.header-builder {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.header-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.batch-ac {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.summary-tag {
  flex-shrink: 0;
}
</style>
