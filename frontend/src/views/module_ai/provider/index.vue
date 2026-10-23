<!-- 模型供应商管理：CRUD + 连通性测试 + 拉取远端模型 -->
<template>
  <div class="app-container ai-provider-page">
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
          :perm-create="['module_ai:provider:create']"
          :perm-delete="['module_ai:provider:delete']"
          @add="openCreate"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <span class="batch-ac">
            <el-badge
              :value="providerSelIds.length"
              :hidden="!providerSelIds.length"
              class="batch-badge"
            >
              <el-button size="small" :disabled="!providerSelIds.length" @click="batchProvider(true)">
                批量启用
              </el-button>
            </el-badge>
            <el-badge
              :value="providerSelIds.length"
              :hidden="!providerSelIds.length"
              class="batch-badge"
            >
              <el-button size="small" :disabled="!providerSelIds.length" @click="batchProvider(false)">
                批量停用
              </el-button>
            </el-badge>
          </span>
          <el-tag size="small" type="info" effect="plain" class="summary-tag">
            共 <b>{{ summary.total }}</b> 个供应商 · 启用 <b>{{ summary.enabled }}</b> · 停用
            <b>{{ summary.disabled }}</b>
          </el-tag>
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            border
            :data="data"
            row-key="id"
            stripe
            height="100%"
            @selection-change="(sel: any[]) => (providerSelIds = sel.map((s) => s.id))"
          >
            <el-table-column type="selection" width="45" />
            <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
            <el-table-column label="协议" width="160">
              <template #default="{ row }">
                <el-tag size="small">{{ row.protocol || "openai_compatible" }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="base_url"
              label="API 基址"
              min-width="240"
              show-overflow-tooltip
            />
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
            <el-table-column label="操作" min-width="200" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:provider:query']"
                  icon="View"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  详情
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:provider:query']"
                  icon="Connection"
                  link
                  type="primary"
                  :loading="testingId === row.id"
                  @click="onTest(row)"
                >
                  测试
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:provider:update']"
                  icon="edit"
                  link
                  type="primary"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => onMoreCmd(row, cmd)">
                  <el-button link type="primary" icon="MoreFilled" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-if="perm('module_ai:provider:query')"
                        command="pull"
                        icon="Download"
                      >
                        拉取模型
                      </el-dropdown-item>
                      <el-dropdown-item
                        v-if="perm('module_ai:provider:delete')"
                        command="delete"
                        icon="delete"
                        divided
                        style="color: var(--el-color-danger)"
                      >
                        删除
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="暂无供应商，点击「新增」创建" />
            </template>
          </el-table>
        </div>
      </template>
    </PageContent>

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
              <el-button text type="danger" icon="delete" @click="form.headerFields.splice(i, 1)" />
            </div>
            <el-button
              text
              type="primary"
              icon="plus"
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
      width="600px"
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

    <!-- 供应商详情抽屉 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || '供应商详情'"
      size="480px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="协议">
          <el-tag size="small">{{ detail.protocol || "openai_compatible" }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="API 基址">{{ detail.base_url || "—" }}</el-descriptions-item>
        <el-descriptions-item label="API Key">
          {{ detail.api_key_masked || "—" }}
        </el-descriptions-item>
        <el-descriptions-item label="自定义请求头">
          <template v-if="detail.extra_headers && Object.keys(detail.extra_headers).length">
            <el-tag
              v-for="(v, k) in detail.extra_headers"
              :key="k"
              size="small"
              effect="plain"
              type="info"
              class="cap-tag"
            >
              {{ k }}={{ v }}
            </el-tag>
          </template>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="启用">
          <el-tag :type="detail.enabled !== false ? 'success' : 'info'" size="small">
            {{ detail.enabled !== false ? "启用" : "停用" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ detail.description || "—" }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ detail.created_time || "—" }}
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createAiProvider,
  deleteAiProvider,
  getAiProviderList,
  getAiProviderRemoteModels,
  importAiProviderRemoteModels,
  batchProviderStatus,
  testAiProvider,
  updateAiProvider,
} from "@/api/module_ai/provider";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { usePerm } from "@/composables/usePerm";

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
  created_time?: string;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const perm = usePerm();

const loading = ref(false);
const rows = ref<ProviderRow[]>([]);
const providerSelIds = ref<number[]>([]);

// 列表统计摘要（工具栏展示）
const summary = computed(() => ({
  total: rows.value.length,
  enabled: rows.value.filter((r) => r.enabled !== false).length,
  disabled: rows.value.filter((r) => r.enabled === false).length,
}));

/** 加载全量供应商（数据量小：客户端过滤 + 分页，与模型配置页一致） */
async function loadProviders() {
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

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:provider",
  colon: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "keyword",
      label: "关键字",
      type: "input",
      attrs: { placeholder: "名称 / API 基址", clearable: true, style: { width: "200px" } },
    },
    {
      prop: "protocol",
      label: "协议",
      type: "select",
      options: [
        { label: "openai", value: "openai" },
        { label: "OpenAI 兼容", value: "openai_compatible" },
        { label: "ollama", value: "ollama" },
        { label: "anthropic", value: "anthropic" },
      ],
      attrs: { placeholder: "全部", clearable: true, style: { width: "160px" } },
    },
    {
      prop: "enabled",
      label: "状态",
      type: "select",
      options: [
        { label: "启用", value: "true" },
        { label: "停用", value: "false" },
      ],
      attrs: { placeholder: "全部", clearable: true, style: { width: "140px" } },
    },
  ],
});

const contentConfig = reactive<IContentConfig<any>>({
  permPrefix: "module_ai:provider",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    await loadProviders();
    const q = params as any;
    const keyword = String(q.keyword || "")
      .trim()
      .toLowerCase();
    const protocol = String(q.protocol || "").trim();
    const enabled = String(q.enabled ?? "");
    const list = rows.value.filter((r) => {
      if (protocol && (r.protocol || "openai_compatible") !== protocol) return false;
      if (enabled && String(r.enabled !== false) !== enabled) return false;
      if (keyword) {
        const haystack = [r.name, r.base_url, r.description]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }
      return true;
    });
    const pageNo = Number(q.page_no) || 1;
    const size = Number(q.page_size) || 10;
    return { total: list.length, list: list.slice((pageNo - 1) * size, pageNo * size) };
  },
  deleteAction: async (ids) => {
    await deleteAiProvider(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: "警告",
    message: "确认删除所选供应商？删除后其下模型配置将不可用。",
    type: "warning",
  },
});

async function batchProvider(enabled: boolean) {
  if (!providerSelIds.value.length) return;
  try {
    const r = await batchProviderStatus(providerSelIds.value, enabled);
    ElMessage.success(`已${enabled ? "启用" : "停用"} ${r.data?.data?.count || 0} 个供应商`);
    await refreshList();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
}
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

function onMoreCmd(row: any, cmd: string) {
  if (cmd === "pull") {
    onPullModels(row);
  } else if (cmd === "delete") {
    onDelete(row);
  }
}

// ---- 详情抽屉 ----
const detailVisible = ref(false);
const detail = ref<ProviderRow | null>(null);
function openDetail(row: any) {
  detail.value = row;
  detailVisible.value = true;
}

onMounted(() => {
  refreshList();
});
</script>

<style scoped>
.ai-provider-page {
  /* 继承 .app-container 的 16px padding（此前 padding:0 让内容紧贴侧边栏） */
  padding: 16px;
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
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.pull-model-row:last-child {
  border-bottom: none;
}
.header-builder {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}
.header-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.summary-tag {
  flex-shrink: 0;
}

.cap-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.muted {
  color: var(--el-text-color-placeholder);
}
</style>

<!-- 布局统一（非 scoped + 唯一类名）：页面撑满；工具栏批量操作按钮成组 -->
<style lang="scss">
.app-container.ai-provider-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.ai-provider-page .batch-ac {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
</style>
