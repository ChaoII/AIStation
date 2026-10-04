<!-- 模型供应商管理：CRUD + 连通性测试 + 拉取远端模型 -->
<template>
  <div class="app-container ai-provider-page">
    <!-- 顶部工具栏 -->
    <div class="provider-toolbar">
      <div>
        <span class="provider-toolbar__hint">
          配置 OpenAI 兼容的模型供应商，供大模型配置关联取用。
        </span>
      </div>
      <el-button
        v-hasPerm="['module_ai:provider:create']"
        type="primary"
        :icon="Plus"
        @click="openCreate"
      >
        新增供应商
      </el-button>
    </div>

    <!-- 列表 -->
    <el-table v-loading="loading" :data="rows" row-key="id" stripe>
      <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="协议" width="160">
        <template #default="{ row }">
          <el-tag size="small">{{ row.protocol || "openai_compatible" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="base_url" label="API 基址" min-width="240" show-overflow-tooltip />
      <el-table-column label="API Key" width="150">
        <template #default="{ row }">{{ row.api_key_masked || "—" }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-switch
            v-hasPerm="['module_ai:provider:update']"
            :model-value="row.enabled !== false"
            @change="(v) => onToggle(row, Boolean(v))"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button
            v-hasPerm="['module_ai:provider:query']"
            text
            type="primary"
            :loading="testingId === row.id"
            @click="onTest(row)"
          >
            测试连通
          </el-button>
          <el-button
            v-hasPerm="['module_ai:provider:query']"
            text
            type="primary"
            :loading="pullingId === row.id"
            @click="onPullModels(row)"
          >
            拉取模型
          </el-button>
          <el-button
            v-hasPerm="['module_ai:provider:update']"
            text
            type="primary"
            @click="openEdit(row)"
          >
            编辑
          </el-button>
          <el-button
            v-hasPerm="['module_ai:provider:delete']"
            text
            type="danger"
            @click="onDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :image-size="80" description="暂无供应商，点击「新增」创建" />
      </template>
    </el-table>

    <!-- 新增 / 编辑弹窗 -->
    <EnhancedDialog
      v-model="dialog.visible"
      :title="dialog.title"
      append-to-body
      width="560px"
      @close="dialog.visible = false"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如 OpenAI / DeepSeek 官方" />
        </el-form-item>
        <el-form-item label="协议">
          <el-input v-model="form.protocol" placeholder="openai_compatible" />
        </el-form-item>
        <el-form-item label="API 基址" required>
          <el-input v-model="form.base_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="isEdit ? '留空表示不修改' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="自定义请求头">
          <div class="header-builder">
            <div v-for="(h, i) in form.headerFields" :key="i" class="header-row">
              <el-input v-model="h.key" placeholder="请求头名，如 x-api-key" />
              <el-input v-model="h.value" placeholder="值" />
              <el-button
                text
                type="danger"
                :icon="Delete"
                @click="form.headerFields.splice(i, 1)"
              />
            </div>
            <el-button
              text
              type="primary"
              :icon="Plus"
              @click="form.headerFields.push({ key: '', value: '' })"
            >
              添加请求头
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- 远端模型 -> 一键导入为模型配置 -->
    <el-dialog
      v-model="pullVisible"
      :title="`远端模型列表 · ${pullProvider?.name || ''}`"
      width="560px"
      append-to-body
    >
      <p class="pull-intro">
        共发现
        <b>{{ pullModels.length }}</b>
        个模型，导入时将作为「模型配置」创建（自动去重）。
      </p>
      <el-form label-width="90px">
        <el-form-item label="用途">
          <el-select v-model="pullUsage" style="width: 100%">
            <el-option label="聊天 chat" value="chat" />
            <el-option label="助手 assistant" value="assistant" />
            <el-option label="嵌入 embedding" value="embedding" />
            <el-option label="语音识别 asr" value="asr" />
            <el-option label="语音合成 tts" value="tts" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-scrollbar max-height="40vh">
        <div class="pull-models">
          <div v-for="m in pullModels" :key="m" class="pull-model-row">{{ m }}</div>
        </div>
      </el-scrollbar>
      <template #footer>
        <el-button @click="pullVisible = false">取消</el-button>
        <el-button type="primary" :loading="pullImporting" @click="onImportModels">
          一键导入为模型配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Delete } from "@element-plus/icons-vue";
import {
  createAiProvider,
  deleteAiProvider,
  getAiProviderList,
  getAiProviderRemoteModels,
  importAiProviderRemoteModels,
  testAiProvider,
  updateAiProvider,
} from "@/api/module_ai/provider";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

defineOptions({ name: "AiProviderManage" });

interface ProviderRow {
  id: number;
  name: string;
  protocol?: string;
  base_url: string;
  api_key_masked: string;
  extra_headers?: Record<string, string> | null;
  enabled?: boolean;
  description?: string | null;
}

const loading = ref(false);
const rows = ref<ProviderRow[]>([]);
const testingId = ref<number | null>(null);
const pullingId = ref<number | null>(null);
const submitLoading = ref(false);

const dialog = reactive({ visible: false, title: "" });
const isEdit = ref(false);
const form = reactive({
  id: undefined as number | undefined,
  name: "",
  protocol: "openai_compatible",
  base_url: "",
  api_key: "",
  headerFields: [] as { key: string; value: string }[],
  enabled: true,
  description: "",
});

async function refreshList() {
  loading.value = true;
  try {
    const res = await getAiProviderList();
    rows.value = (res.data?.data || []) as ProviderRow[];
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  Object.assign(form, {
    id: undefined,
    name: "",
    protocol: "openai_compatible",
    base_url: "",
    api_key: "",
    headerFields: [],
    enabled: true,
    description: "",
  });
}

function openCreate() {
  resetForm();
  isEdit.value = false;
  dialog.title = "新增供应商";
  dialog.visible = true;
}

function openEdit(row: any) {
  resetForm();
  isEdit.value = true;
  dialog.title = `编辑供应商：${row.name}`;
  Object.assign(form, {
    id: row.id,
    name: row.name,
    protocol: row.protocol || "openai_compatible",
    base_url: row.base_url || "",
    api_key: "",
    headerFields: Object.entries(row.extra_headers || {}).map(([k, v]) => ({
      key: k,
      value: String(v),
    })),
    enabled: row.enabled !== false,
    description: row.description || "",
  });
  dialog.visible = true;
}

function buildHeaders(): Record<string, string> | undefined {
  const out: Record<string, string> = {};
  for (const r of form.headerFields || []) {
    const k = (r.key || "").trim();
    if (!k) continue;
    out[k] = r.value;
  }
  return Object.keys(out).length ? out : undefined;
}

async function handleSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写供应商名称");
    return;
  }
  if (!form.base_url.trim()) {
    ElMessage.warning("请填写 API 基址");
    return;
  }
  const headers = buildHeaders();
  const payload: any = {
    name: form.name.trim(),
    protocol: form.protocol || "openai_compatible",
    base_url: form.base_url.trim(),
    api_key: form.api_key || undefined,
    extra_headers: headers || null,
    enabled: form.enabled,
    description: form.description || null,
  };
  submitLoading.value = true;
  try {
    if (form.id) await updateAiProvider(form.id, payload);
    else await createAiProvider(payload);
    dialog.visible = false;
    await refreshList();
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

async function onTest(row: any) {
  testingId.value = row.id;
  try {
    const res = await testAiProvider(row.id);
    const result = res.data?.data || {};
    if (result.ok) ElMessage.success(result.message || "连接成功");
    else ElMessage.error(result.message || "连接失败");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "测试失败");
  } finally {
    testingId.value = null;
  }
}

async function onPullModels(row: any) {
  pullingId.value = row.id;
  try {
    const res = await getAiProviderRemoteModels(row.id);
    const models = (res.data?.data || []) as string[];
    if (!models.length) {
      ElMessage.warning("未拉取到模型，请检查供应商连通与鉴权");
    } else {
      pullProvider.value = row;
      pullModels.value = models;
      pullUsage.value = "chat";
      pullVisible.value = true;
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "拉取失败");
  } finally {
    pullingId.value = null;
  }
}

const pullVisible = ref(false);
const pullProvider = ref<any>(null);
const pullModels = ref<string[]>([]);
const pullUsage = ref("chat");
const pullImporting = ref(false);
async function onImportModels() {
  if (!pullProvider.value) return;
  pullImporting.value = true;
  try {
    const r = await importAiProviderRemoteModels(pullProvider.value.id, pullUsage.value);
    const d = r.data?.data || {};
    ElMessage.success(
      `已导入 ${d.imported} 个模型${d.skipped ? `，跳过 ${d.skipped} 个已存在` : ""}`
    );
    pullVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "导入失败");
  } finally {
    pullImporting.value = false;
  }
}

async function onToggle(row: any, enabled: boolean) {
  try {
    await updateAiProvider(row.id, { enabled });
    row.enabled = enabled;
    ElMessage.success(enabled ? "已启用" : "已停用");
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}

async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除供应商「${row.name}」？删除后关联此供应商的模型配置将无法自动取用其 base_url/Key，且不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await deleteAiProvider([row.id]);
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
.ai-provider-page {
  padding: 0;
}

.pull-intro {
  margin: 0 0 12px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.pull-models {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.pull-model-row {
  padding: 8px 12px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}
.pull-model-row:last-child {
  border-bottom: none;
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

.provider-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.provider-toolbar__hint {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-secondary);
}
</style>
