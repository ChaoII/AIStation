<!-- 工具创建/编辑对话框：HTTP/脚本表单 + Agno 配置 + 测试/试运行。
     由「能力市场 → 我的资产」挂载，复用原工具中心逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="680px"
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
          :placeholder="field.required ? '必填' : '可选'"
        />
        <el-input
          v-else
          v-model="agnoFields[field.key]"
          :placeholder="field.required ? '必填' : '可选'"
        />
      </el-form-item>

      <el-divider content-position="left">自定义参数</el-divider>
      <div v-for="(param, index) in customParams" :key="index" class="custom-param">
        <el-input v-model="param.key" placeholder="参数名" class="custom-param__key" />
        <el-input v-model="param.value" placeholder="参数值" class="custom-param__value" />
        <el-button text type="danger" :icon="Delete" @click="removeCustomParam(index)" />
      </div>
      <el-button text type="primary" :icon="Plus" @click="addCustomParam">添加参数</el-button>
    </el-form>

    <!-- HTTP / 脚本 工具表单 -->
    <el-form v-else :model="httpForm" label-width="120px">
      <el-form-item label="工具名" required>
        <el-input v-model="httpForm.name" placeholder="唯一名称，供模型调用" />
      </el-form-item>
      <el-form-item label="工具类型">
        <el-radio-group v-model="httpForm.kind" :disabled="kindLocked">
          <el-radio-button value="http">HTTP 请求</el-radio-button>
          <el-radio-button value="script">Python 脚本</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" label="请求方法">
        <el-select v-model="httpForm.method" style="width: 100%">
          <el-option label="GET" value="GET" />
          <el-option label="POST" value="POST" />
          <el-option label="PUT" value="PUT" />
          <el-option label="PATCH" value="PATCH" />
          <el-option label="DELETE" value="DELETE" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" label="请求地址" required>
        <el-input
          v-model="httpForm.url"
          placeholder="如 https://api.example.com/items/{id}，{id} 会被入参替换"
        />
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" label="请求头">
        <div class="header-builder">
          <div v-for="(h, i) in httpForm.headerFields" :key="i" class="header-row">
            <el-input v-model="h.key" placeholder="请求头名，如 Authorization" />
            <el-input v-model="h.value" placeholder="值" />
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
            添加请求头
          </el-button>
        </div>
      </el-form-item>
      <el-form-item label="入参字段">
        <div class="header-builder">
          <div v-for="(p, i) in httpForm.paramFields" :key="i" class="field-param-row">
            <el-input v-model="p.key" placeholder="字段名，如 id" class="field-row__key" />
            <el-select v-model="p.type" class="field-row__type">
              <el-option label="文本" value="string" />
              <el-option label="整数" value="integer" />
              <el-option label="数值" value="number" />
              <el-option label="布尔" value="boolean" />
              <el-option label="数组" value="array" />
              <el-option label="对象" value="object" />
            </el-select>
            <el-input v-model="p.default" placeholder="默认值" class="field-row__default" />
            <el-checkbox v-model="p.required" class="field-row__req">必填</el-checkbox>
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
            添加字段
          </el-button>
        </div>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http'" label="请求体类型">
        <el-select v-model="httpForm.bodyType" style="width: 100%" :disabled="isGetOrDelete">
          <el-option label="无（参数走查询串）" value="none" />
          <el-option label="JSON" value="json" />
          <el-option label="Form Data" value="form-data" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="httpForm.kind === 'http' && bodyHintText" label="请求体">
        <el-alert type="info" :closable="false" show-icon :title="bodyHintText" />
      </el-form-item>
      <template v-if="httpForm.kind === 'script'">
        <el-form-item label="脚本代码" required>
          <div class="script-editor">
            <div class="script-editor__toolbar">
              <span class="script-editor__label">Python 脚本</span>
              <div class="script-editor__actions">
                <el-button
                  size="small"
                  :icon="MagicStick"
                  :loading="inspecting"
                  @click="handleInspectScript"
                >
                  从代码提取参数
                </el-button>
                <el-button
                  size="small"
                  :icon="RefreshRight"
                  :loading="formatting"
                  @click="handleFormatScript"
                >
                  格式化
                </el-button>
                <el-button size="small" text @click="fillScriptTemplate">填入示例</el-button>
                <el-button size="small" text type="danger" @click="clearScriptCode">清空</el-button>
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
        <el-form-item label="执行超时(秒)">
          <el-input-number v-model="httpForm.timeout" :min="1" :max="60" />
        </el-form-item>
        <el-form-item label="运行时参数">
          <div class="header-builder">
            <div v-for="(rq, ri) in runtimeConfig" :key="ri" class="header-row">
              <el-input v-model="rq.key" placeholder="参数名，如 api_key" class="field-row__key" />
              <el-input
                v-model="rq.value"
                type="password"
                show-password
                placeholder="值（保存后不可见）"
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
              添加参数
            </el-button>
          </div>
          <div class="runtime-config__tip">
            用于密钥/敏感值/按用户区分的参数（如 api_key、用户名）。脚本内通过
            <code>TOOL_CONFIG["参数名"]</code>
            读取，不写进源码；值保存后一律不可见。
          </div>
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="脚本在受控沙箱内运行：仅允许导入 json/math/re/datetime 等白名单模块，禁止文件、网络与系统调用。建议用带类型注解的多参数签名（如 def run(name: str = 'x')），点击「从代码提取参数」自动生成入参表。"
        />
      </template>
      <el-form-item label="启用">
        <el-switch v-model="httpForm.enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button v-if="mode === 'http-edit'" :loading="testing" @click="handleTestTool">
        测试
      </el-button>
      <el-button v-if="mode === 'script-edit'" :loading="testing" @click="handleTestScript">
        试运行
      </el-button>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, MagicStick, Plus, RefreshRight } from "@element-plus/icons-vue";

import CodeEditor from "@/components/CodeEditor/index.vue";

import {
  createAiTool,
  formatAiScript,
  getAiToolList,
  inspectAiScript,
  testAiScript,
  testAiTool,
  updateAiTool,
  type AiToolConfigField,
  type AiToolRow,
} from "@/api/module_ai/tool";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

type DialogMode = "http-create" | "http-edit" | "script-create" | "script-edit" | "agno-config";

const mode = ref<DialogMode>("http-create");
const dialogTitle = computed(() => {
  if (mode.value === "agno-config") return "配置工具";
  return props.realId ? "编辑工具" : "新增工具";
});

const submitLoading = ref(false);
const testing = ref(false);
const inspecting = ref(false);
const formatting = ref(false);
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

/** GET/DELETE 无请求体；其余方法按「请求体类型」决定剩余入参进入 query 还是 body */
const isGetOrDelete = computed(() => ["GET", "DELETE"].includes(httpForm.method));
const bodyHintText = computed(() => {
  const m = httpForm.method;
  const bt = isGetOrDelete.value ? "none" : httpForm.bodyType;
  if (bt === "none") {
    if (isGetOrDelete.value) return `${m} 无请求体，剩余入参字段作为查询串。`;
    return `以 ${m} 发送，不携带请求体，剩余入参字段作为查询串。`;
  }
  if (bt === "form-data")
    return `以 ${m} 发送，剩余入参字段作为 application/x-www-form-urlencoded 表单（Form Data）。`;
  if (m === "POST") return "以 POST 发送，剩余入参字段作为 JSON 请求体。";
  if (m === "PUT") return "以 PUT 发送，剩余入参字段作为 JSON 请求体（整体替换）。";
  if (m === "PATCH") return "以 PATCH 发送，剩余入参字段作为 JSON 请求体（局部更新）。";
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
      ElMessage.warning(`请填写必填项：${field.label || field.key}`);
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
    ElMessage.success("配置已保存");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

async function submitHttpForm() {
  if (!httpForm.name.trim()) {
    ElMessage.warning("请填写工具名");
    return;
  }
  const isScript = httpForm.kind === "script";
  if (isScript) {
    if (!httpForm.code.trim()) {
      ElMessage.warning("请填写脚本代码");
      return;
    }
    // 保存前静默校验脚本（语法 + 安全白名单）
    inspecting.value = true;
    try {
      const res: any = await inspectAiScript(httpForm.code);
      const data = res.data?.data || {};
      if (!data.valid) {
        ElMessage.error(data.error || "脚本校验未通过");
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
    ElMessage.warning("请填写请求地址");
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
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
    ElMessage.success("测试完成");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "测试失败");
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
    ElMessage.warning("请先保存脚本，再试运行");
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
        "试运行结果",
        { dangerouslyUseHTMLString: true, confirmButtonText: "关闭" }
      );
    } else {
      ElMessage.error(data.error || "试运行失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "试运行失败");
  } finally {
    testing.value = false;
  }
}

/** 从代码自动提取参数：解析 run 签名，回填参数表 */
async function handleInspectScript() {
  if (!httpForm.code.trim()) {
    ElMessage.warning("请先编写脚本代码");
    return;
  }
  inspecting.value = true;
  try {
    const res: any = await inspectAiScript(httpForm.code);
    const data = res.data?.data || {};
    if (!data.valid) {
      ElMessage.error(data.error || "脚本校验未通过");
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
      ElMessage.info(
        "未检测到多参数：当前为 run(args) 形态，可改用带类型注解的多参数签名以便自动提取"
      );
      return;
    }
    httpForm.paramFields = params.map((p) => ({
      key: p.name,
      type: p.type || "string",
      default: p.default === undefined || p.default === null ? "" : String(p.default),
      required: !!p.required,
      description: "",
    }));
    ElMessage.success(`已从代码提取 ${params.length} 个参数`);
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "解析失败");
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
    ElMessage.error(e?.msg || "格式化失败");
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
    if (v) loadForEdit();
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
</style>
