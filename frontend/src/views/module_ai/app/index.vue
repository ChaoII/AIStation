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

onMounted(() => {
  loadOptions();
});
</script>

<style scoped>
.ai-app-page {
  flex-shrink: 0;
}
</style>
