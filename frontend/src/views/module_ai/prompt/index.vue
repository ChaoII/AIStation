<!-- AI 提示词：列表（上搜索/下列表）+ 全屏画布弹窗（左块列表可拖拽 / 中块编辑 / 右变量与预览） -->
<template>
  <div class="app-container ai-prompt-page">
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
          :perm-create="['module_ai:prompt:create']"
          :perm-delete="['module_ai:prompt:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <el-dropdown v-if="templates.length" style="margin-left: 8px" @command="createFromTemplate">
          <el-button size="small">
            {{ t("ai_workflow.prompt_createFromTemplate") }}
            <el-icon style="margin-left: 4px"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="t in templates" :key="t.key" :command="t">
                {{ t.name }}（{{ t.category }}）
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="batch-ac">
          <el-button size="small" :disabled="!promptSelIds.length" @click="batchPrompt(true)">
            {{ t("ai_workflow.prompt_batchEnable") }}
          </el-button>
          <el-button size="small" :disabled="!promptSelIds.length" @click="batchPrompt(false)">
            {{ t("ai_workflow.prompt_batchDisable") }}
          </el-button>
        </span>
        <el-tag size="small" type="info" effect="plain" class="summary-tag">
          {{
            t("ai_workflow.prompt_summary", {
              total: promptSummary.total,
              enabled: promptSummary.enabled,
              disabled: promptSummary.disabled,
            })
          }}
        </el-tag>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onPromptSel"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.prompt_noData')" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column
              :label="t('ai_workflow.prompt_name')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('ai_workflow.prompt_category')"
              prop="category"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.category || "—" }}</template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.prompt_version')"
              prop="version"
              width="80"
              align="center"
            >
              <template #default="{ row }">v{{ row.version ?? 1 }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.prompt_enabled')" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{
                    row.enabled
                      ? t("ai_workflow.prompt_enabledText")
                      : t("ai_workflow.prompt_disabledText")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.prompt_action')"
              fixed="right"
              width="230"
              align="center"
            >
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:prompt:query']"
                  icon="View"
                  size="small"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  {{ t("ai_workflow.prompt_detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:update']"
                  icon="edit"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', row.id)"
                >
                  {{ t("ai_workflow.prompt_edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:create']"
                  icon="CopyDocument"
                  size="small"
                  link
                  @click="doCopy(row)"
                >
                  {{ t("ai_workflow.prompt_copy") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:delete']"
                  icon="delete"
                  size="small"
                  link
                  type="danger"
                  @click="handleRowDelete(row.id)"
                >
                  {{ t("ai_workflow.prompt_delete") }}
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
      fullscreen
      append-to-body
      @close="handleCloseDialog"
    >
      <!-- 编辑区：顶部信息条 + 左块导航 / 中主编辑 / 右助手面板 -->
      <div class="prompt-editor">
        <!-- 顶部信息条：名称 / 分类 / 启用 -->
        <div class="prompt-editor__meta">
          <el-input
            v-model="form.name"
            :placeholder="t('ai_workflow.prompt_namePlaceholder')"
            clearable
            class="prompt-editor__name"
          />
          <el-input
            v-model="form.category"
            :placeholder="t('ai_workflow.prompt_categoryPlaceholder')"
            clearable
            class="prompt-editor__category"
          />
          <div class="prompt-editor__enabled">
            <span>{{ t("ai_workflow.prompt_enabled") }}</span>
            <el-switch v-model="form.enabled" />
          </div>
        </div>

        <div class="prompt-editor__body">
          <!-- 左：块导航（排序 / 增删 / 选中） -->
          <div class="prompt-editor__nav">
            <div class="prompt-editor__nav-head">
              <span>{{ t("ai_workflow.prompt_blocksLabel") }}</span>
              <el-tag size="small" effect="plain">{{ form.blocks.length }}</el-tag>
            </div>
            <div class="prompt-editor__nav-list">
              <draggable
                v-model="form.blocks"
                item-key="key"
                handle=".drag-handle"
                :animation="150"
                ghost-class="block-item--ghost"
              >
                <template #item="{ element, index }">
                  <div
                    class="nav-item"
                    :class="{ 'nav-item--active': index === activeIndex }"
                    @click="activeIndex = index"
                  >
                    <span class="drag-handle">⠿</span>
                    <el-tag size="small" effect="plain" class="nav-item__tag">
                      {{ typeLabel(element.type) }}
                    </el-tag>
                    <span class="nav-item__preview">
                      {{ element.content || t("ai_workflow.prompt_emptyBlock") }}
                    </span>
                    <el-button
                      v-hasPerm="['module_ai:prompt:update']"
                      link
                      type="danger"
                      size="small"
                      class="nav-item__del"
                      @click.stop="removeBlock(index)"
                    >
                      {{ t("ai_workflow.prompt_del") }}
                    </el-button>
                  </div>
                </template>
              </draggable>
              <el-empty
                v-if="!form.blocks.length"
                :image-size="40"
                :description="t('ai_workflow.prompt_noBlocks')"
              />
            </div>
            <div class="prompt-editor__add">
              <el-select v-model="newBlockType" class="prompt-editor__add-select">
                <el-option
                  v-for="opt in blockTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-button
                v-hasPerm="['module_ai:prompt:update']"
                type="primary"
                plain
                @click="addBlock"
              >
                {{ t("ai_workflow.prompt_addBlock") }}
              </el-button>
            </div>
          </div>

          <!-- 中：主编辑区（编辑当前选中块） -->
          <div class="prompt-editor__main">
            <template v-if="currentBlock">
              <div class="prompt-editor__main-head">
                <div class="prompt-editor__main-title">
                  <el-tag size="small">{{ typeLabel(currentBlock.type) }}</el-tag>
                  <span class="prompt-editor__index">
                    {{
                      t("ai_workflow.prompt_blockIndex", {
                        index: activeIndex + 1,
                        total: form.blocks.length,
                      })
                    }}
                  </span>
                </div>
                <el-select
                  v-model="currentBlock.type"
                  size="small"
                  class="prompt-editor__type-select"
                >
                  <el-option
                    v-for="opt in blockTypeOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </div>
              <el-input
                v-model="currentBlock.content"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 24 }"
                :placeholder="
                  t('ai_workflow.prompt_contentPlaceholder', { type: typeLabel(currentBlock.type) })
                "
                class="prompt-editor__textarea"
              />
              <div class="prompt-editor__hint">
                <el-text size="small" type="info">
                  {{ t("ai_workflow.prompt_hintPrefix") }}
                  <code>&#123;&#123;变量名&#125;&#125;</code>
                  {{ t("ai_workflow.prompt_hintSuffix") }}
                </el-text>
              </div>
            </template>
            <el-empty v-else :image-size="60" :description="t('ai_workflow.prompt_noBlocksMain')" />
          </div>

          <!-- 右：助手面板（变量 / 预览） -->
          <div class="prompt-editor__aside">
            <el-tabs v-model="asideTab">
              <el-tab-pane :label="t('ai_workflow.prompt_varsTab')" name="vars">
                <el-empty
                  v-if="!detectedVariables.length"
                  :image-size="50"
                  :description="t('ai_workflow.prompt_noVars')"
                />
                <div v-for="name in detectedVariables" :key="name" class="var-row">
                  <el-tag size="small">{{ name }}</el-tag>
                  <el-input
                    v-model="variableValues[name]"
                    size="small"
                    :placeholder="t('ai_workflow.prompt_exampleValue')"
                    class="var-row__input"
                  />
                </div>
                <el-text v-if="!detectedVariables.length" size="small" type="info" class="var-tip">
                  {{ t("ai_workflow.prompt_varTipPrefix") }}
                  <code>&#123;&#123;变量名&#125;&#125;</code>
                  {{ t("ai_workflow.prompt_varTipSuffix") }}
                </el-text>
              </el-tab-pane>
              <el-tab-pane :label="t('ai_workflow.prompt_previewTab')" name="preview">
                <div v-if="preview" class="preview" v-html="renderMd(preview)"></div>
                <div v-else class="preview muted">{{ t("ai_workflow.prompt_noContent") }}</div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="handleCloseDialog">{{ t("ai_workflow.prompt_cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ t("ai_workflow.prompt_save") }}
        </el-button>
      </template>
    </EnhancedDialog>

    <!-- 提示词详情预览抽屉 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || t('ai_workflow.prompt_detailTitle')"
      size="480px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item :label="t('ai_workflow.prompt_name')">
          {{ detail.name }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.prompt_category')">
          {{ detail.category || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.prompt_version')">
          v{{ detail.version ?? 1 }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.prompt_enabled')">
          <el-tag :type="detail.enabled ? 'success' : 'info'" size="small">
            {{
              detail.enabled
                ? t("ai_workflow.prompt_enabledText")
                : t("ai_workflow.prompt_disabledText")
            }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.prompt_variables')">
          <template v-if="(detail.variables || []).length">
            <el-tag
              v-for="v in detail.variables"
              :key="v"
              size="small"
              effect="plain"
              class="cap-tag"
            >
              {{ v }}
            </el-tag>
          </template>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.prompt_content')" :span="1">
          <div v-if="(detail.blocks || []).length" class="prompt-block-list">
            <div v-for="(b, i) in detail.blocks" :key="i" class="prompt-block">
              <div class="prompt-block__head">
                <el-tag size="small" effect="plain">{{ typeLabel(b.type) }}</el-tag>
              </div>
              <div class="prompt-block__body" v-html="renderMd(b.content || '')"></div>
            </div>
          </div>
          <span v-else class="muted">—</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ArrowDown } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import draggable from "vuedraggable";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import MarkdownIt from "markdown-it";
import {
  createAiPrompt,
  deleteAiPrompt,
  getAiPromptDetail,
  getAiPromptList,
  updateAiPrompt,
  batchPromptStatus,
  getAiPromptTemplates,
  createAiPromptFromTemplate,
} from "@/api/module_ai/prompt";

defineOptions({ name: "AiPrompt" });

const { t } = useI18n();

interface PromptBlock {
  key: string;
  type: string;
  content: string;
}

const blockTypeOptions = [
  { label: t("ai_workflow.prompt_systemOption"), value: "system" },
  { label: t("ai_workflow.prompt_contextOption"), value: "context" },
  { label: t("ai_workflow.prompt_instructionOption"), value: "instruction" },
  { label: t("ai_workflow.prompt_exampleOption"), value: "example" },
  { label: t("ai_workflow.prompt_outputOption"), value: "output" },
];

const blockTypeLabels: Record<string, string> = {
  system: t("ai_workflow.prompt_system"),
  context: t("ai_workflow.prompt_context"),
  instruction: t("ai_workflow.prompt_instruction"),
  example: t("ai_workflow.prompt_example"),
  output: t("ai_workflow.prompt_output"),
};

function typeLabel(type: string): string {
  return blockTypeLabels[type] || type;
}

let seq = 0;
function uid(): string {
  seq += 1;
  return `${Date.now()}-${seq}`;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:prompt",
  colon: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("ai_workflow.prompt_name"),
      type: "input",
      attrs: {
        placeholder: t("ai_workflow.prompt_searchNamePlaceholder"),
        clearable: true,
        style: { width: "200px" },
      },
    },
    {
      prop: "category",
      label: t("ai_workflow.prompt_category"),
      type: "input",
      attrs: {
        placeholder: t("ai_workflow.prompt_category"),
        clearable: true,
        style: { width: "200px" },
      },
    },
  ],
});

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:prompt",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: false,
  indexAction: async (params) => {
    const res = await getAiPromptList();
    const list = res.data?.data || [];
    const name = (params as any)?.name;
    const category = (params as any)?.category;
    if (!name && !category) return list;
    return list.filter(
      (x: any) =>
        (!name || (x.name || "").includes(name)) &&
        (!category || (x.category || "").includes(category))
    );
  },
  deleteAction: async (ids) => {
    await deleteAiPrompt(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { type: "warning" },
});

const dialogVisible = ref(false);
const dialogTitle = ref(t("ai_workflow.prompt_createTitle"));
const currentId = ref<number | undefined>(undefined);
const activeIndex = ref(0);
const newBlockType = ref("instruction");
const asideTab = ref("vars");
const saving = ref(false);

const form = reactive({
  name: "",
  category: "",
  enabled: true,
  blocks: [] as PromptBlock[],
});

/** 当前选中块（左导航 → 中栏主编辑区联动） */
const currentBlock = computed(() => form.blocks[activeIndex.value]);

const variableValues = reactive<Record<string, string>>({});

const detectedVariables = computed(() => {
  const re = /\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}/g;
  const names = new Set<string>();
  for (const block of form.blocks) {
    for (const match of (block.content || "").matchAll(re)) {
      names.add(match[1]);
    }
  }
  return Array.from(names);
});

const preview = computed(() => {
  const re = /\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}/g;
  return form.blocks
    .map((block) => {
      const text = (block.content || "").replace(re, (raw: string, name: string) => {
        const value = variableValues[name];
        return value === undefined || value === "" ? raw : value;
      });
      return `【${block.type}】\n${text}`;
    })
    .join("\n\n");
});

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
function renderMd(text: string) {
  return md.render(text || "");
}

function resetVariables() {
  Object.keys(variableValues).forEach((key) => delete variableValues[key]);
}

function resetForm() {
  currentId.value = undefined;
  form.name = "";
  form.category = "";
  form.enabled = true;
  form.blocks = [{ key: uid(), type: "system", content: "" }];
  activeIndex.value = 0;
  resetVariables();
}

function addBlock() {
  form.blocks.push({ key: uid(), type: newBlockType.value, content: "" });
  activeIndex.value = form.blocks.length - 1;
}

function removeBlock(index: number) {
  form.blocks.splice(index, 1);
  if (activeIndex.value >= form.blocks.length) {
    activeIndex.value = Math.max(0, form.blocks.length - 1);
  }
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

// ---- 批量启停 / 统计摘要 ----
const promptSelIds = ref<number[]>([]);
function onPromptSel(sel: any[]) {
  promptSelIds.value = sel.map((s: any) => s.id);
}
const promptSummary = ref({ total: 0, enabled: 0, disabled: 0 });
const templates = ref<any[]>([]);
async function loadTemplates() {
  try {
    templates.value = (await getAiPromptTemplates()).data?.data || [];
  } catch {
    templates.value = [];
  }
}
async function createFromTemplate(tpl: any) {
  try {
    const r = await createAiPromptFromTemplate(tpl.key, tpl.name);
    ElMessage.success(
      t("ai_workflow.prompt_fromTemplateSuccess", { name: r.data?.data?.name || tpl.name })
    );
    loadPromptSummary();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.prompt_createFail"));
  }
}
async function loadPromptSummary() {
  try {
    const res = await getAiPromptList();
    const list = res.data?.data || [];
    promptSummary.value = {
      total: list.length,
      enabled: list.filter((x: any) => x.enabled).length,
      disabled: list.filter((x: any) => !x.enabled).length,
    };
  } catch {
    /* 忽略 */
  }
}
async function batchPrompt(enabled: boolean) {
  if (!promptSelIds.value.length) return;
  try {
    const r = await batchPromptStatus(promptSelIds.value, enabled);
    ElMessage.success(
      t("ai_workflow.prompt_batchResult", {
        action: enabled
          ? t("ai_workflow.prompt_enabledText")
          : t("ai_workflow.prompt_disabledText"),
        count: r.data?.data?.count || 0,
      })
    );
    refreshList();
    loadPromptSummary();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_workflow.prompt_opFail"));
  }
}

// ---- 详情预览 ----
const detailVisible = ref(false);
const detail = ref<any>(null);
async function openDetail(row: any) {
  try {
    const res = await getAiPromptDetail(row.id);
    detail.value = res.data?.data || row;
  } catch {
    detail.value = row;
  }
  detailVisible.value = true;
}

// ---- 复制 ----
async function doCopy(row: any) {
  try {
    await createAiPrompt({
      name: t("ai_workflow.prompt_copyName", { name: row.name }),
      category: row.category || "",
      enabled: row.enabled !== false,
      blocks: (row.blocks || []).map((b: any) => ({ type: b.type, content: b.content })),
      variables: row.variables || [],
    });
    ElMessage.success(t("ai_workflow.prompt_copySuccess"));
    refreshList();
    loadPromptSummary();
  } catch {
    ElMessage.error(t("ai_workflow.prompt_copyFail"));
  }
}

onMounted(() => {
  loadPromptSummary();
  loadTemplates();
});

async function handleOpenDialog(type: "create" | "update", id?: number) {
  resetForm();
  if (type === "update" && id) {
    dialogTitle.value = t("ai_workflow.prompt_editTitle");
    try {
      const res = await getAiPromptDetail(id);
      const data = res.data?.data || {};
      currentId.value = id;
      form.name = data.name || "";
      form.category = data.category || "";
      form.enabled = data.enabled !== false;
      form.blocks = (data.blocks || []).map((b: any) => ({
        key: uid(),
        type: b.type || "instruction",
        content: b.content || "",
      }));
      activeIndex.value = 0;
      resetVariables();
    } catch (e: any) {
      ElMessage.error(e?.msg || t("ai_workflow.prompt_loadFail"));
      return;
    }
  } else {
    dialogTitle.value = t("ai_workflow.prompt_createTitle");
  }
  dialogVisible.value = true;
}

function handleCloseDialog() {
  dialogVisible.value = false;
  resetForm();
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning(t("ai_workflow.prompt_nameRequired"));
    return;
  }
  const payload = {
    name: form.name.trim(),
    category: form.category,
    enabled: form.enabled,
    blocks: form.blocks.map(({ type, content }) => ({ type, content })),
    variables: detectedVariables.value,
  };
  saving.value = true;
  try {
    if (currentId.value) await updateAiPrompt(currentId.value, payload);
    else await createAiPrompt(payload);
    dialogVisible.value = false;
    refreshList();
    ElMessage.success(t("ai_workflow.prompt_saveSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.prompt_saveFail"));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped lang="scss">
.batch-ac {
  margin-left: 8px;
}
.summary-tag {
  margin-left: 8px;
}
.cap-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}
.muted {
  color: var(--el-text-color-placeholder);
}

/* ===== 编辑区：顶部信息条 + 左导航 / 主编辑 / 右助手 ===== */
.prompt-editor {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 200px);
  min-height: 480px;
}

.prompt-editor__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);

  .prompt-editor__name {
    width: 300px;
  }

  .prompt-editor__category {
    width: 220px;
  }

  .prompt-editor__enabled {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    color: var(--el-text-color-regular);
  }
}

/* 编辑台：三栏融合为一个整体（分隔线分隔），不再三块盒子拼贴 */
.prompt-editor__body {
  display: flex;
  gap: 0;
  flex: 1;
  min-height: 0;
  margin-top: 14px;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

/* ---- 左：块导航 ---- */
.prompt-editor__nav {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 250px;
  min-height: 0;
  padding: 12px;
  border-right: 1px solid var(--el-border-color-lighter);

  &-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    font-weight: 600;
  }

  &-list {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;

  &:hover {
    border-color: var(--el-color-primary-light-5);
  }

  &--active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &__tag {
    flex-shrink: 0;
  }

  &__preview {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  &__del {
    flex-shrink: 0;
  }
}

.drag-handle {
  color: var(--el-text-color-secondary);
  cursor: grab;
  user-select: none;
}

.block-item--ghost {
  opacity: 0.5;
  background: var(--el-color-primary-light-8);
}

.prompt-editor__add {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);

  &-select {
    flex: 1;
  }
}

/* ---- 中：主编辑区 ---- */
.prompt-editor__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 12px;

  &-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }

  &-title {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  &-index {
    color: var(--el-text-color-secondary);
    font-size: 12px;
    white-space: nowrap;
  }

  &-type-select {
    flex-shrink: 0;
    width: 160px;
  }

  &-textarea {
    flex: 1;
    min-height: 0;

    :deep(.el-textarea) {
      height: 100%;
    }

    :deep(.el-textarea__inner) {
      height: 100%;
      min-height: 100%;
      font-family: var(--el-font-family-mono, monospace);
    }
  }

  &-hint {
    margin-top: 8px;

    code {
      padding: 0 4px;
      color: var(--el-color-primary);
      background: var(--el-fill-color-light);
      border-radius: 4px;
      font-family: var(--el-font-family-mono, monospace);
    }
  }
}

/* ---- 右：助手面板（变量 / 预览） ---- */
.prompt-editor__aside {
  flex-shrink: 0;
  width: 300px;
  min-height: 0;
  padding: 0 12px 12px;
  overflow: auto;
  border-left: 1px solid var(--el-border-color-lighter);

  :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
}

.var-tip {
  display: block;
  margin-top: 4px;

  code {
    padding: 0 4px;
    color: var(--el-color-primary);
    background: var(--el-fill-color-light);
    border-radius: 4px;
    font-family: var(--el-font-family-mono, monospace);
  }
}

/* ===== 详情抽屉（保留） ===== */
.prompt-block-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.prompt-block__body {
  margin-top: 4px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  word-break: break-word;
}
.prompt-block__body :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 6px;
  overflow: auto;
}
.prompt-block__body :deep(code) {
  font-family: var(--el-font-family-mono, monospace);
}
.prompt-block__body :deep(h1),
.prompt-block__body :deep(h2),
.prompt-block__body :deep(h3) {
  margin: 0.5em 0;
}

/* ===== 变量 / 预览（共用） ===== */
.var-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.var-row__input {
  flex: 1;
}

.preview {
  line-height: 1.7;
  word-break: break-word;
  font-family: inherit;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
}
.preview.muted {
  color: var(--el-text-color-placeholder);
}
.preview :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 6px;
  overflow: auto;
}
.preview :deep(code) {
  font-family: var(--el-font-family-mono, monospace);
}
.preview :deep(h1),
.preview :deep(h2),
.preview :deep(h3) {
  margin: 0.5em 0;
}
</style>
