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
              <el-empty :image-size="80" description="暂无 AI 应用" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="图标" width="80" align="center">
              <template #default="{ row }">
                <el-icon v-if="row.icon"><component :is="row.icon" /></el-icon>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
            <el-table-column label="类型" width="120" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="typeTagType(row.app_type)" effect="plain">
                  {{ typeLabel(row.app_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="模型" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ modelName(row.model_id) }}</template>
            </el-table-column>
            <el-table-column label="提示词" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ promptName(row.prompt_id) }}</template>
            </el-table-column>
            <el-table-column label="工具数" width="90" align="center">
              <template #default="{ row }">{{ (row.tools || []).length }}</template>
            </el-table-column>
            <el-table-column label="输出格式" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ formatLabel(row.output_format) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.enabled ? 'success' : 'info'">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="260" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:app:query']"
                  size="small"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  详情
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:query']"
                  size="small"
                  link
                  type="primary"
                  @click="handleRun(row)"
                >
                  运行
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:update']"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:create']"
                  size="small"
                  link
                  @click="doCopy(row)"
                >
                  复制
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:app:delete']"
                  size="small"
                  link
                  type="danger"
                  @click="handleRowDelete(row.id)"
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
      v-model="dialogVisible"
      :title="dialogTitle"
      append-to-body
      width="660px"
      @close="handleCloseDialog"
    >
      <el-form ref="formRef" :model="formData" label-width="120px">
        <el-form-item label="名称" required>
          <el-input v-model="formData.name" placeholder="应用唯一名称" />
        </el-form-item>
        <el-form-item label="组件类型">
          <el-select v-model="formData.app_type" style="width: 100%">
            <el-option label="聊天" value="chat" />
            <el-option label="智能体" value="agent" />
            <el-option label="工作流" value="workflow" />
            <el-option label="知识库问答" value="kb" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.app_type === 'kb'" label="知识库">
          <el-select
            v-model="formData.kb_id"
            clearable
            placeholder="绑定知识库"
            style="width: 100%"
          >
            <el-option v-for="k in kbOptions" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="formData.app_type === 'workflow' || formData.workflow_id"
          label="工作流"
        >
          <el-select
            v-model="formData.workflow_id"
            clearable
            placeholder="绑定工作流"
            style="width: 100%"
          >
            <el-option v-for="w in wfOptions" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="formData.icon" placeholder="Element Plus 图标名，如 MagicStick" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="模型">
          <el-select
            v-model="formData.model_id"
            clearable
            placeholder="不选则用默认模型"
            style="width: 100%"
          >
            <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="提示词">
          <el-select
            v-model="formData.prompt_id"
            clearable
            placeholder="不选则用默认助手提示词"
            style="width: 100%"
          >
            <el-option v-for="p in promptOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="温度">
              <el-input-number
                v-model="formData.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                controls-position="right"
                style="width: 100%"
                placeholder="留空用模型默认"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大 token">
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
            <el-form-item label="上下文窗口">
              <el-input-number
                v-model="formData.context_window"
                :min="0"
                :step="1024"
                :controls="false"
                style="width: 100%"
                placeholder="如 128000"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="超时(秒)">
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
        <el-form-item label="系统提示词">
          <el-input
            v-model="formData.system_prompt"
            type="textarea"
            :rows="3"
            placeholder="自定义系统提示词（覆盖所选提示词）；留空用默认"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="tagsInput"
            placeholder="逗号分隔多个标签，如 客服, 销售"
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
        <el-form-item label="多轮记忆">
          <el-switch v-model="formData.memory" />
        </el-form-item>
        <el-form-item label="工具集">
          <el-select
            v-model="formData.tools"
            multiple
            clearable
            placeholder="选择内置 / 已启用工具"
            style="width: 100%"
          >
            <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="输出格式">
          <el-select v-model="formData.output_format" style="width: 100%">
            <el-option label="文本" value="text" />
            <el-option label="表格" value="table" />
            <el-option label="报告" value="report" />
          </el-select>
        </el-form-item>
        <el-form-item label="入参字段">
          <div class="field-builder">
            <div v-for="(f, i) in formData.inputFields" :key="i" class="field-row">
              <el-input v-model="f.key" placeholder="字段名" class="field-row__key" />
              <el-select v-model="f.type" class="field-row__type">
                <el-option label="文本" value="string" />
                <el-option label="数值" value="number" />
                <el-option label="布尔" value="boolean" />
                <el-option label="数组" value="array" />
                <el-option label="对象" value="object" />
              </el-select>
              <el-input v-model="f.default" placeholder="默认值" class="field-row__default" />
              <el-checkbox v-model="f.required" class="field-row__req">必填</el-checkbox>
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
              添加字段
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="formData.order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- 应用组件详情 + 运行调试 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || '应用详情'"
      size="520px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item label="组件类型">
          <el-tag size="small" :type="typeTagType(detail.app_type)" effect="plain">
            {{ typeLabel(detail.app_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型">{{ modelName(detail.model_id) }}</el-descriptions-item>
        <el-descriptions-item v-if="detail.app_type === 'kb'" label="知识库">
          {{ kbName(detail.kb_id) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.workflow_id" label="工作流">
          {{ wfName(detail.workflow_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="提示词">
          {{ promptName(detail.prompt_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="工具数">
          {{ (detail.tools || []).length }}
        </el-descriptions-item>
        <el-descriptions-item label="输出格式">
          {{ formatLabel(detail.output_format) }}
        </el-descriptions-item>
        <el-descriptions-item label="启用">
          <el-tag size="small" :type="detail.enabled ? 'success' : 'info'">
            {{ detail.enabled ? "启用" : "停用" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ detail.created_time }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">运行调试</el-divider>
      <div class="app-run">
        <div class="app-run__input">
          <el-input
            v-model="runQuery"
            placeholder="输入问题，调试组件（回车发送）"
            @keyup.enter="runDebug"
          />
          <el-button type="primary" :loading="runLoading" @click="runDebug">发送</el-button>
        </div>
        <div v-loading="runLoading" class="app-run__output">
          <template v-if="runAnswer">
            <div class="app-run__bot">
              <span class="app-run__label">回答</span>
              <div class="app-run__text">{{ runAnswer }}</div>
            </div>
          </template>
          <el-empty v-else description="输入问题开始调试" :image-size="50" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Auth } from "@/utils/auth";
import { Delete, Plus } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { createAiApp, deleteAiApp, getAiAppList, updateAiApp } from "@/api/module_ai/app";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { getAiWorkflowList } from "@/api/module_ai/workflow";

defineOptions({ name: "AiApp" });

const router = useRouter();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:app",
  colon: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "名称",
      type: "input",
      attrs: { placeholder: "应用名称", clearable: true, style: { width: "200px" } },
    },
    {
      prop: "enabled",
      label: "启用",
      type: "select",
      options: [
        { label: "启用", value: "true" },
        { label: "停用", value: "false" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "167.5px" } },
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
  deleteConfirm: { title: "警告", message: "确认删除所选应用?", type: "warning" },
});

const modelOptions = ref<any[]>([]);
const promptOptions = ref<any[]>([]);
const toolOptions = ref<any[]>([]);
const kbOptions = ref<any[]>([]);
const wfOptions = ref<any[]>([]);

const dialogVisible = ref(false);
const dialogTitle = ref("新增应用");
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
  if (!id) return "默认";
  return modelMap.value[id] || `#${id}`;
}
function promptName(id: number | null) {
  if (!id) return "默认";
  return promptMap.value[id] || `#${id}`;
}
function formatLabel(fmt: string) {
  return { text: "文本", table: "表格", report: "报告" }[fmt || "text"] || fmt;
}
function typeLabel(t: string) {
  return { chat: "聊天", agent: "智能体", workflow: "工作流", kb: "知识库" }[t || "chat"] || t;
}
function typeTagType(t: string): "primary" | "success" | "warning" | "danger" | "info" {
  const m: Record<string, "primary" | "success" | "warning" | "danger"> = {
    chat: "primary",
    agent: "success",
    workflow: "warning",
    kb: "danger",
  };
  return m[t || "chat"] || "info";
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
    toolOptions.value = (tools.data?.data || []).filter((t: any) => t.enabled);
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
    dialogTitle.value = "编辑应用";
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
    dialogTitle.value = "新增应用";
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
    ElMessage.warning("请填写名称");
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
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

function handleRun(row: any) {
  router.push({ path: "/ai/chat", query: { app_id: String(row.id) } });
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
      name: `${row.name}（副本）`,
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
    ElMessage.success("已复制");
    refreshList();
  } catch {
    ElMessage.error("复制失败");
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
    if (!resp.ok || !resp.body) throw new Error("请求失败");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        const s = line.trim();
        if (!s.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(s.slice(6));
          if (evt.type === "text-delta") runAnswer.value += evt.delta || "";
          else if (evt.type === "error")
            runAnswer.value += `\n[错误] ${evt.error || evt.message || ""}`;
          else if (evt.type === "text") runAnswer.value += evt.text || "";
          else if (evt.type === "finish") {
            if (evt.payload?.reply) runAnswer.value += evt.payload.reply;
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }
  } catch (e: any) {
    runAnswer.value = `运行失败：${e?.message || e}`;
  } finally {
    runLoading.value = false;
  }
}

onMounted(() => {
  loadOptions();
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
