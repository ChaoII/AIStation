<!-- AI 工具中心：内置工具开关 + 自定义 HTTP 工具 CRUD -->
<template>
  <div class="app-container ai-tool-page">
    <el-card shadow="never" class="tool-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="内置工具" name="builtin">
          <el-table v-loading="loading" :data="builtinList" row-key="id" border stripe>
            <template #empty>
              <el-empty :image-size="80" description="暂无内置工具" />
            </template>
            <el-table-column label="工具名" prop="name" min-width="260" show-overflow-tooltip />
            <el-table-column label="类型" width="110" align="center">
              <template #default>
                <el-tag size="small" type="info">内置</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="120" align="center">
              <template #default="{ row }">
                <span v-hasPerm="['module_ai:tool:update']">
                  <el-switch
                    :model-value="row.enabled"
                    @change="(val) => handleToggle(row, Boolean(val))"
                  />
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="自定义 HTTP 工具" name="http">
          <div class="toolbar">
            <el-button
              v-hasPerm="['module_ai:tool:create']"
              type="primary"
              @click="handleOpenDialog()"
            >
              新增工具
            </el-button>
            <el-button @click="refreshList">刷新</el-button>
          </div>
          <el-table v-loading="loading" :data="httpList" row-key="id" border stripe>
            <template #empty>
              <el-empty :image-size="80" description="暂无自定义 HTTP 工具" />
            </template>
            <el-table-column label="工具名" prop="name" min-width="180" show-overflow-tooltip />
            <el-table-column label="方法" prop="method" width="90" align="center" />
            <el-table-column label="请求地址" prop="url" min-width="260" show-overflow-tooltip />
            <el-table-column label="启用" width="100" align="center">
              <template #default="{ row }">
                <span v-hasPerm="['module_ai:tool:update']">
                  <el-switch
                    :model-value="row.enabled"
                    @change="(val) => handleToggle(row, Boolean(val))"
                  />
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="200" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:tool:update']"
                  size="small"
                  link
                  type="primary"
                  @click="handleTest(row)"
                >
                  测试
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:tool:update']"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:tool:delete']"
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
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <EnhancedDialog
      v-model="dialogVisible"
      :title="dialogTitle"
      append-to-body
      width="640px"
      @close="handleCloseDialog"
    >
      <el-form ref="formRef" :model="formData" label-width="120px">
        <el-form-item label="工具名" required>
          <el-input v-model="formData.name" placeholder="唯一名称，供模型调用" />
        </el-form-item>
        <el-form-item label="请求方法">
          <el-select v-model="formData.method" style="width: 100%">
            <el-option label="GET" value="GET" />
            <el-option label="POST" value="POST" />
          </el-select>
        </el-form-item>
        <el-form-item label="请求地址" required>
          <el-input
            v-model="formData.url"
            placeholder="如 https://api.example.com/items/{id}，{id} 会被入参替换"
          />
        </el-form-item>
        <el-form-item label="请求头 JSON">
          <el-input
            v-model="formData.headers_text"
            type="textarea"
            :rows="2"
            placeholder='可选，如 {"Authorization":"Bearer xxx"}'
          />
        </el-form-item>
        <el-form-item label="入参 JSON Schema">
          <el-input
            v-model="formData.params_schema_text"
            type="textarea"
            :rows="4"
            placeholder='如 {"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}'
          />
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
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createAiTool,
  deleteAiTool,
  getAiToolList,
  testAiTool,
  toggleAiTool,
  updateAiTool,
} from "@/api/module_ai/tool";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

defineOptions({ name: "AiTool" });

interface ToolRow {
  id: number;
  name: string;
  kind: string;
  method: string;
  url: string;
  headers: Record<string, any> | null;
  params_schema: Record<string, any> | null;
  enabled: boolean;
}

const activeTab = ref("builtin");
const loading = ref(false);
const builtinList = ref<ToolRow[]>([]);
const httpList = ref<ToolRow[]>([]);

const dialogVisible = ref(false);
const dialogTitle = ref("新增工具");
const submitLoading = ref(false);
const formRef = ref();

const emptyForm = () => ({
  id: undefined as number | undefined,
  name: "",
  method: "GET",
  url: "",
  headers_text: "",
  params_schema_text: "",
  enabled: true,
});

const formData = reactive(emptyForm());

async function refreshList() {
  loading.value = true;
  try {
    const res = await getAiToolList();
    const list: ToolRow[] = res.data?.data || [];
    builtinList.value = list.filter((x) => (x.kind || "builtin") === "builtin");
    httpList.value = list.filter((x) => x.kind === "http");
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleToggle(row: any, enabled: boolean) {
  const prev = row.enabled;
  row.enabled = enabled;
  try {
    await toggleAiTool(row.id, enabled);
    ElMessage.success(enabled ? "已启用" : "已停用");
  } catch (e: any) {
    row.enabled = prev;
    ElMessage.error(e?.msg || "操作失败");
  }
}

function handleOpenDialog(row?: any) {
  Object.assign(formData, emptyForm());
  if (row) {
    dialogTitle.value = "编辑工具";
    formData.id = row.id;
    formData.name = row.name;
    formData.method = row.method || "GET";
    formData.url = row.url || "";
    formData.headers_text = row.headers ? JSON.stringify(row.headers, null, 2) : "";
    formData.params_schema_text = row.params_schema
      ? JSON.stringify(row.params_schema, null, 2)
      : "";
    formData.enabled = row.enabled !== false;
  } else {
    dialogTitle.value = "新增工具";
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
    ElMessage.warning("请填写工具名");
    return;
  }
  if (!formData.url.trim()) {
    ElMessage.warning("请填写请求地址");
    return;
  }
  let headers: Record<string, any> | undefined;
  let paramsSchema: Record<string, any> | undefined;
  try {
    headers = parseJson(formData.headers_text);
    paramsSchema = parseJson(formData.params_schema_text);
  } catch (e: any) {
    ElMessage.error(`JSON 解析失败：${e?.message || e}`);
    return;
  }
  const payload: any = {
    name: formData.name.trim(),
    kind: "http",
    method: formData.method,
    url: formData.url.trim(),
    headers,
    params_schema: paramsSchema,
    enabled: formData.enabled,
  };
  submitLoading.value = true;
  try {
    if (formData.id) await updateAiTool(formData.id, payload);
    else await createAiTool(payload);
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
    await ElMessageBox.confirm(`确认删除工具「${row.name}」?`, "警告", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteAiTool([row.id]);
    await refreshList();
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

async function handleTest(row: any) {
  try {
    const res = await testAiTool(row.id);
    ElMessage.success(res.data?.data?.result !== undefined ? "测试完成" : "测试成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "测试失败");
  }
}

onMounted(() => {
  refreshList();
});
</script>

<style scoped>
.ai-tool-page {
  flex-shrink: 0;
}

.tool-card {
  flex-shrink: 0;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
