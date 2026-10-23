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
            从模板创建
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
            批量启用
          </el-button>
          <el-button size="small" :disabled="!promptSelIds.length" @click="batchPrompt(false)">
            批量停用
          </el-button>
        </span>
        <el-tag size="small" type="info" effect="plain" class="summary-tag">
          共 {{ promptSummary.total }} 个提示词 · 启用 {{ promptSummary.enabled }} · 停用
          {{ promptSummary.disabled }}
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
              <el-empty :image-size="80" description="暂无提示词，点击「新建」创建" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
            <el-table-column label="分类" prop="category" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.category || "—" }}</template>
            </el-table-column>
            <el-table-column label="版本" prop="version" width="80" align="center">
              <template #default="{ row }">v{{ row.version ?? 1 }}</template>
            </el-table-column>
            <el-table-column label="启用" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="230" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:prompt:query']"
                  icon="View"
                  size="small"
                  link
                  type="primary"
                  @click="openDetail(row)"
                >
                  详情
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:update']"
                  icon="edit"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:create']"
                  icon="CopyDocument"
                  size="small"
                  link
                  @click="doCopy(row)"
                >
                  复制
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:delete']"
                  icon="delete"
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
            placeholder="提示词名称（唯一）"
            clearable
            class="prompt-editor__name"
          />
          <el-input
            v-model="form.category"
            placeholder="分类，如：qa / 摘要 / 报表"
            clearable
            class="prompt-editor__category"
          />
          <div class="prompt-editor__enabled">
            <span>启用</span>
            <el-switch v-model="form.enabled" />
          </div>
        </div>

        <div class="prompt-editor__body">
          <!-- 左：块导航（排序 / 增删 / 选中） -->
          <div class="prompt-editor__nav">
            <div class="prompt-editor__nav-head">
              <span>提示词块</span>
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
                    <span class="nav-item__preview">{{ element.content || "（空）" }}</span>
                    <el-button
                      v-hasPerm="['module_ai:prompt:update']"
                      link
                      type="danger"
                      size="small"
                      class="nav-item__del"
                      @click.stop="removeBlock(index)"
                    >
                      删
                    </el-button>
                  </div>
                </template>
              </draggable>
              <el-empty v-if="!form.blocks.length" :image-size="40" description="暂无块" />
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
                添加块
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
                    第 {{ activeIndex + 1 }} / {{ form.blocks.length }} 块
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
                :placeholder="`${typeLabel(currentBlock.type)}内容，支持 {{变量名}} 插值`"
                class="prompt-editor__textarea"
              />
              <div class="prompt-editor__hint">
                <el-text size="small" type="info">
                  支持
                  <code>&#123;&#123;变量名&#125;&#125;</code>
                  插值；左侧拖拽调整块顺序，右侧可填写示例值并实时预览
                </el-text>
              </div>
            </template>
            <el-empty v-else :image-size="60" description="暂无块，请从左侧添加" />
          </div>

          <!-- 右：助手面板（变量 / 预览） -->
          <div class="prompt-editor__aside">
            <el-tabs v-model="asideTab">
              <el-tab-pane label="变量" name="vars">
                <el-empty
                  v-if="!detectedVariables.length"
                  :image-size="50"
                  description="未检测到变量"
                />
                <div v-for="name in detectedVariables" :key="name" class="var-row">
                  <el-tag size="small">{{ name }}</el-tag>
                  <el-input
                    v-model="variableValues[name]"
                    size="small"
                    placeholder="示例值"
                    class="var-row__input"
                  />
                </div>
                <el-text v-if="!detectedVariables.length" size="small" type="info" class="var-tip">
                  在块内容中写入
                  <code>&#123;&#123;变量名&#125;&#125;</code>
                  后会自动识别
                </el-text>
              </el-tab-pane>
              <el-tab-pane label="预览" name="preview">
                <div v-if="preview" class="preview" v-html="renderMd(preview)"></div>
                <div v-else class="preview muted">（暂无内容）</div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- 提示词详情预览抽屉 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || '提示词详情'"
      size="480px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="分类">{{ detail.category || "—" }}</el-descriptions-item>
        <el-descriptions-item label="版本">v{{ detail.version ?? 1 }}</el-descriptions-item>
        <el-descriptions-item label="启用">
          <el-tag :type="detail.enabled ? 'success' : 'info'" size="small">
            {{ detail.enabled ? "启用" : "停用" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="变量">
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
        <el-descriptions-item label="提示词内容" :span="1">
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

interface PromptBlock {
  key: string;
  type: string;
  content: string;
}

const blockTypeOptions = [
  { label: "系统 (system)", value: "system" },
  { label: "上下文 (context)", value: "context" },
  { label: "指令 (instruction)", value: "instruction" },
  { label: "示例 (example)", value: "example" },
  { label: "输出 (output)", value: "output" },
];

const blockTypeLabels: Record<string, string> = {
  system: "系统",
  context: "上下文",
  instruction: "指令",
  example: "示例",
  output: "输出",
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
      label: "名称",
      type: "input",
      attrs: { placeholder: "提示词名称", clearable: true, style: { width: "200px" } },
    },
    {
      prop: "category",
      label: "分类",
      type: "input",
      attrs: { placeholder: "分类", clearable: true, style: { width: "200px" } },
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
const dialogTitle = ref("新增提示词");
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
    ElMessage.success(`已从模板创建「${r.data?.data?.name || tpl.name}」`);
    loadPromptSummary();
  } catch (e: any) {
    ElMessage.error(e?.msg || "创建失败");
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
    ElMessage.success(`已${enabled ? "启用" : "停用"} ${r.data?.data?.count || 0} 个提示词`);
    refreshList();
    loadPromptSummary();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
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
      name: `${row.name}（副本）`,
      category: row.category || "",
      enabled: row.enabled !== false,
      blocks: (row.blocks || []).map((b: any) => ({ type: b.type, content: b.content })),
      variables: row.variables || [],
    });
    ElMessage.success("已复制提示词");
    refreshList();
    loadPromptSummary();
  } catch {
    ElMessage.error("复制失败");
  }
}

onMounted(() => {
  loadPromptSummary();
  loadTemplates();
});

async function handleOpenDialog(type: "create" | "update", id?: number) {
  resetForm();
  if (type === "update" && id) {
    dialogTitle.value = "编辑提示词";
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
      ElMessage.error(e?.msg || "加载失败");
      return;
    }
  } else {
    dialogTitle.value = "新增提示词";
  }
  dialogVisible.value = true;
}

function handleCloseDialog() {
  dialogVisible.value = false;
  resetForm();
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写提示词名称");
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
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
