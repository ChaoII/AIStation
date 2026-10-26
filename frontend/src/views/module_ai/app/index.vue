<!-- AI 应用：上搜索/下列表 + 弹窗表单（模型+提示词+工具集+输出格式+入参），行内可运行 -->
<template>
  <div class="app-container ai-app-page">
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
          :perm-create="['module_ai:app:create']"
          :perm-delete="['module_ai:app:delete']"
          @add="handleOpenDialog()"
          @delete="onToolbar('delete')"
        />
        <el-button size="small" :disabled="!appSelIds.length" @click="batchApp(true)">
          {{ t("ai_workflow.app_batchEnable") }}
        </el-button>
        <el-button size="small" :disabled="!appSelIds.length" @click="batchApp(false)">
          {{ t("ai_workflow.app_batchDisable") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain" class="summary-tag">
          {{
            t("ai_workflow.app_summary", {
              total: appSummary.total,
              enabled: appSummary.enabled,
              disabled: appSummary.disabled,
            })
          }}
        </el-tag>
        <el-dropdown
          v-if="appTemplates.length"
          style="margin-left: 8px"
          @command="createFromTemplate"
        >
          <el-button size="small">
            {{ t("ai_workflow.app_createFromTemplate") }}
            <el-icon style="margin-left: 4px"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="t in appTemplates" :key="t.key" :command="t" icon="Document">
                {{ t.name }}（{{ t.app_type }}）
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <div class="data-table__toolbar--right">
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
            @selection-change="onAppSel"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.app_noData')" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column :label="t('ai_workflow.app_icon')" width="80" align="center">
              <template #default="{ row }">
                <el-icon v-if="row.icon"><component :is="row.icon" /></el-icon>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.app_name')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_workflow.app_type')" width="120" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="typeTagType(row.app_type)" effect="plain">
                  {{ typeLabel(row.app_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.app_model')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ modelName(row.model_id) }}</template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.app_prompt')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ promptName(row.prompt_id) }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.app_toolCount')" width="90" align="center">
              <template #default="{ row }">{{ (row.tools || []).length }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.app_outputFormat')" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ formatLabel(row.output_format) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.app_enabled')" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.enabled ? 'success' : 'info'">
                  {{
                    row.enabled
                      ? t("ai_workflow.app_enabledText")
                      : t("ai_workflow.app_disabledText")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.app_action')"
              fixed="right"
              width="260"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:app:query']"
                  icon="View"
                  size="small"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  {{ t("ai_workflow.app_detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:update']"
                  icon="edit"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog(row)"
                >
                  {{ t("ai_workflow.app_edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:create']"
                  icon="CopyDocument"
                  size="small"
                  link
                  @click="doCopy(row)"
                >
                  {{ t("ai_workflow.app_copy") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:delete']"
                  icon="delete"
                  size="small"
                  link
                  type="danger"
                  @click="handleRowDelete(row.id)"
                >
                  {{ t("ai_workflow.app_delete") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible"
      :title="dialogTitle"
      append-to-body
      width="660px"
      @close="handleCloseDialog"
    >
      <el-form ref="formRef" :model="formData" label-width="120px">
        <el-form-item :label="t('ai_workflow.app_name')" required>
          <el-input v-model="formData.name" :placeholder="t('ai_workflow.app_namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_componentType')">
          <el-select v-model="formData.app_type" style="width: 100%">
            <el-option :label="t('ai_workflow.app_typeChat')" value="chat" />
            <el-option :label="t('ai_workflow.app_typeAgent')" value="agent" />
            <el-option :label="t('ai_workflow.app_typeWorkflow')" value="workflow" />
            <el-option :label="t('ai_workflow.app_typeKb')" value="kb" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.app_type === 'kb'" :label="t('ai_workflow.app_kb')">
          <el-select
            v-model="formData.kb_id"
            clearable
            :placeholder="t('ai_workflow.app_bindKb')"
            style="width: 100%"
          >
            <el-option v-for="k in kbOptions" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="formData.app_type === 'workflow' || formData.workflow_id"
          :label="t('ai_workflow.app_workflow')"
        >
          <el-select
            v-model="formData.workflow_id"
            clearable
            :placeholder="t('ai_workflow.app_bindWorkflow')"
            style="width: 100%"
          >
            <el-option v-for="w in wfOptions" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_iconLabel')">
          <el-input v-model="formData.icon" :placeholder="t('ai_workflow.app_iconPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_description')">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_model')">
          <el-select
            v-model="formData.model_id"
            clearable
            :placeholder="t('ai_workflow.app_modelPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_prompt')">
          <el-select
            v-model="formData.prompt_id"
            clearable
            :placeholder="t('ai_workflow.app_promptPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="p in promptOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('ai_workflow.app_temperature')">
              <el-input-number
                v-model="formData.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                controls-position="right"
                style="width: 100%"
                :placeholder="t('ai_workflow.app_temperaturePlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('ai_workflow.app_maxTokens')">
              <el-input-number
                v-model="formData.max_tokens"
                :min="64"
                :max="32768"
                :step="128"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('ai_workflow.app_contextWindow')">
              <el-input-number
                v-model="formData.context_window"
                :min="0"
                :step="1024"
                :controls="false"
                style="width: 100%"
                :placeholder="t('ai_workflow.app_contextWindowPlaceholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('ai_workflow.app_timeout')">
              <el-input-number
                v-model="formData.timeout"
                :min="5"
                :max="600"
                :step="5"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('ai_workflow.app_systemPrompt')">
          <el-input
            v-model="formData.system_prompt"
            type="textarea"
            :rows="3"
            :placeholder="t('ai_workflow.app_systemPromptPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_tags')">
          <el-input
            v-model="tagsInput"
            :placeholder="t('ai_workflow.app_tagsPlaceholder')"
            clearable
            @change="tagsInputToArray"
          />
          <div v-if="formData.tags.length" class="app-tags">
            <el-tag
              v-for="(t, i) in formData.tags"
              :key="i"
              size="small"
              closable
              @close="formData.tags.splice(i, 1)"
            >
              {{ t }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_memory')">
          <el-switch v-model="formData.memory" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_tools')">
          <el-select
            v-model="formData.tools"
            multiple
            clearable
            :placeholder="t('ai_workflow.app_toolsPlaceholder')"
            style="width: 100%"
          >
            <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_outputFormat')">
          <el-select v-model="formData.output_format" style="width: 100%">
            <el-option :label="t('ai_workflow.app_text')" value="text" />
            <el-option :label="t('ai_workflow.app_table')" value="table" />
            <el-option :label="t('ai_workflow.app_report')" value="report" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_inputFields')">
          <div class="field-builder">
            <div v-for="(f, i) in formData.inputFields" :key="i" class="field-row">
              <el-input
                v-model="f.key"
                :placeholder="t('ai_workflow.app_fieldName')"
                class="field-row__key"
              />
              <el-select v-model="f.type" class="field-row__type">
                <el-option :label="t('ai_workflow.app_text')" value="string" />
                <el-option :label="t('ai_workflow.app_number')" value="number" />
                <el-option :label="t('ai_workflow.app_boolean')" value="boolean" />
                <el-option :label="t('ai_workflow.app_array')" value="array" />
                <el-option :label="t('ai_workflow.app_object')" value="object" />
              </el-select>
              <el-input
                v-model="f.default"
                :placeholder="t('ai_workflow.app_fieldDefault')"
                class="field-row__default"
              />
              <el-checkbox v-model="f.required" class="field-row__req">
                {{ t("ai_workflow.app_fieldRequired") }}
              </el-checkbox>
              <el-button
                text
                type="danger"
                :icon="Delete"
                @click="formData.inputFields.splice(i, 1)"
              />
            </div>
            <el-button
              text
              type="primary"
              :icon="Plus"
              @click="
                formData.inputFields.push({ key: '', type: 'string', default: '', required: false })
              "
            >
              {{ t("ai_workflow.app_addField") }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_order')">
          <el-input-number v-model="formData.order" :min="0" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.app_enabled')">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">{{ t("ai_workflow.app_cancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ t("ai_workflow.app_save") }}
        </el-button>
      </template>
    </EnhancedDialog>

    <!-- 应用组件详情 + 运行调试 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || t('ai_workflow.app_detailTitle')"
      size="520px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item :label="t('ai_workflow.app_componentType')">
          <el-tag size="small" :type="typeTagType(detail.app_type)" effect="plain">
            {{ typeLabel(detail.app_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_model')">
          {{ modelName(detail.model_id) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.app_type === 'kb'" :label="t('ai_workflow.app_kb')">
          {{ kbName(detail.kb_id) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.workflow_id" :label="t('ai_workflow.app_workflow')">
          {{ wfName(detail.workflow_id) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_prompt')">
          {{ promptName(detail.prompt_id) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_toolCount')">
          {{ (detail.tools || []).length }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_outputFormat')">
          {{ formatLabel(detail.output_format) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_enabled')">
          <el-tag size="small" :type="detail.enabled ? 'success' : 'info'">
            {{
              detail.enabled ? t("ai_workflow.app_enabledText") : t("ai_workflow.app_disabledText")
            }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.app_createdTime')">
          {{ detail.created_time }}
        </el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">{{ t("ai_workflow.app_runDebug") }}</el-divider>
      <div class="app-run">
        <div class="app-run__input">
          <el-input
            v-model="runQuery"
            :placeholder="t('ai_workflow.app_runPlaceholder')"
            @keyup.enter="runDebug"
          />
          <el-button type="primary" :loading="runLoading" @click="runDebug">
            {{ t("ai_workflow.app_send") }}
          </el-button>
        </div>
        <div v-loading="runLoading" class="app-run__output">
          <template v-if="runAnswer">
            <div class="app-run__bot">
              <span class="app-run__label">{{ t("ai_workflow.app_answer") }}</span>
              <div class="app-run__text">{{ runAnswer }}</div>
            </div>
          </template>
          <el-empty v-else :description="t('ai_workflow.app_runEmpty')" :image-size="50" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Auth } from "@/utils/auth";
import { readAgnoFrames } from "@/composables/ai/agnoSse";
import { Delete, Plus, ArrowDown } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import {
  createAiApp,
  deleteAiApp,
  getAiAppList,
  getAiAppTemplates,
  createAiAppFromTemplate,
  updateAiApp,
  batchAppStatus,
} from "@/api/module_ai/app";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { getAiWorkflowList } from "@/api/module_ai/workflow";

defineOptions({ name: "AiApp" });

const { t } = useI18n();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:app",
  colon: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("ai_workflow.app_name"),
      type: "input",
      attrs: {
        placeholder: t("ai_workflow.app_namePlaceholder"),
        clearable: true,
        style: { width: "200px" },
      },
    },
    {
      prop: "enabled",
      label: t("ai_workflow.app_enabled"),
      type: "select",
      options: [
        { label: t("ai_workflow.app_enabledText"), value: "true" },
        { label: t("ai_workflow.app_disabledText"), value: "false" },
      ],
      attrs: {
        placeholder: t("ai_workflow.app_selectStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:app",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: false,
  indexAction: async (params) => {
    const res = await getAiAppList();
    const list = res.data?.data || [];
    const name = (params as any)?.name;
    const enabled = (params as any)?.enabled;
    if (!name && enabled === undefined) return list;
    return list.filter(
      (x: any) =>
        (!name || (x.name || "").includes(name)) &&
        (enabled === undefined || String(x.enabled) === enabled)
    );
  },
  deleteAction: async (ids) => {
    await deleteAiApp(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { type: "warning" },
});

const modelOptions = ref<any[]>([]);
const promptOptions = ref<any[]>([]);
const toolOptions = ref<any[]>([]);
const kbOptions = ref<any[]>([]);
const wfOptions = ref<any[]>([]);
const appTemplates = ref<any[]>([]);
async function loadAppTemplates() {
  try {
    appTemplates.value = (await getAiAppTemplates()).data?.data || [];
  } catch {
    appTemplates.value = [];
  }
}
async function createFromTemplate(tpl: any) {
  try {
    const r = await createAiAppFromTemplate(tpl.key, tpl.name);
    ElMessage.success(
      t("ai_workflow.app_fromTemplateSuccess", { name: r.data?.data?.name || tpl.name })
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.app_createFail"));
  }
}

const dialogVisible = ref(false);
const dialogTitle = ref(t("ai_workflow.app_createTitle"));
const submitLoading = ref(false);
const formRef = ref();

const emptyForm = () => ({
  id: undefined as number | undefined,
  name: "",
  icon: "",
  description: "",
  model_id: null as number | null,
  prompt_id: null as number | null,
  tools: [] as string[],
  output_format: "text",
  input_schema_text: "",
  inputFields: [] as { key: string; type: string; default: string; required: boolean }[],
  order: 0,
  enabled: true,
  app_type: "chat",
  kb_id: null as number | null,
  workflow_id: null as number | null,
  temperature: null as number | null,
  max_tokens: null as number | null,
  context_window: null as number | null,
  system_prompt: "",
  tags: [] as string[],
  memory: true,
  timeout: 60,
});

const formData = reactive(emptyForm());
const tagsInput = ref("");
const appSelIds = ref<number[]>([]);
function onAppSel(sel: any[]) {
  appSelIds.value = sel.map((s: any) => s.id);
}
async function batchApp(enabled: boolean) {
  if (!appSelIds.value.length) return;
  try {
    const r = await batchAppStatus(appSelIds.value, enabled);
    ElMessage.success(
      t("ai_workflow.app_batchResult", {
        action: enabled ? t("ai_workflow.app_enabledText") : t("ai_workflow.app_disabledText"),
        count: r.data?.data?.count || 0,
      })
    );
    refreshList();
    loadAppSummary();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_workflow.app_opFail"));
  }
}
const appSummary = ref({ total: 0, enabled: 0, disabled: 0 });
async function loadAppSummary() {
  try {
    const res = await getAiAppList();
    const list = res.data?.data || [];
    appSummary.value = {
      total: list.length,
      enabled: list.filter((x: any) => x.enabled).length,
      disabled: list.filter((x: any) => !x.enabled).length,
    };
  } catch {
    /* 忽略 */
  }
}
function tagsInputToArray() {
  formData.tags = (tagsInput.value || "")
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

const modelMap = computed(() => {
  const map: Record<number, string> = {};
  modelOptions.value.forEach((m) => (map[m.id] = m.name));
  return map;
});
const promptMap = computed(() => {
  const map: Record<number, string> = {};
  promptOptions.value.forEach((p) => (map[p.id] = p.name));
  return map;
});

function modelName(id: number | null) {
  if (!id) return t("ai_workflow.app_default");
  return modelMap.value[id] || `#${id}`;
}
function promptName(id: number | null) {
  if (!id) return t("ai_workflow.app_default");
  return promptMap.value[id] || `#${id}`;
}
function formatLabel(fmt: string) {
  return (
    {
      text: t("ai_workflow.app_text"),
      table: t("ai_workflow.app_table"),
      report: t("ai_workflow.app_report"),
    }[fmt || "text"] || fmt
  );
}
function typeLabel(t2: string) {
  return (
    {
      chat: t("ai_workflow.app_typeChat"),
      agent: t("ai_workflow.app_typeAgent"),
      workflow: t("ai_workflow.app_typeWorkflow"),
      kb: t("ai_workflow.app_typeKbShort"),
    }[t2 || "chat"] || t2
  );
}
function typeTagType(t2: string): "primary" | "success" | "warning" | "danger" | "info" {
  const m: Record<string, "primary" | "success" | "warning" | "danger"> = {
    chat: "primary",
    agent: "success",
    workflow: "warning",
    kb: "danger",
  };
  return m[t2 || "chat"] || "info";
}

async function loadOptions() {
  try {
    const [models, prompts, tools, kbs, wfs] = await Promise.all([
      getAiModelList(),
      getAiPromptList(),
      getAiToolList(),
      getAiKnowledgeList(),
      getAiWorkflowList(),
    ]);
    modelOptions.value = models.data?.data || [];
    promptOptions.value = prompts.data?.data || [];
    toolOptions.value = (tools.data?.data || []).filter((t2: any) => t2.enabled);
    kbOptions.value = kbs.data?.data || [];
    wfOptions.value = wfs.data?.data || [];
  } catch {
    // 选项加载失败不阻断列表展示
  }
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

function handleOpenDialog(row?: any) {
  Object.assign(formData, emptyForm());
  if (row) {
    dialogTitle.value = t("ai_workflow.app_editTitle");
    formData.id = row.id;
    formData.name = row.name;
    formData.icon = row.icon || "";
    formData.description = row.description || "";
    formData.model_id = row.model_id ?? null;
    formData.prompt_id = row.prompt_id ?? null;
    formData.tools = [...(row.tools || [])];
    formData.output_format = row.output_format || "text";
    formData.inputFields = schemaToFields(row.input_schema);
    formData.order = row.order ?? 0;
    formData.enabled = row.enabled !== false;
    formData.app_type = row.app_type || "chat";
    formData.kb_id = row.kb_id ?? null;
    formData.workflow_id = row.workflow_id ?? null;
    formData.temperature = row.temperature ?? null;
    formData.max_tokens = row.max_tokens ?? null;
    formData.context_window = row.context_window ?? null;
    formData.system_prompt = row.system_prompt || "";
    formData.tags = [...(row.tags || [])];
    formData.memory = row.memory !== false;
    formData.timeout = row.timeout || 60;
    tagsInput.value = (row.tags || []).join(",");
  } else {
    dialogTitle.value = t("ai_workflow.app_createTitle");
  }
  dialogVisible.value = true;
}

function handleCloseDialog() {
  dialogVisible.value = false;
  Object.assign(formData, emptyForm());
}

function coerceDefault(v: string, type: string): any {
  if (v === "" || v === undefined || v === null) return undefined;
  if (type === "number") {
    const n = Number(v);
    return Number.isNaN(n) ? v : n;
  }
  if (type === "boolean") return v === "true" || v === "1";
  if (type === "array") {
    try {
      return JSON.parse(v);
    } catch {
      return v;
    }
  }
  return v;
}
function schemaToFields(
  schema: any
): { key: string; type: string; default: string; required: boolean }[] {
  if (!schema || typeof schema !== "object") return [];
  const props = schema.properties || {};
  const required = new Set(schema.required || []);
  return Object.entries<any>(props).map(([key, spec]) => ({
    key,
    type: spec?.type || "string",
    default: spec?.default === undefined ? "" : String(spec.default),
    required: required.has(key),
  }));
}
function fieldsToSchema(fields: any[]): Record<string, any> | undefined {
  const properties: Record<string, any> = {};
  const required: string[] = [];
  for (const f of fields || []) {
    const key = (f.key || "").trim();
    if (!key) continue;
    const p: Record<string, any> = { type: f.type || "string" };
    const dv = coerceDefault(f.default, f.type);
    if (dv !== undefined) p.default = dv;
    if (f.required) required.push(key);
    properties[key] = p;
  }
  if (!Object.keys(properties).length) return undefined;
  const schema: Record<string, any> = { type: "object", properties, additionalProperties: false };
  if (required.length) schema.required = required;
  return schema;
}

async function handleSubmit() {
  if (!formData.name.trim()) {
    ElMessage.warning(t("ai_workflow.app_nameRequired"));
    return;
  }
  const inputSchema = fieldsToSchema(formData.inputFields);
  const payload: any = {
    name: formData.name.trim(),
    icon: formData.icon.trim(),
    description: formData.description || null,
    model_id: formData.model_id,
    prompt_id: formData.prompt_id,
    tools: formData.tools,
    output_format: formData.output_format,
    input_schema: inputSchema,
    order: formData.order,
    enabled: formData.enabled,
    app_type: formData.app_type,
    kb_id: formData.app_type === "kb" ? formData.kb_id : null,
    workflow_id: formData.workflow_id,
    temperature: formData.temperature,
    max_tokens: formData.max_tokens,
    context_window: formData.context_window,
    system_prompt: formData.system_prompt || null,
    tags: formData.tags,
    memory: formData.memory,
    timeout: formData.timeout,
  };
  submitLoading.value = true;
  try {
    if (formData.id) await updateAiApp(formData.id, payload);
    else await createAiApp(payload);
    dialogVisible.value = false;
    refreshList();
    ElMessage.success(t("ai_workflow.app_saveSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.app_saveFail"));
  } finally {
    submitLoading.value = false;
  }
}

// ---- 详情 / 复制 / 运行调试 ----
const detailVisible = ref(false);
const detail = ref<any>(null);
function openDetail(row: any) {
  detail.value = row;
  detailVisible.value = true;
}
function kbName(id: number | null) {
  if (!id) return "—";
  return kbOptions.value.find((k: any) => k.id === id)?.name || `#${id}`;
}
function wfName(id: number | null) {
  if (!id) return "—";
  return wfOptions.value.find((w: any) => w.id === id)?.name || `#${id}`;
}
async function doCopy(row: any) {
  try {
    await createAiApp({
      name: t("ai_workflow.app_copyName", { name: row.name }),
      icon: row.icon || "",
      description: row.description || "",
      model_id: row.model_id ?? null,
      prompt_id: row.prompt_id ?? null,
      tools: row.tools || [],
      output_format: row.output_format || "text",
      input_schema: row.input_schema || undefined,
      order: 0,
      enabled: row.enabled !== false,
      app_type: row.app_type || "chat",
      kb_id: row.kb_id ?? null,
      workflow_id: row.workflow_id ?? null,
    });
    ElMessage.success(t("ai_workflow.app_copySuccess"));
    refreshList();
  } catch {
    ElMessage.error(t("ai_workflow.app_copyFail"));
  }
}

const runQuery = ref("");
const runAnswer = ref("");
const runLoading = ref(false);
async function runDebug() {
  if (!detail.value || !runQuery.value.trim()) return;
  runLoading.value = true;
  runAnswer.value = "";
  try {
    const resp = await fetch(`/api/v1/ai/apps/${detail.value.id}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken()}`,
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: runQuery.value }],
      }),
    });
    if (!resp.ok || !resp.body) throw new Error(t("ai_workflow.app_requestFail"));
    // Agno 原生事件流：正文来自 RunContent，错误来自 RunError
    for await (const { event, data } of readAgnoFrames(resp)) {
      if (event === "RunContent") {
        const text = typeof data.content === "string" ? data.content : "";
        if (text) runAnswer.value += text;
      } else if (event === "RunError") {
        runAnswer.value += `\n${t("ai_workflow.app_errorPrefix")} ${data.error || data.message || ""}`;
      }
    }
  } catch (e: any) {
    runAnswer.value = t("ai_workflow.app_runFail", { message: e?.message || e });
  } finally {
    runLoading.value = false;
  }
}

onMounted(() => {
  loadOptions();
  loadAppSummary();
  loadAppTemplates();
});
</script>

<style scoped>
.ai-app-page {
  flex-shrink: 0;
}
.app-run__input {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.app-run__output {
  min-height: 160px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
}
.app-run__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.app-run__text {
  line-height: 1.7;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  word-break: break-word;
  white-space: pre-wrap;
}
.app-tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.batch-bar {
  margin-bottom: 8px;
}
.summary-tag {
  margin-left: 8px;
}
.field-builder {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.field-row__key {
  width: 160px;
}
.field-row__type {
  width: 100px;
}
.field-row__default {
  flex: 1;
}
.field-row__req {
  flex-shrink: 0;
}
</style>
