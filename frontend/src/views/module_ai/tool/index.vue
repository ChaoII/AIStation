<!-- AI 工具中心：el-card 卡片网格 + 参数自动生成 + 自定义参数 -->
<template>
  <div class="app-container ai-tool-page">
    <!-- 顶部搜索/筛选 -->
    <el-form :inline="true" :model="searchForm" class="tool-search">
      <el-form-item label="关键字">
        <el-input
          v-model="searchForm.keyword"
          placeholder="工具名 / 简介"
          clearable
          style="width: 200px"
        />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="searchForm.source" placeholder="全部" clearable style="width: 140px">
          <el-option label="系统" value="system" />
          <el-option label="Agno" value="agno" />
          <el-option label="HTTP" value="http" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="searchForm.ready" placeholder="全部" clearable style="width: 140px">
          <el-option label="就绪" value="ready" />
          <el-option label="未就绪" value="not-ready" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button :icon="Search" @click="refreshList">刷新</el-button>
        <el-button
          v-hasPerm="['module_ai:tool:create']"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          新增工具
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 批量操作 / 统计摘要 -->
    <div class="tool-batchbar">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="isIndeterminate"
        @change="toggleSelectAll"
      >
        全选
      </el-checkbox>
      <el-button size="small" :disabled="!toolSelIds.length" @click="batchTool(true)">
        批量启用
      </el-button>
      <el-button size="small" :disabled="!toolSelIds.length" @click="batchTool(false)">
        批量停用
      </el-button>
      <el-tag size="small" type="info" effect="plain" class="summary-tag">
        共 {{ toolSummary.total }} 个工具 · 启用 {{ toolSummary.enabled }} · 停用
        {{ toolSummary.disabled }}
      </el-tag>
    </div>

    <!-- 工具卡片网格 -->
    <el-row v-loading="loading" :gutter="12" class="tool-grid">
      <el-col v-for="tool in pagedTools" :key="tool.id" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card
          shadow="hover"
          class="tool-card"
          :class="{ 'is-not-ready': !tool.ready }"
          data-testid="tool-card"
        >
          <template #header>
            <div class="tool-card__hd">
              <el-checkbox
                :model-value="isSelected(tool)"
                class="tool-card__check"
                @change="toggleSelect(tool)"
              />
              <el-avatar :size="32" :icon="iconOf(tool)" class="tool-card__avatar">
                {{ iconOf(tool) ? "" : firstChar(tool) }}
              </el-avatar>
              <span class="tool-card__name" :title="displayName(tool)">
                {{ displayName(tool) }}
              </span>
              <el-tag size="small" :type="sourceTagType(tool.source)">
                {{ sourceLabel(tool.source) }}
              </el-tag>
              <el-tag
                v-if="tool.risk === 'high'"
                size="small"
                type="danger"
                class="tool-card__risk"
                data-testid="tool-risk-tag"
              >
                高危
              </el-tag>
              <el-tag
                size="small"
                :type="tool.ready ? 'success' : 'warning'"
                class="tool-card__ready"
              >
                {{ tool.ready ? "就绪" : `未就绪：${tool.reason || "缺少配置"}` }}
              </el-tag>
            </div>
          </template>

          <div class="tool-card__body">
            <div v-if="tool.group" class="tool-card__group">{{ tool.group }}</div>
            <div class="tool-card__desc">{{ tool.description || "—" }}</div>
          </div>

          <template #footer>
            <div class="tool-card__ft">
              <span v-hasPerm="['module_ai:tool:update']">
                <el-switch
                  :model-value="tool.enabled"
                  :disabled="!tool.ready"
                  @change="(v) => onToggle(tool, Boolean(v))"
                />
              </span>
              <div class="tool-card__actions">
                <el-button text type="primary" @click="openDetail(tool)">详情</el-button>
                <el-button
                  text
                  type="primary"
                  :disabled="configDisabled(tool)"
                  @click="openConfig(tool)"
                >
                  配置
                </el-button>
                <el-button
                  v-if="tool.source === 'http'"
                  v-hasPerm="['module_ai:tool:update']"
                  text
                  type="primary"
                  @click="openEdit(tool)"
                >
                  编辑
                </el-button>
                <el-button
                  v-if="tool.source === 'http'"
                  v-hasPerm="['module_ai:tool:delete']"
                  text
                  type="danger"
                  @click="onDelete(tool)"
                >
                  删除
                </el-button>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>

      <el-col v-if="!loading && !filteredTools.length" :span="24">
        <el-empty :image-size="80" description="暂无工具，点击「新增工具」创建" />
      </el-col>
    </el-row>

    <div v-if="filteredTools.length > 0" class="tool-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="filteredTools.length"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        background
      />
    </div>

    <!-- 新增 / 编辑 / 配置 弹窗 -->
    <EnhancedDialog
      v-model="dialog.visible"
      :title="dialog.title"
      append-to-body
      width="640px"
      @close="handleCloseDialog"
    >
      <!-- Agno 工具配置：按 config_fields 自动生成 + 自定义参数 -->
      <el-form v-if="dialog.mode === 'agno-config'" label-width="140px">
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

      <!-- HTTP 工具表单 -->
      <el-form v-else :model="httpForm" label-width="120px">
        <el-form-item label="工具名" required>
          <el-input v-model="httpForm.name" placeholder="唯一名称，供模型调用" />
        </el-form-item>
        <el-form-item label="请求方法">
          <el-select v-model="httpForm.method" style="width: 100%">
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
          </el-select>
        </el-form-item>
        <el-form-item label="请求地址" required>
          <el-input
            v-model="httpForm.url"
            placeholder="如 https://api.example.com/items/{id}，{id} 会被入参替换"
          />
        </el-form-item>
        <el-form-item label="请求头">
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
                httpForm.paramFields.push({ key: '', type: 'string', default: '', required: false })
              "
            >
              添加字段
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="httpForm.enabled" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button
          v-if="dialog.mode === 'http-edit'"
          :loading="testing"
          @click="handleTestTool(currentTool)"
        >
          测试
        </el-button>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- 工具详情（结构化参数展示） -->
    <el-dialog
      v-model="detailVisible"
      :title="detailTool ? displayName(detailTool) : '工具详情'"
      width="640px"
      append-to-body
    >
      <el-descriptions v-if="detailTool" :column="2" border size="small">
        <el-descriptions-item label="来源">
          {{ sourceLabel(detailTool.source) }}
        </el-descriptions-item>
        <el-descriptions-item label="分组">{{ detailTool.group || "—" }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="detailTool.ready ? 'success' : 'warning'">
            {{ detailTool.ready ? "就绪" : "未就绪" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="风险">
          <el-tag v-if="detailTool.risk === 'high'" size="small" type="danger">高危</el-tag>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">
          {{ detailTool.description || "—" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="paramsFields.length" label="入参" :span="2">
          <div class="tool-params">
            <div v-for="p in paramsFields" :key="p.key" class="tool-params__row">
              <el-tag size="small" type="info" effect="plain">{{ p.key }}</el-tag>
              <span class="tool-params__type">{{ p.type }}</span>
              <span v-if="p.required" class="tool-params__req">必填</span>
              <span v-if="p.desc" class="tool-params__desc">{{ p.desc }}</span>
            </div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item
          v-if="detailTool.config && Object.keys(detailTool.config).length"
          label="已配置参数"
          :span="2"
        >
          <div class="tool-params">
            <div v-for="(v, k) in detailTool.config" :key="k" class="tool-params__row">
              <el-tag size="small" effect="plain">{{ k }}</el-tag>
              <span class="tool-params__val">{{ String(v) }}</span>
            </div>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch, type Component } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Cloudy,
  Coin,
  Compass,
  Connection,
  Cpu,
  DataAnalysis,
  Delete,
  Document,
  Link,
  MagicStick,
  Monitor,
  Plus,
  Reading,
  Search,
  Setting,
  Tools,
  TrendCharts,
} from "@element-plus/icons-vue";
import {
  createAiTool,
  deleteAiTool,
  getAiToolList,
  testAiTool,
  toggleAiTool,
  updateAiTool,
  batchToolStatus,
  type AiToolConfigField,
  type AiToolRow,
} from "@/api/module_ai/tool";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

defineOptions({ name: "AiTool" });

type DialogMode = "http-create" | "http-edit" | "agno-config";
type TagType = "primary" | "success" | "info" | "warning" | "danger";

// 按工具 key 映射图标；未知则按分组，再退回来源/首字符
const ICON_BY_KEY: Record<string, Component> = {
  calculator: Coin,
  csv_toolkit: DataAnalysis,
  visualization: TrendCharts,
  webtools: Link,
  hackernews: Reading,
  python: Cpu,
  shell: Monitor,
  tavily: Compass,
  serpapi: Compass,
  duckduckgo: Compass,
  wikipedia: Reading,
  openweather: Cloudy,
  newspaper: Document,
  arxiv: Document,
};

const ICON_BY_GROUP: Record<string, Component> = {
  基础: MagicStick,
  数据: DataAnalysis,
  网络: Connection,
  资讯: Document,
  高级: Cpu,
};

const loading = ref(false);
const allTools = ref<AiToolRow[]>([]);
const searchForm = reactive({ keyword: "", source: "", ready: "" });

const dialog = reactive({
  visible: false,
  mode: "http-create" as DialogMode,
  title: "",
});
const currentTool = ref<AiToolRow | null>(null);
const currentConfigFields = ref<AiToolConfigField[]>([]);
const agnoFields = reactive<Record<string, string>>({});
const customParams = ref<{ key: string; value: string }[]>([]);
const submitLoading = ref(false);
const testing = ref(false);

const httpForm = reactive({
  id: undefined as number | undefined,
  name: "",
  method: "GET",
  url: "",
  headers_text: "",
  headerFields: [] as { key: string; value: string }[],
  params_schema_text: "",
  paramFields: [] as { key: string; type: string; default: string; required: boolean }[],
  enabled: true,
});

const filteredTools = computed(() => {
  const keyword = searchForm.keyword.trim().toLowerCase();
  return allTools.value.filter((tool) => {
    if (searchForm.source && tool.source !== searchForm.source) return false;
    if (searchForm.ready === "ready" && !tool.ready) return false;
    if (searchForm.ready === "not-ready" && tool.ready) return false;
    if (keyword) {
      const haystack = [tool.name, displayName(tool), tool.description, tool.group, tool.title]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    return true;
  });
});

// ---- 分页 ----
const page = ref(1);
const pageSize = ref(12);
const pagedTools = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredTools.value.slice(start, start + pageSize.value);
});

// ---- 批量选择 / 启停 ----
const toolSelIds = ref<number[]>([]);
const toolSelSet = computed(() => new Set(toolSelIds.value));
function isSelected(tool: AiToolRow) {
  return toolSelSet.value.has(tool.id);
}
function toggleSelect(tool: AiToolRow) {
  toolSelIds.value = toolSelIds.value.includes(tool.id)
    ? toolSelIds.value.filter((id) => id !== tool.id)
    : [...toolSelIds.value, tool.id];
}
const allSelected = computed(() => {
  const ids = filteredTools.value.map((t) => t.id);
  return ids.length > 0 && ids.every((id) => toolSelSet.value.has(id));
});
const isIndeterminate = computed(() => {
  const ids = filteredTools.value.map((t) => t.id);
  const n = ids.filter((id) => toolSelSet.value.has(id)).length;
  return n > 0 && n < ids.length;
});
function toggleSelectAll(checked: boolean | string | number) {
  if (checked) {
    const ids = filteredTools.value.map((t) => t.id);
    toolSelIds.value = Array.from(new Set([...toolSelIds.value, ...ids]));
  } else {
    const pageIds = new Set(filteredTools.value.map((t) => t.id));
    toolSelIds.value = toolSelIds.value.filter((id) => !pageIds.has(id));
  }
}

// ---- 统计摘要 ----
const toolSummary = ref({ total: 0, enabled: 0, disabled: 0 });
async function batchTool(enabled: boolean) {
  if (!toolSelIds.value.length) return;
  try {
    const r = await batchToolStatus(toolSelIds.value, enabled);
    ElMessage.success(`已${enabled ? "启用" : "停用"} ${r.data?.data?.count || 0} 个工具`);
    toolSelIds.value = [];
    await refreshList();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
}

// 切换筛选时回到第一页
watch(searchForm, () => {
  page.value = 1;
});

function sourceLabel(source: string): string {
  if (source === "agno") return "Agno";
  if (source === "http") return "HTTP";
  return "系统";
}

function sourceTagType(source: string): TagType {
  if (source === "agno") return "warning";
  if (source === "http") return "success";
  return "info";
}

function displayName(tool: AiToolRow): string {
  return tool.title || tool.name;
}

function firstChar(tool: AiToolRow): string {
  return (displayName(tool) || "?").slice(0, 1).toUpperCase();
}

function iconOf(tool: AiToolRow): Component | undefined {
  return (
    ICON_BY_KEY[tool.name] ||
    (tool.group ? ICON_BY_GROUP[tool.group] : undefined) ||
    (tool.source === "http" ? Link : tool.source === "system" ? Tools : Setting)
  );
}

/** 无配置项的 agno/系统工具禁用「配置」入口；HTTP 始终可配置 */
function configDisabled(tool: AiToolRow): boolean {
  return tool.source !== "http" && !tool.config_fields?.length;
}

async function refreshList() {
  loading.value = true;
  try {
    const res = await getAiToolList();
    allTools.value = (res.data?.data || []) as AiToolRow[];
    toolSummary.value = {
      total: allTools.value.length,
      enabled: allTools.value.filter((t: AiToolRow) => t.enabled).length,
      disabled: allTools.value.filter((t: AiToolRow) => !t.enabled).length,
    };
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function onToggle(tool: AiToolRow, enabled: boolean) {
  if (!tool.ready) return;
  // 高危工具启用前二次确认（后端另有门禁，前端仅作显式提示）
  if (enabled && tool.risk === "high") {
    try {
      await ElMessageBox.confirm(
        `「${displayName(tool)}」属高危工具，启用后可执行任意代码/命令，确认启用？`,
        "高危操作确认",
        { confirmButtonText: "确认启用", cancelButtonText: "取消", type: "warning" }
      );
    } catch {
      return; // 用户取消，保持关闭
    }
  }
  try {
    await toggleAiTool(tool.id, enabled);
    tool.enabled = enabled;
    ElMessage.success(enabled ? "已启用" : "已停用");
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}

function resetHttpForm() {
  Object.assign(httpForm, {
    id: undefined,
    name: "",
    method: "GET",
    url: "",
    headers_text: "",
    headerFields: [],
    params_schema_text: "",
    paramFields: [],
    enabled: true,
  });
}

function openCreate() {
  resetHttpForm();
  currentTool.value = null;
  dialog.mode = "http-create";
  dialog.title = "新增 HTTP 工具";
  dialog.visible = true;
}

function openEdit(tool: AiToolRow) {
  resetHttpForm();
  currentTool.value = tool;
  dialog.mode = "http-edit";
  dialog.title = `编辑工具：${tool.name}`;
  Object.assign(httpForm, {
    id: tool.id,
    name: tool.name,
    method: tool.method || "GET",
    url: tool.url || "",
    headerFields: Object.entries(tool.headers || {}).map(([k, v]) => ({
      key: k,
      value: String(v),
    })),
    paramFields: schemaToParamFields(tool.params_schema),
    enabled: tool.enabled !== false,
  });
  dialog.visible = true;
}

function openConfig(tool: AiToolRow) {
  if (tool.source === "http") {
    openEdit(tool);
    return;
  }
  if (!tool.config_fields?.length) return;
  currentTool.value = tool;
  currentConfigFields.value = tool.config_fields;
  Object.keys(agnoFields).forEach((key) => delete agnoFields[key]);
  for (const field of currentConfigFields.value) {
    const value = tool.config ? tool.config[field.key] : undefined;
    agnoFields[field.key] = value === undefined || value === null ? "" : String(value);
  }
  // 已存 config 中不属于声明字段的键 → 归入「自定义参数」
  const declared = new Set(currentConfigFields.value.map((field) => field.key));
  customParams.value = Object.entries(tool.config || {})
    .filter(([key]) => !declared.has(key))
    .map(([key, value]) => ({
      key,
      value: value === null || value === undefined ? "" : String(value),
    }));
  dialog.mode = "agno-config";
  dialog.title = `配置工具：${displayName(tool)}`;
  dialog.visible = true;
}

function addCustomParam() {
  customParams.value.push({ key: "", value: "" });
}

function removeCustomParam(index: number) {
  customParams.value.splice(index, 1);
}

function handleCloseDialog() {
  dialog.visible = false;
  currentTool.value = null;
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

async function handleSubmit() {
  if (dialog.mode === "agno-config") {
    await submitAgnoConfig();
    return;
  }
  await submitHttpForm();
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
    dialog.visible = false;
    await refreshList();
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
  if (!httpForm.url.trim()) {
    ElMessage.warning("请填写请求地址");
    return;
  }
  const headers = buildObjectFromRows(httpForm.headerFields);
  const paramsSchema = paramFieldsToSchema(httpForm.paramFields);
  const payload: any = {
    name: httpForm.name.trim(),
    kind: "http",
    method: httpForm.method,
    url: httpForm.url.trim(),
    headers,
    params_schema: paramsSchema,
    enabled: httpForm.enabled,
  };
  submitLoading.value = true;
  try {
    if (httpForm.id) await updateAiTool(httpForm.id, payload);
    else await createAiTool(payload);
    dialog.visible = false;
    await refreshList();
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

async function handleTestTool(tool: AiToolRow | null) {
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

async function onDelete(tool: AiToolRow) {
  try {
    await ElMessageBox.confirm(`确认删除工具「${tool.name}」?`, "警告", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteAiTool([tool.id]);
    await refreshList();
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

// ---- 工具详情（结构化参数展示） ----
const detailVisible = ref(false);
const detailTool = ref<AiToolRow | null>(null);
const paramsFields = computed(() => {
  const tool = detailTool.value;
  const out: { key: string; type: string; required: boolean; desc: string }[] = [];
  // config_fields（Agno/系统声明字段）
  for (const f of tool?.config_fields || []) {
    out.push({
      key: f.key,
      type: (f as any).type || (f.secret ? "password" : "string"),
      required: !!f.required,
      desc: f.label || "",
    });
  }
  // params_schema（HTTP 入参 JSON Schema）
  const schema = tool?.params_schema as any;
  const props = schema?.properties;
  if (props && typeof props === "object") {
    const required = new Set(schema?.required || []);
    for (const [key, spec] of Object.entries<any>(props)) {
      out.push({
        key,
        type: String(spec?.type || "any"),
        required: required.has(key),
        desc: String(spec?.description || spec?.title || ""),
      });
    }
  }
  return out;
});
function openDetail(tool: AiToolRow | null) {
  if (!tool) return;
  detailTool.value = tool;
  detailVisible.value = true;
}

onMounted(() => {
  refreshList();
});
</script>

<style scoped>
.tool-search {
  margin-bottom: 4px;
}

.tool-batchbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.tool-card__check {
  flex-shrink: 0;
}

.summary-tag {
  margin-left: 4px;
}

.tool-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}

.tool-grid {
  margin-top: 8px;
}

.tool-card {
  margin-bottom: 12px;
}

.tool-card.is-not-ready {
  opacity: 0.6;
}

.tool-card__hd {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.tool-card__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  white-space: nowrap;
}

.tool-card__ready {
  height: auto;
  white-space: normal;
}

.tool-card__body {
  min-height: 44px;
}

.tool-card__group {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tool-card__desc {
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-regular);
}

.tool-card__ft {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tool-card__actions {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

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
.tool-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tool-params__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: var(--el-font-size-base);
}
.tool-params__type {
  color: var(--el-text-color-secondary);
  font-family: var(--el-font-family-mono, monospace);
}
.tool-params__req {
  color: var(--el-color-danger);
  font-size: 12px;
}
.tool-params__desc,
.tool-params__val {
  color: var(--el-text-color-regular);
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
