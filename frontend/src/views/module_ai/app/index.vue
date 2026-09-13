<!-- AI 应用：模型+提示词+工具集+输出格式+入参，一键运行 -->
<template>
  <div class="app-container ai-app-page">
    <el-card shadow="never" class="app-card">
      <div class="toolbar">
        <el-button v-hasPerm="['module_ai:app:create']" type="primary" @click="handleOpenDialog()">
          新增应用
        </el-button>
        <el-button @click="refreshList">刷新</el-button>
      </div>

      <el-table v-loading="loading" :data="list" row-key="id" border stripe>
        <template #empty>
          <el-empty :image-size="80" description="暂无 AI 应用" />
        </template>
        <el-table-column label="图标" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.icon"><component :is="row.icon" /></el-icon>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
        <el-table-column label="描述" prop="description" min-width="180" show-overflow-tooltip />
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
        <el-table-column label="操作" fixed="right" width="200" align="center">
          <template #default="{ row }">
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
              v-hasPerm="['module_ai:app:delete']"
              size="small"
              link
              type="danger"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

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
        <el-form-item label="入参 JSON">
          <el-input
            v-model="formData.input_schema_text"
            type="textarea"
            :rows="4"
            placeholder='可选，如 {"type":"object","properties":{"question":{"type":"string"}}}'
          />
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { createAiApp, deleteAiApp, getAiAppList, updateAiApp } from "@/api/module_ai/app";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

defineOptions({ name: "AiApp" });

interface AppRow {
  id: number;
  name: string;
  icon: string;
  description: string | null;
  model_id: number | null;
  prompt_id: number | null;
  tools: string[];
  output_format: string;
  input_schema: Record<string, any> | null;
  enabled: boolean;
  order: number;
}

const router = useRouter();

const loading = ref(false);
const list = ref<AppRow[]>([]);
const modelOptions = ref<any[]>([]);
const promptOptions = ref<any[]>([]);
const toolOptions = ref<any[]>([]);

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
  order: 0,
  enabled: true,
});

const formData = reactive(emptyForm());

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

async function loadOptions() {
  try {
    const [models, prompts, tools] = await Promise.all([
      getAiModelList(),
      getAiPromptList(),
      getAiToolList(),
    ]);
    modelOptions.value = models.data?.data || [];
    promptOptions.value = prompts.data?.data || [];
    toolOptions.value = (tools.data?.data || []).filter((t: any) => t.enabled);
  } catch {
    // 选项加载失败不阻断列表展示
  }
}

async function refreshList() {
  loading.value = true;
  try {
    const res = await getAiAppList();
    list.value = res.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    loading.value = false;
  }
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
    formData.input_schema_text = row.input_schema ? JSON.stringify(row.input_schema, null, 2) : "";
    formData.order = row.order ?? 0;
    formData.enabled = row.enabled !== false;
  } else {
    dialogTitle.value = "新增应用";
  }
  dialogVisible.value = true;
}

function handleCloseDialog() {
  dialogVisible.value = false;
  Object.assign(formData, emptyForm());
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
  if (!formData.name.trim()) {
    ElMessage.warning("请填写名称");
    return;
  }
  let inputSchema: Record<string, any> | undefined;
  try {
    inputSchema = parseJson(formData.input_schema_text);
  } catch (e: any) {
    ElMessage.error(`入参 JSON 解析失败：${e?.message || e}`);
    return;
  }
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
  };
  submitLoading.value = true;
  try {
    if (formData.id) await updateAiApp(formData.id, payload);
    else await createAiApp(payload);
    dialogVisible.value = false;
    await refreshList();
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除应用「${row.name}」?`, "警告", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteAiApp([row.id]);
    await refreshList();
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

function handleRun(row: any) {
  router.push({ path: "/ai/playground", query: { app_id: String(row.id) } });
}

onMounted(() => {
  loadOptions();
  refreshList();
});
</script>

<style scoped>
.ai-app-page {
  flex-shrink: 0;
}

.app-card {
  flex-shrink: 0;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
