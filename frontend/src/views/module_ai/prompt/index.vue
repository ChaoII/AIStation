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
              <el-empty :image-size="80" description="暂无提示词" />
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
            <el-table-column label="操作" fixed="right" width="160" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:prompt:update']"
                  size="small"
                  link
                  type="primary"
                  @click="handleOpenDialog('update', row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:prompt:delete']"
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
      <el-row :gutter="12">
        <el-col :xs="24" :sm="24" :md="6" :lg="6">
          <el-card shadow="never" class="col-card">
            <template #header>提示词块</template>
            <draggable
              v-model="form.blocks"
              item-key="key"
              handle=".drag-handle"
              :animation="150"
              ghost-class="block-item--ghost"
            >
              <template #item="{ element, index }">
                <div
                  class="block-item"
                  :class="{ 'block-item--active': index === activeIndex }"
                  @click="activeIndex = index"
                >
                  <span class="drag-handle">☰</span>
                  <div class="block-item__body">
                    <el-tag size="small" effect="plain">{{ typeLabel(element.type) }}</el-tag>
                    <div class="block-item__preview">{{ element.content || "（空）" }}</div>
                  </div>
                  <el-button
                    v-hasPerm="['module_ai:prompt:update']"
                    link
                    type="danger"
                    size="small"
                    @click.stop="removeBlock(index)"
                  >
                    删
                  </el-button>
                </div>
              </template>
            </draggable>
            <div class="add-block">
              <el-select v-model="newBlockType" class="add-block__select">
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
          </el-card>
        </el-col>

        <el-col :xs="24" :sm="24" :md="12" :lg="12">
          <el-card shadow="never" class="col-card">
            <template #header>编辑</template>
            <el-form :model="form" label-width="64px">
              <el-form-item label="名称">
                <el-input v-model="form.name" placeholder="提示词名称（唯一）" />
              </el-form-item>
              <el-form-item label="分类">
                <el-input v-model="form.category" placeholder="如：qa / 摘要 / 报表" />
              </el-form-item>
              <el-form-item label="启用">
                <el-switch v-model="form.enabled" />
              </el-form-item>
            </el-form>

            <div
              v-for="(block, index) in form.blocks"
              :key="block.key"
              class="block-editor"
              :class="{ 'block-editor--active': index === activeIndex }"
              @click="activeIndex = index"
            >
              <div class="block-editor__head">
                <el-tag size="small">{{ typeLabel(block.type) }}</el-tag>
                <span class="block-editor__index">#{{ index + 1 }}</span>
              </div>
              <el-input
                v-model="block.content"
                type="textarea"
                :rows="3"
                :placeholder="`${typeLabel(block.type)}内容，支持 {{变量名}}`"
              />
            </div>
            <el-empty
              v-if="!form.blocks.length"
              :image-size="60"
              description="暂无块，请从左侧添加"
            />
          </el-card>
        </el-col>

        <el-col :xs="24" :sm="24" :md="6" :lg="6">
          <el-card shadow="never" class="col-card">
            <template #header>变量</template>
            <el-empty
              v-if="!detectedVariables.length"
              :image-size="50"
              description="未检测到 {{变量}}"
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
          </el-card>
          <el-card shadow="never" class="col-card">
            <template #header>预览</template>
            <pre class="preview">{{ preview || "（暂无内容）" }}</pre>
          </el-card>
        </el-col>
      </el-row>

      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import draggable from "vuedraggable";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import {
  createAiPrompt,
  deleteAiPrompt,
  getAiPromptDetail,
  getAiPromptList,
  updateAiPrompt,
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
  deleteConfirm: { title: "警告", message: "确认删除所选提示词?", type: "warning" },
});

const dialogVisible = ref(false);
const dialogTitle = ref("新增提示词");
const currentId = ref<number | undefined>(undefined);
const activeIndex = ref(0);
const newBlockType = ref("instruction");
const saving = ref(false);

const form = reactive({
  name: "",
  category: "",
  enabled: true,
  blocks: [] as PromptBlock[],
});

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

<style scoped>
.col-card {
  margin-bottom: 12px;
}

.block-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  cursor: pointer;
  background: var(--el-bg-color);
}

.block-item--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.block-item--ghost {
  opacity: 0.5;
  background: var(--el-color-primary-light-8);
}

.drag-handle {
  color: var(--el-text-color-secondary);
  cursor: grab;
  user-select: none;
}

.block-item__body {
  flex: 1;
  min-width: 0;
}

.block-item__preview {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.add-block {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.add-block__select {
  flex: 1;
}

.block-editor {
  padding: 8px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.block-editor--active {
  border-color: var(--el-color-primary);
}

.block-editor__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.block-editor__index {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

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
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  color: var(--el-text-color-regular);
}
</style>
