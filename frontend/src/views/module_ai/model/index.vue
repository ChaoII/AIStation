<template>
  <div class="app-container">
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
          :perm-create="['module_ai:model:create']"
          :perm-delete="['module_ai:model:delete']"
          @add="handleOpenDialog('create')"
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
              <el-empty :image-size="80" description="暂无配置" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="配置名称" prop="name" min-width="140" show-overflow-tooltip />
            <el-table-column label="模型" prop="model" min-width="140" show-overflow-tooltip />
            <el-table-column
              label="API 基址"
              prop="base_url"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column label="Key" prop="api_key_masked" width="140" />
            <el-table-column label="温度" prop="temperature" width="80" align="center" />
            <el-table-column label="默认" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="260" align="center">
              <template #default="scope">
                <el-button size="small" link type="primary" @click="handleTest(scope.row)">
                  测试
                </el-button>
                <el-button
                  size="small"
                  link
                  type="success"
                  :disabled="scope.row.is_default"
                  @click="handleSetDefault(scope.row.id)"
                >
                  设为默认
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:model:update']"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:model:delete']"
                  size="small"
                  link
                  type="danger"
                  @click="handleRowDelete(scope.row.id)"
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
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="640px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px">
        <el-form-item
          label="配置名称"
          prop="name"
          :rules="[{ required: true, message: '请输入配置名称', trigger: 'blur' }]"
        >
          <el-input v-model="formData.name" placeholder="如：DeepSeek 生产" />
        </el-form-item>
        <el-form-item label="提供商">
          <el-select
            v-model="formData.provider_id"
            clearable
            filterable
            style="width: 100%"
            placeholder="选择提供商（可选，留空用自定义地址）"
          >
            <el-option v-for="p in providerOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用途">
          <el-select v-model="formData.usage" style="width: 100%">
            <el-option label="对话/通用" value="chat" />
            <el-option label="助手/工具" value="assistant" />
            <el-option label="向量/Embedding" value="embedding" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
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
            <el-form-item label="能力标签">
              <el-input v-model="formData.capabilities_text" placeholder="chat,tool,vision" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="模型名" prop="model" required>
          <el-input v-model="formData.model" placeholder="如：deepseek-chat" />
        </el-form-item>
        <el-form-item label="API 基址" prop="base_url" required>
          <el-input v-model="formData.base_url" placeholder="如：https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="formData.api_key"
            type="password"
            show-password
            :placeholder="dialogVisible.type === 'update' ? '留空表示不变更' : 'sk-...'"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="温度">
              <el-input-number v-model="formData.temperature" :min="0" :max="2" :step="0.1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大 token">
              <el-input-number v-model="formData.max_tokens" :min="64" :max="32768" :step="128" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="自定义请求头">
          <el-input
            v-model="formData.extra_headers_text"
            type="textarea"
            :rows="2"
            placeholder='可选 JSON，如 {"x-opencode-session":"my-session"}；opencode 网关会自动注入该头'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :loading="testing" @click="handleTestForm">测试连接</el-button>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import {
  getAiModelList,
  createAiModel,
  updateAiModel,
  deleteAiModel,
  setDefaultAiModel,
  testAiModel,
} from "@/api/module_ai/model";
import { getAiProviderList } from "@/api/module_ai/provider";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:model",
  colon: true,
  showNumber: 1,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "配置名称",
      type: "input",
      attrs: { placeholder: "配置名称", clearable: true, style: { width: "200px" } },
    },
  ],
});

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_ai:model",
  pk: "id",
  cols: [] as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAiModelList(params as TablePageQuery);
    const list = res.data?.data || [];
    const keyword = (params as any)?.name;
    const filtered = keyword ? list.filter((x: any) => (x.name || "").includes(keyword)) : list;
    return { total: filtered.length, list: filtered };
  },
  deleteAction: async (ids) => {
    await deleteAiModel(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除所选模型配置?", type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const emptyForm = () => ({
  id: undefined as number | undefined,
  name: "",
  model: "",
  provider_id: undefined as number | undefined,
  usage: "chat",
  capabilities_text: "",
  context_window: undefined as number | undefined,
  base_url: "",
  api_key: "",
  temperature: 0.3,
  max_tokens: 2048,
  enabled: true,
  is_default: false,
  extra_headers_text: "",
  description: undefined as string | undefined,
});
const formData = reactive<any>(emptyForm());

const providerOptions = ref<any[]>([]);
(async () => {
  try {
    const res = await getAiProviderList();
    providerOptions.value = res.data?.data || [];
  } catch {
    providerOptions.value = [];
  }
})();

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  Object.assign(formData, emptyForm());
  if (id && type === "update") {
    dialogVisible.title = "编辑模型配置";
    const res = await getAiModelList();
    const item = (res.data?.data || []).find((x: any) => x.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id,
        name: item.name,
        model: item.model,
        provider_id: item.provider_id,
        usage: item.usage || "chat",
        capabilities_text: (item.capabilities || []).join(","),
        context_window: item.context_window,
        base_url: item.base_url,
        api_key: "",
        temperature: item.temperature,
        max_tokens: item.max_tokens,
        enabled: item.enabled,
        is_default: item.is_default,
        extra_headers_text: item.extra_headers ? JSON.stringify(item.extra_headers) : "",
        description: item.description,
      });
    }
  } else {
    dialogVisible.title = "新增模型配置";
  }
  dialogVisible.visible = true;
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  Object.assign(formData, emptyForm());
}

async function handleSubmit() {
  if (!formData.name || !formData.model || (!formData.base_url && !formData.provider_id)) {
    ElMessage.warning("请填写配置名称、模型名，并选择提供商或填 API 基址");
    return;
  }
  submitLoading.value = true;
  try {
    let extraHeaders: any = undefined;
    if (formData.extra_headers_text && formData.extra_headers_text.trim()) {
      try {
        extraHeaders = JSON.parse(formData.extra_headers_text);
      } catch {
        ElMessage.error("自定义请求头不是合法 JSON");
        submitLoading.value = false;
        return;
      }
    }
    const payload: any = {
      name: formData.name,
      provider: "openai_compatible",
      provider_id: formData.provider_id,
      usage: formData.usage,
      capabilities: formData.capabilities_text
        ? formData.capabilities_text
            .split(",")
            .map((s: string) => s.trim())
            .filter(Boolean)
        : null,
      context_window: formData.context_window,
      model: formData.model,
      base_url: formData.base_url,
      temperature: formData.temperature,
      max_tokens: formData.max_tokens,
      enabled: formData.enabled,
      is_default: formData.is_default,
      extra_headers: extraHeaders,
      description: formData.description,
    };
    if (formData.api_key) payload.api_key = formData.api_key;
    if (formData.id) await updateAiModel(formData.id, payload);
    else await createAiModel(payload);
    dialogVisible.visible = false;
    refreshList();
  } finally {
    submitLoading.value = false;
  }
}

async function handleSetDefault(id: number) {
  await setDefaultAiModel(id);
  refreshList();
}

async function handleTest(row: any) {
  try {
    const res = await testAiModel({ id: row.id });
    ElMessage.success(`连接成功：${res.data?.data?.reply || "ok"}`);
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "连接失败");
  }
}

const testing = ref(false);

// 弹窗内测试：有 Key 用当前表单值；编辑态未改 Key 则用已保存配置
async function handleTestForm() {
  const payload: any = { base_url: formData.base_url, model: formData.model };
  if (formData.extra_headers_text && formData.extra_headers_text.trim()) {
    try {
      payload.extra_headers = JSON.parse(formData.extra_headers_text);
    } catch {
      ElMessage.error("自定义请求头不是合法 JSON");
      return;
    }
  }
  if (formData.api_key) payload.api_key = formData.api_key;
  else if (formData.id) payload.id = formData.id;
  else {
    ElMessage.warning("请先填写 API Key");
    return;
  }
  testing.value = true;
  try {
    const res = await testAiModel(payload);
    ElMessage.success(`连接成功：${res.data?.data?.reply || "ok"}`);
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "连接失败");
  } finally {
    testing.value = false;
  }
}
</script>

<style scoped>
.muted {
  color: var(--el-text-color-placeholder);
}
</style>
