<!-- AI 提示词工作台（画布）：左块列表可拖拽 / 中块编辑 / 右变量与预览 -->
<template>
  <div class="app-container ai-prompt-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-select
          v-model="currentId"
          class="toolbar__select"
          clearable
          filterable
          placeholder="选择提示词加载"
          @change="handleSelect"
          @clear="newPrompt"
        >
          <el-option v-for="p in promptList" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button @click="newPrompt">新建</el-button>
        <el-button
          v-hasPerm="['module_ai:prompt:create']"
          type="primary"
          :loading="saving"
          @click="handleSave"
        >
          保存
        </el-button>
        <el-button
          v-hasPerm="['module_ai:prompt:delete']"
          type="danger"
          :disabled="!currentId"
          @click="handleDelete"
        >
          删除
        </el-button>
      </div>
    </el-card>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import draggable from "vuedraggable";
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

const promptList = ref<any[]>([]);
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

function newPrompt() {
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

async function refreshPrompts() {
  try {
    const res = await getAiPromptList();
    promptList.value = res.data?.data || [];
  } catch {
    promptList.value = [];
  }
}

async function handleSelect(id: number | undefined) {
  if (!id) return;
  try {
    const res = await getAiPromptDetail(id);
    const data = res.data?.data || {};
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
  }
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
    const res = currentId.value
      ? await updateAiPrompt(currentId.value, payload)
      : await createAiPrompt(payload);
    const saved = res.data?.data;
    if (saved?.id) currentId.value = saved.id;
    await refreshPrompts();
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function handleDelete() {
  if (!currentId.value) return;
  try {
    await ElMessageBox.confirm("确认删除该提示词?", "警告", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteAiPrompt([currentId.value]);
    newPrompt();
    await refreshPrompts();
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

onMounted(() => {
  newPrompt();
  refreshPrompts();
});
</script>

<style scoped>
.toolbar-card,
.col-card {
  flex-shrink: 0;
}

.col-card {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.toolbar__select {
  width: 260px;
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
