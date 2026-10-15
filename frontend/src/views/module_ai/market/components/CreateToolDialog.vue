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
            <el-button text type="danger" :icon="Delete" @click="httpForm.headerFields.splice(i, 1)" />
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
              httpForm.paramFields.push({ key: '', type: 'string', default: '', required: false })
            "
          >
            添加字段
          </el-button>
        </div>
      </el-form-item>
      <template v-if="httpForm.kind === 'script'">
        <el-form-item label="脚本代码" required>
          <el-input
            v-model="httpForm.code"
            type="textarea"
            :rows="12"
            spellcheck="false"
            placeholder='必须定义 run(args) 函数，返回 dict，例如：&#10;def run(args):&#10;    return {"sum": args.get("a", 0) + args.get("b", 0)}'
          />
        </el-form-item>
        <el-form-item label="执行超时(秒)">
          <el-input-number v-model="httpForm.timeout" :min="1" :max="60" />
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="脚本在受控沙箱内运行：仅允许导入 json/math/re/datetime 等白名单模块，禁止文件、网络与系统调用。"
        />
      </template>
      <el-form-item label="启用">
        <el-switch v-model="httpForm.enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button
        v-if="mode === 'http-edit'"
        :loading="testing"
        @click="handleTestTool"
      >
        测试
      </el-button>
      <el-button
        v-if="mode === 'script-edit'"
        :loading="testing"
        @click="handleTestScript"
      >
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
import { Delete, Plus } from "@element-plus/icons-vue";

import {
  createAiTool,
  getAiToolList,
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
const currentTool = ref<AiToolRow | null>(null);
const currentConfigFields = ref<AiToolConfigField[]>([]);
const agnoFields = reactive<Record<string, string>>({});
const customParams = ref<{ key: string; value: string }[]>([]);

const httpForm = reactive({
  id: undefined as number | undefined,
  name: "",
  kind: "http" as "http" | "script",
  method: "GET",
  url: "",
  headerFields: [] as { key: string; value: string }[],
  paramFields: [] as { key: string; type: string; default: string; required: boolean }[],
  code: "",
  timeout: 10,
  enabled: true,
});

/** 编辑 HTTP/脚本时锁定类型；新建可切换 */
const kindLocked = computed(() => mode.value === "http-edit" || mode.value === "script-edit");

function resetForm() {
  Object.assign(httpForm, {
    id: undefined,
    name: "",
    kind: "http",
    method: "GET",
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
}

function schemaToParamFields(
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

function paramFieldsToSchema(fields: any[]): Record<string, any> | undefined {
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
      headerFields: Object.entries(tool.headers || {}).map(([k, v]) => ({ key: k, value: String(v) })),
      paramFields: schemaToParamFields(tool.params_schema),
      code: tool.code || "",
      timeout: tool.timeout || 10,
      enabled: tool.enabled !== false,
    });
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
      .map(([key, value]) => ({ key, value: value === null || value === undefined ? "" : String(value) }));
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
  } else {
    payload.method = httpForm.method;
    payload.url = httpForm.url.trim();
    payload.headers = buildObjectFromRows(httpForm.headerFields);
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
    const data = res.data || {};
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
</style>
