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

    <!-- 工具卡片网格 -->
    <el-row v-loading="loading" :gutter="12" class="tool-grid">
      <el-col v-for="tool in filteredTools" :key="tool.id" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card
          shadow="hover"
          class="tool-card"
          :class="{ 'is-not-ready': !tool.ready }"
          data-testid="tool-card"
        >
          <template #header>
            <div class="tool-card__hd">
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
        <el-empty :image-size="80" description="暂无工具" />
      </el-col>
    </el-row>

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
        <el-form-item label="请求头 JSON">
          <el-input
            v-model="httpForm.headers_text"
            type="textarea"
            :rows="2"
            placeholder='可选，如 {"Authorization":"Bearer xxx"}'
          />
        </el-form-item>
        <el-form-item label="入参 JSON Schema">
          <el-input
            v-model="httpForm.params_schema_text"
            type="textarea"
            :rows="4"
            placeholder='如 {"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}'
          />
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Component } from "vue";
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
  params_schema_text: "",
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
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function onToggle(tool: AiToolRow, enabled: boolean) {
  if (!tool.ready) return;
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
    params_schema_text: "",
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
    headers_text: tool.headers ? JSON.stringify(tool.headers, null, 2) : "",
    params_schema_text: tool.params_schema ? JSON.stringify(tool.params_schema, null, 2) : "",
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

function parseJson(text: string): Record<string, any> | undefined {
  const trimmed = (text || "").trim();
  if (!trimmed) return undefined;
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("必须是 JSON 对象");
  }
  return parsed;
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
  let headers: Record<string, any> | undefined;
  let paramsSchema: Record<string, any> | undefined;
  try {
    headers = parseJson(httpForm.headers_text);
    paramsSchema = parseJson(httpForm.params_schema_text);
  } catch (e: any) {
    ElMessage.error(`JSON 解析失败：${e?.message || e}`);
    return;
  }
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

onMounted(() => {
  refreshList();
});
</script>

<style scoped>
.tool-search {
  margin-bottom: 4px;
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
  font-size: 13px;
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
</style>
