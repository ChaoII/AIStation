<!-- 工具创建/编辑对话框：HTTP/脚本表单 + Agno 配置 + 测试/试运行。
     由「能力市场 → 我的资产」挂载，复用原工具中心逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="600px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <!-- Agno / 系统工具：按 config_fields 自动生成 + 自定义参数 -->
    <el-form v-if="mode === 'agno-config'" label-width="140px">
      <el-form-item
        v-for="field in currentConfigFields"
        :key="field.key"
        :label="field.label || field.key"
        :required="!!field.required"
      >
        <el-input
          v-if="field.secret"
          v-model="agnoFields[field.key]"
          type="password"
          show-password
          :placeholder="field.required ? t('ai_market.required') : t('ai_market.optional')"
        />
        <el-input
          v-else
          v-model="agnoFields[field.key]"
          :placeholder="field.required ? t('ai_market.required') : t('ai_market.optional')"
        />
      </el-form-item>

      <el-divider content-position="left">{{ t("ai_market.customParams") }}</el-divider>
      <div v-for="(param, index) in customParams" :key="index" class="custom-param">
        <el-input
          v-model="param.key"
          :placeholder="t('ai_market.paramNamePlaceholder')"
          class="custom-param__key"
        />
        <el-input
          v-model="param.value"
          :placeholder="t('ai_market.paramValuePlaceholder')"
          class="custom-param__value"
        />
        <el-button text type="danger" :icon="Delete" @click="removeCustomParam(index)" />
      </div>
      <el-button text type="primary" :icon="Plus" @click="addCustomParam">
        {{ t("ai_market.addParam") }}
      </el-button>
    </el-form>

    <!-- HTTP / 脚本 工具表单 -->
    <el-form v-else :model="httpForm" label-width="120px">
      <el-form-item :label="t('ai_market.toolName')" required>
        <el-input v-model="httpForm.name" :placeholder="t('ai_market.toolNamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('ai_market.toolType')">
        <el-radio-group v-model="httpForm.kind" :disabled="kindLocked">
          <el-radio-button value="http">{{ t("ai_market.httpRequest") }}</el-radio-button>
          <el-radio-button value="script" :disabled="scriptLocked">
            {{ t("ai_market.pythonScript") }}
          </el-radio-button>
        </el-radio-group>
        <el-alert
          v-if="scriptLocked"
          type="warning"
          :closable="false"
          show-icon
          :title="t('ai_market.scriptDisabledAlert')"
          class="script-locked-tip"
        />
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" :label="t('ai_market.requestMethod')">
        <el-select v-model="httpForm.method" style="width: 100%">
          <el-option label="GET" value="GET" />
          <el-option label="POST" value="POST" />
          <el-option label="PUT" value="PUT" />
          <el-option label="PATCH" value="PATCH" />
          <el-option label="DELETE" value="DELETE" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" :label="t('ai_market.requestUrl')" required>
        <el-input v-model="httpForm.url" :placeholder="t('ai_market.urlPlaceholder')" />
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" :label="t('ai_market.requestHeaders')">
        <div class="header-builder">
          <div v-for="(h, i) in httpForm.headerFields" :key="i" class="header-row">
            <el-input v-model="h.key" :placeholder="t('ai_market.headerNamePlaceholder')" />
            <el-input v-model="h.value" :placeholder="t('ai_market.valuePlaceholder')" />
            <el-button
              text
              type="danger"
              :icon="Delete"
              @click="httpForm.headerFields.splice(i, 1)"
            />
          </div>
          <el-button
            text
            type="primary"
            :icon="Plus"
            @click="httpForm.headerFields.push({ key: '', value: '' })"
          >
            {{ t("ai_market.addHeader") }}
          </el-button>
        </div>
      </el-form-item>
      <el-form-item :label="t('ai_market.paramFieldsLabel')">
        <div class="header-builder">
          <div v-for="(p, i) in httpForm.paramFields" :key="i" class="field-param-row">
            <el-input
              v-model="p.key"
              :placeholder="t('ai_market.fieldNamePlaceholder')"
              class="field-row__key"
            />
            <el-select v-model="p.type" class="field-row__type">
              <el-option :label="t('ai_market.typeText')" value="string" />
              <el-option :label="t('ai_market.typeInteger')" value="integer" />
              <el-option :label="t('ai_market.typeNumber')" value="number" />
              <el-option :label="t('ai_market.typeBoolean')" value="boolean" />
              <el-option :label="t('ai_market.typeArray')" value="array" />
              <el-option :label="t('ai_market.typeObject')" value="object" />
            </el-select>
            <el-input
              v-model="p.default"
              :placeholder="t('ai_market.defaultPlaceholder')"
              class="field-row__default"
            />
            <el-checkbox v-model="p.required" class="field-row__req">
              {{ t("ai_market.fieldRequired") }}
            </el-checkbox>
            <el-button
              text
              type="danger"
              :icon="Delete"
              @click="httpForm.paramFields.splice(i, 1)"
            />
          </div>
          <el-button
            text
            type="primary"
            :icon="Plus"
            @click="
              httpForm.paramFields.push({
                key: '',
                type: 'string',
                default: '',
                required: false,
                description: '',
              })
            "
          >
            {{ t("ai_market.addField") }}
          </el-button>
        </div>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" :label="t('ai_market.bodyTypeLabel')">
        <el-select v-model="httpForm.bodyType" style="width: 100%" :disabled="isGetOrDelete">
          <el-option :label="t('ai_market.bodyNone')" value="none" />
          <el-option label="JSON" value="json" />
          <el-option label="Form Data" value="form-data" />
        </el-select>
      </el-form-item>
      <el-form-item
        v-if="httpForm.kind === 'http' && bodyHintText"
        :label="t('ai_market.requestBodyLabel')"
      >
        <el-alert type="info" :closable="false" show-icon :title="bodyHintText" />
      </el-form-item>
      <template v-if="httpForm.kind === 'script'">
        <el-form-item :label="t('ai_market.scriptCode')" required>
          <div class="script-editor">
            <div class="script-editor__toolbar">
              <span class="script-editor__label">{{ t("ai_market.pythonScript") }}</span>
              <div class="script-editor__actions">
                <el-button
                  size="small"
                  :icon="MagicStick"
                  :loading="inspecting"
                  @click="handleInspectScript"
                >
                  {{ t("ai_market.extractParams") }}
                </el-button>
                <el-button
                  size="small"
                  :icon="RefreshRight"
                  :loading="formatting"
                  @click="handleFormatScript"
                >
                  {{ t("ai_market.formatScript") }}
                </el-button>
                <el-button size="small" text @click="fillScriptTemplate">
                  {{ t("ai_market.fillTemplate") }}
                </el-button>
                <el-button size="small" text type="danger" @click="clearScriptCode">
                  {{ t("ai_market.clearScript") }}
                </el-button>
              </div>
            </div>
            <CodeEditor
              v-model="httpForm.code"
              language="python"
              theme="one-dark"
              :height="'260px'"
              border
            />
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_market.timeoutLabel')">
          <el-input-number v-model="httpForm.timeout" :min="1" :max="60" />
        </el-form-item>
        <el-form-item :label="t('ai_market.runtimeParamsLabel')">
          <div class="header-builder">
            <div v-for="(rq, ri) in runtimeConfig" :key="ri" class="header-row">
              <el-input
                v-model="rq.key"
                :placeholder="t('ai_market.runtimeParamKeyPlaceholder')"
                class="field-row__key"
              />
              <el-input
                v-model="rq.value"
                type="password"
                show-password
                :placeholder="t('ai_market.runtimeValuePlaceholder')"
                class="field-row__default"
              />
              <el-button text type="danger" :icon="Delete" @click="runtimeConfig.splice(ri, 1)" />
            </div>
            <el-button
              text
              type="primary"
              :icon="Plus"
              @click="runtimeConfig.push({ key: '', value: '' })"
            >
              {{ t("ai_market.addParam") }}
            </el-button>
          </div>
          <div class="runtime-config__tip">
            {{ t("ai_market.runtimeTipPre") }}
            <code>TOOL_CONFIG["参数名"]</code>
            {{ t("ai_market.runtimeTipPost") }}
          </div>
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon :title="t('ai_market.sandboxAlert')" />
      </template>
      <el-form-item :label="t('ai_market.enableLabel')">
        <el-switch v-model="httpForm.enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button v-if="mode === 'http-edit'" :loading="testing" @click="handleTestTool">
        {{ t("ai_market.test") }}
      </el-button>
      <el-button v-if="mode === 'script-edit'" :loading="testing" @click="handleTestScript">
        {{ t("ai_market.trialRun") }}
      </el-button>
      <el-button @click="visible = false">{{ t("ai_market.cancel") }}</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
        {{ t("ai_market.save") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, MagicStick, Plus, RefreshRight } from "@element-plus/icons-vue";

import CodeEditor from "@/components/CodeEditor/index.vue";

import {
  createAiTool,
  formatAiScript,
  getAiToolList,
  getAiScriptSecurity,
  inspectAiScript,
  testAiScript,
  testAiTool,
  updateAiTool,
  type AiScriptSecurity,
  type AiToolConfigField,
  type AiToolRow,
} from "@/api/module_ai/tool";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

type DialogMode = "http-create" | "http-edit" | "script-create" | "script-edit" | "agno-config";

const mode = ref<DialogMode>("http-create");
const dialogTitle = computed(() => {
  if (mode.value === "agno-config") return t("ai_market.configTool");
  return props.realId ? t("ai_market.editTool") : t("ai_market.createTool");
});

const submitLoading = ref(false);
const testing = ref(false);
const inspecting = ref(false);
const formatting = ref(false);
/** 脚本安全配置：非超管且总开关关闭时禁用「Python 脚本」类型 */
const scriptSecurity = ref<AiScriptSecurity>({
  script_allowed: true,
  sandbox_policies: {},
  is_superuser: false,
});
const currentTool = ref<AiToolRow | null>(null);
const currentConfigFields = ref<AiToolConfigField[]>([]);
const agnoFields = reactive<Record<string, string>>({});
const customParams = ref<{ key: string; value: string }[]>([]);
/** 脚本工具运行时私有参数（密钥/敏感值/按用户区分，值不可见） */
const runtimeConfig = ref<{ key: string; value: string }[]>([]);

interface ParamField {
  key: string;
  type: string;
  default: string;
  required: boolean;
  description?: string;
}

const httpForm = reactive({
  id: undefined as number | undefined,
  name: "",
  kind: "http" as "http" | "script",
  method: "GET",
  bodyType: "none" as "none" | "json" | "form-data",
  url: "",
  headerFields: [] as { key: string; value: string }[],
  paramFields: [] as ParamField[],
  code: "",
  timeout: 10,
  enabled: true,
});

/** 编辑 HTTP/脚本时锁定类型；新建可切换 */
const kindLocked = computed(() => mode.value === "http-edit" || mode.value === "script-edit");

/** 总开关关闭且当前用户非超管时，禁止新建脚本工具（超管豁免） */
const scriptLocked = computed(
  () => !scriptSecurity.value.script_allowed && !scriptSecurity.value.is_superuser
);

/** GET/DELETE 无请求体；其余方法按「请求体类型」决定剩余入参进入 query 还是 body */
const isGetOrDelete = computed(() => ["GET", "DELETE"].includes(httpForm.method));
const bodyHintText = computed(() => {
  const m = httpForm.method;
  const bt = isGetOrDelete.value ? "none" : httpForm.bodyType;
  if (bt === "none") {
    if (isGetOrDelete.value) return t("ai_market.bodyHintGet", { m });
    return t("ai_market.bodyHintNoBody", { m });
  }
  if (bt === "form-data") return t("ai_market.bodyHintFormData", { m });
  if (m === "POST") return t("ai_market.bodyHintPost");
  if (m === "PUT") return t("ai_market.bodyHintPut");
  if (m === "PATCH") return t("ai_market.bodyHintPatch");
  return "";
});

/** 切换方法时调整请求体类型：GET/DELETE 强制 none；切回需请求体的方法时默认回 JSON */
watch(
  () => httpForm.method,
  (m) => {
    if (["GET", "DELETE"].includes(m)) {
      httpForm.bodyType = "none";
    } else if (httpForm.bodyType === "none") {
      httpForm.bodyType = "json";
    }
  }
);

function resetForm() {
  Object.assign(httpForm, {
    id: undefined,
    name: "",
    kind: "http",
    method: "GET",
    bodyType: "none",
    url: "",
    headerFields: [],
    paramFields: [],
    code: "",
    timeout: 10,
    enabled: true,
  });
  currentTool.value = null;
  currentConfigFields.value = [];
  Object.keys(agnoFields).forEach((k) => delete agnoFields[k]);
  customParams.value = [];
  runtimeConfig.value = [];
}

const SCRIPT_TEMPLATE = `def run(name: str = "world", count: int = 1) -> dict:
    """工具说明：返回问候语。

    Args:
        name: 称呼
        count: 重复次数
    """
    return {"message": f"Hello, {name}!", "count": count}
`;

function schemaToParamFields(schema: any): ParamField[] {
  if (!schema || typeof schema !== "object") return [];
  const props = schema.properties || {};
  const required = new Set(schema.required || []);
  return Object.entries<any>(props).map(([key, spec]) => ({
    key,
    type: spec?.type || "string",
    default: spec?.default === undefined ? "" : String(spec.default),
    required: required.has(key),
    description: spec?.description || "",
  }));
}

function coerceDefault(v: string, type: string): any {
  if (v === "" || v === undefined) return undefined;
  if (type === "integer" || type === "number") {
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

function paramFieldsToSchema(fields: ParamField[]): Record<string, any> | undefined {
  const properties: Record<string, any> = {};
  const required: string[] = [];
  for (const f of fields || []) {
    const key = (f.key || "").trim();
    if (!key) continue;
    const p: Record<string, any> = { type: f.type || "string" };
    const desc = (f.description || "").trim();
    if (desc) p.description = desc;
    const dv = coerceDefault(f.default, f.type);
    if (dv !== undefined) p.default = dv;
    if (f.required) required.push(key);
    properties[key] = p;
  }
  if (!Object.keys(properties).length) return undefined;
  const schema: Record<string, any> = { type: "object", properties };
  if (required.length) schema.required = required;
  return schema;
}

function buildObjectFromRows(
  rows: { key: string; value: string }[]
): Record<string, any> | undefined {
  const out: Record<string, any> = {};
  for (const r of rows || []) {
    const k = (r.key || "").trim();
    if (!k) continue;
    out[k] = r.value;
  }
  return Object.keys(out).length ? out : undefined;
}

/** 拉取脚本安全配置：决定「Python 脚本」类型是否可创建（开关关闭 + 非超管时禁用）。 */
async function loadScriptSecurity() {
  try {
    const res: any = await getAiScriptSecurity();
    scriptSecurity.value = res.data?.data || scriptSecurity.value;
  } catch {
    /* 拉取失败按默认放行；后端仍会按总开关拦截 */
  }
}

/** 打开时据 realId 加载编辑数据；无 realId 则创建。 */
async function loadForEdit() {
  if (!props.realId) {
    mode.value = "http-create";
    return;
  }
  // 工具无单条 detail，从 list 中按 id 取
  const res: any = await getAiToolList();
  const rows = (res.data?.data || []) as AiToolRow[];
  const tool = rows.find((t) => t.id === props.realId);
  if (!tool) return;
  currentTool.value = tool;
  const isScript = tool.kind === "script";
  if (tool.source === "http" || tool.source === "script") {
    mode.value = isScript ? "script-edit" : "http-edit";
    Object.assign(httpForm, {
      id: tool.id,
      name: tool.name,
      kind: isScript ? "script" : "http",
      method: tool.method || "GET",
      url: tool.url || "",
      bodyType: ["GET", "DELETE"].includes(tool.method || "GET")
        ? "none"
        : tool.body_type || "none",
      headerFields: Object.entries(tool.headers || {}).map(([k, v]) => ({
        key: k,
        value: String(v),
      })),
      paramFields: schemaToParamFields(tool.params_schema),
      code: tool.code || "",
      timeout: tool.timeout || 10,
      enabled: tool.enabled !== false,
    });
    // 脚本工具：加载运行时私有参数（值已由后端脱敏为 ****）
    runtimeConfig.value = Object.entries(tool.config || {}).map(([k, v]) => ({
      key: k,
      value: v === null || v === undefined ? "" : String(v),
    }));
  } else {
    // agno / system：配置字段自动生成
    mode.value = "agno-config";
    currentConfigFields.value = tool.config_fields || [];
    Object.keys(agnoFields).forEach((k) => delete agnoFields[k]);
    for (const field of currentConfigFields.value) {
      const value = tool.config ? tool.config[field.key] : undefined;
      agnoFields[field.key] = value === undefined || value === null ? "" : String(value);
    }
    const declared = new Set(currentConfigFields.value.map((f) => f.key));
    customParams.value = Object.entries(tool.config || {})
      .filter(([key]) => !declared.has(key))
      .map(([key, value]) => ({
        key,
        value: value === null || value === undefined ? "" : String(value),
      }));
  }
}

function addCustomParam() {
  customParams.value.push({ key: "", value: "" });
}
function removeCustomParam(index: number) {
  customParams.value.splice(index, 1);
}

async function submitAgnoConfig() {
  const tool = currentTool.value;
  if (!tool) return;
  const config: Record<string, any> = {};
  for (const field of currentConfigFields.value) {
    const value = agnoFields[field.key];
    if (field.required && (value === undefined || value === "")) {
      ElMessage.warning(t("ai_market.requiredFieldMessage", { name: field.label || field.key }));
      return;
    }
    config[field.key] = value === undefined ? "" : value;
  }
  for (const param of customParams.value) {
    const key = param.key.trim();
    if (!key) continue;
    config[key] = param.value;
  }
  submitLoading.value = true;
  try {
    await updateAiTool(tool.id, { config });
    visible.value = false;
    emit("saved");
    ElMessage.success(t("ai_market.configSaved"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_market.saveFailed"));
  } finally {
    submitLoading.value = false;
  }
}

async function submitHttpForm() {
  if (!httpForm.name.trim()) {
    ElMessage.warning(t("ai_market.requireToolName"));
    return;
  }
  const isScript = httpForm.kind === "script";
  if (isScript && scriptLocked.value) {
    ElMessage.error(t("ai_market.scriptDisabledAlert"));
    return;
  }
  if (isScript) {
    if (!httpForm.code.trim()) {
      ElMessage.warning(t("ai_market.requireScriptCode"));
      return;
    }
    // 保存前静默校验脚本（语法 + 安全白名单）
    inspecting.value = true;
    try {
      const res: any = await inspectAiScript(httpForm.code);
      const data = res.data?.data || {};
      if (!data.valid) {
        ElMessage.error(data.error || t("ai_market.scriptInvalid"));
        return;
      }
      // 若尚未提取参数且代码存在多参签名，自动提取
      if (!httpForm.paramFields.length && (data.params || []).length) {
        httpForm.paramFields = data.params.map((p: any) => ({
          key: p.name,
          type: p.type || "string",
          default: p.default === undefined || p.default === null ? "" : String(p.default),
          required: !!p.required,
          description: "",
        }));
      }
    } finally {
      inspecting.value = false;
    }
  } else if (!httpForm.url.trim()) {
    ElMessage.warning(t("ai_market.requireRequestUrl"));
    return;
  }
  const paramsSchema = paramFieldsToSchema(httpForm.paramFields);
  const payload: any = {
    name: httpForm.name.trim(),
    kind: isScript ? "script" : "http",
    params_schema: paramsSchema,
    enabled: httpForm.enabled,
  };
  if (isScript) {
    payload.code = httpForm.code;
    payload.timeout = httpForm.timeout;
    // 运行时私有参数（密钥/敏感值/按用户区分）：值不写进源码，运行时注入 TOOL_CONFIG
    payload.config = buildObjectFromRows(runtimeConfig.value);
  } else {
    payload.method = httpForm.method;
    payload.url = httpForm.url.trim();
    payload.headers = buildObjectFromRows(httpForm.headerFields);
    payload.body_type = isGetOrDelete.value ? "none" : httpForm.bodyType;
  }
  submitLoading.value = true;
  try {
    if (httpForm.id) await updateAiTool(httpForm.id, payload);
    else await createAiTool(payload);
    visible.value = false;
    emit("saved");
    ElMessage.success(t("ai_market.saveSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_market.saveFailed"));
  } finally {
    submitLoading.value = false;
  }
}

async function handleSubmit() {
  if (mode.value === "agno-config") {
    await submitAgnoConfig();
    return;
  }
  await submitHttpForm();
}

async function handleTestTool() {
  const tool = currentTool.value;
  if (!tool) return;
  testing.value = true;
  try {
    await testAiTool(tool.id);
    ElMessage.success(t("ai_market.testDone"));
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_market.testFailed"));
  } finally {
    testing.value = false;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function handleTestScript() {
  if (!httpForm.id) {
    ElMessage.warning(t("ai_market.saveBeforeTrial"));
    return;
  }
  testing.value = true;
  try {
    const res: any = await testAiScript(httpForm.id, {});
    const data = res.data?.data || {};
    if (data.ok) {
      ElMessageBox.alert(
        `<pre style="max-height:320px;overflow:auto;margin:0">${escapeHtml(
          JSON.stringify(data.result, null, 2)
        )}</pre>`,
        t("ai_market.trialResultTitle"),
        { dangerouslyUseHTMLString: true, confirmButtonText: t("ai_market.close") }
      );
    } else {
      ElMessage.error(data.error || t("ai_market.trialFailed"));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_market.trialFailed"));
  } finally {
    testing.value = false;
  }
}

/** 从代码自动提取参数：解析 run 签名，回填参数表 */
async function handleInspectScript() {
  if (!httpForm.code.trim()) {
    ElMessage.warning(t("ai_market.writeCodeFirst"));
    return;
  }
  inspecting.value = true;
  try {
    const res: any = await inspectAiScript(httpForm.code);
    const data = res.data?.data || {};
    if (!data.valid) {
      ElMessage.error(data.error || t("ai_market.scriptInvalid"));
      return;
    }
    const params = (data.params || []) as {
      name: string;
      type: string;
      default: any;
      required: boolean;
    }[];
    if (!params.length) {
      // 兼容 run(args) 单参形态：无多参可提取，提示改为手动声明
      ElMessage.info(t("ai_market.noMultiParams"));
      return;
    }
    httpForm.paramFields = params.map((p) => ({
      key: p.name,
      type: p.type || "string",
      default: p.default === undefined || p.default === null ? "" : String(p.default),
      required: !!p.required,
      description: "",
    }));
    ElMessage.success(t("ai_market.extractedParams", { count: params.length }));
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_market.parseFailed"));
  } finally {
    inspecting.value = false;
  }
}

/** 格式化脚本代码 */
async function handleFormatScript() {
  if (!httpForm.code.trim()) return;
  formatting.value = true;
  try {
    const res: any = await formatAiScript(httpForm.code);
    httpForm.code = res.data?.code ?? httpForm.code;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_market.formatFailed"));
  } finally {
    formatting.value = false;
  }
}

function fillScriptTemplate() {
  if (!httpForm.code.trim()) {
    httpForm.code = SCRIPT_TEMPLATE;
  }
}

function clearScriptCode() {
  httpForm.code = "";
}

defineExpose({ loadForEdit });

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      loadForEdit();
      loadScriptSecurity();
    }
  }
);
</script>

<style scoped>
.custom-param {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.custom-param__key {
  width: 40%;
}
.custom-param__value {
  flex: 1;
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
.field-param-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.field-row__key {
  width: 130px;
}
.field-row__type {
  width: 92px;
}
.field-row__default {
  flex: 1;
}
.field-row__req {
  flex-shrink: 0;
}
.script-editor {
  width: 100%;
}
.script-editor__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.script-editor__label {
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
}
.script-editor__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.runtime-config__tip {
  margin-top: 6px;
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.runtime-config__tip code {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
  font-family: var(--el-font-family-mono, Consolas, monospace);
}
.script-locked-tip {
  margin-top: 6px;
}
</style>
