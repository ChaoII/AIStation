<template>
  <div class="app-container">
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_ai:provider:create']"
          :perm-delete="['module_ai:provider:delete']"
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
            <template #empty><el-empty :image-size="80" description="暂无提供商" /></template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
            <el-table-column label="协议" prop="protocol" width="120" />
            <el-table-column
              label="Base URL"
              prop="base_url"
              min-width="220"
              show-overflow-tooltip
            />
            <el-table-column label="Key" prop="api_key_masked" width="140" />
            <el-table-column label="启用" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="200" align="center">
              <template #default="scope">
                <el-button size="small" link type="primary" @click="handleRemote(scope.row)">
                  拉取模型
                </el-button>
                <el-button
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button size="small" link type="danger" @click="handleRowDelete(scope.row.id)">
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
      width="620px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="formData.name" placeholder="如：opencode / DeepSeek / 本地 Ollama" />
        </el-form-item>
        <el-form-item label="协议">
          <el-select v-model="formData.protocol" style="width: 100%">
            <el-option label="OpenAI 兼容" value="openai" />
            <el-option label="Anthropic 兼容" value="anthropic" />
            <el-option label="Ollama" value="ollama" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input v-model="formData.base_url" placeholder="如：https://opencode.ai/zen/go/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="formData.api_key"
            type="password"
            show-password
            :placeholder="dialogVisible.type === 'update' ? '留空表示不变更' : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="自定义请求头">
          <el-input
            v-model="formData.extra_headers_text"
            type="textarea"
            :rows="2"
            placeholder='可选 JSON，如 {"x-opencode-session":"my-session"}'
          />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="formData.enabled" /></el-form-item>
        <el-form-item label="备注">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <el-dialog v-model="remoteVisible" title="远端模型列表" width="560px">
      <el-empty v-if="!remoteLoading && remoteModels.length === 0" description="无模型或拉取失败" />
      <el-tag v-for="m in remoteModels" :key="m" class="remote-tag" @click="copy(m)">
        {{ m }}
      </el-tag>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import {
  getAiProviderList,
  createAiProvider,
  updateAiProvider,
  deleteAiProvider,
  getRemoteModels,
} from "@/api/module_ai/provider";
import type { IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

const { contentRef } = useCrudList();
const submitLoading = ref(false);
const dataFormRef = ref();

const contentConfig = reactive<IContentConfig<any>>({
  permPrefix: "module_ai:provider",
  pk: "id",
  cols: [] as IContentConfig["cols"],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async () => {
    const res = await getAiProviderList();
    const list = res.data?.data || [];
    return { total: list.length, list };
  },
  deleteAction: async (ids) => {
    await deleteAiProvider(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除所选提供商?", type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const emptyForm = () => ({
  id: undefined as number | undefined,
  name: "",
  protocol: "openai",
  base_url: "",
  api_key: "",
  extra_headers_text: "",
  enabled: true,
  description: undefined as string | undefined,
});
const formData = reactive<any>(emptyForm());

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  Object.assign(formData, emptyForm());
  if (id && type === "update") {
    dialogVisible.title = "编辑提供商";
    const res = await getAiProviderList();
    const item = (res.data?.data || []).find((x: any) => x.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id,
        name: item.name,
        protocol: item.protocol,
        base_url: item.base_url,
        api_key: "",
        extra_headers_text: item.extra_headers ? JSON.stringify(item.extra_headers) : "",
        enabled: item.enabled,
        description: item.description,
      });
    }
  } else {
    dialogVisible.title = "新增提供商";
  }
  dialogVisible.visible = true;
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  Object.assign(formData, emptyForm());
}

async function handleSubmit() {
  if (!formData.name || !formData.base_url) {
    ElMessage.warning("请填写名称与 Base URL");
    return;
  }
  let extra: any;
  if (formData.extra_headers_text?.trim()) {
    try {
      extra = JSON.parse(formData.extra_headers_text);
    } catch {
      ElMessage.error("自定义请求头不是合法 JSON");
      return;
    }
  }
  submitLoading.value = true;
  try {
    const payload: any = {
      name: formData.name,
      protocol: formData.protocol,
      base_url: formData.base_url,
      extra_headers: extra,
      enabled: formData.enabled,
      description: formData.description,
    };
    if (formData.api_key) payload.api_key = formData.api_key;
    if (formData.id) await updateAiProvider(formData.id, payload);
    else await createAiProvider(payload);
    dialogVisible.visible = false;
    contentRef.value?.fetchPageData({}, true);
  } finally {
    submitLoading.value = false;
  }
}

const remoteVisible = ref(false);
const remoteLoading = ref(false);
const remoteModels = ref<string[]>([]);

async function handleRemote(row: any) {
  remoteVisible.value = true;
  remoteLoading.value = true;
  remoteModels.value = [];
  try {
    const res = await getRemoteModels(row.id);
    remoteModels.value = res.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "拉取失败");
  } finally {
    remoteLoading.value = false;
  }
}

function copy(m: string) {
  navigator.clipboard.writeText(m).then(() => ElMessage.success(`已复制 ${m}`));
}
</script>

<style scoped>
.remote-tag {
  margin: 0 6px 6px 0;
  cursor: pointer;
}
</style>
