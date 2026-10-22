<!-- 技能创建/编辑对话框：新建表单 + 导入 SKILL.md / Zip。
     由「能力市场 → 我的资产」挂载，复用原技能广场逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="props.realId ? '编辑技能' : '新建技能'"
    width="600px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <el-tabs v-if="!props.realId" v-model="importTab" class="skill-tabs">
      <el-tab-pane label="表单新建" name="form" />
      <el-tab-pane label="粘贴 SKILL.md" name="paste" />
      <el-tab-pane label="上传 Zip 包" name="zip" />
    </el-tabs>

    <!-- 表单新建 / 编辑 -->
    <el-form v-if="importTab === 'form'" :model="skillForm" label-width="90px" size="default">
      <el-form-item label="名称" required>
        <el-input v-model="skillForm.name" placeholder="技能名称" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="skillForm.skill_type" style="width: 100%">
          <el-option label="指令 (instruction)" value="instruction" />
          <el-option label="工具 (tool)" value="tool" />
          <el-option label="自定义 (custom)" value="custom" />
        </el-select>
      </el-form-item>
      <el-form-item label="分类">
        <el-input v-model="skillForm.category" placeholder="分类标签（可选）" />
      </el-form-item>
      <el-form-item label="作者">
        <el-input v-model="skillForm.author" placeholder="作者（可选）" />
      </el-form-item>
      <el-form-item label="版本">
        <el-input v-model="skillForm.version" placeholder="1.0" style="width: 160px" />
      </el-form-item>
      <el-form-item label="图标">
        <el-input v-model="skillForm.icon" placeholder="emoji 或图片URL" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="skillForm.description"
          type="textarea"
          :rows="2"
          placeholder="简要描述这个技能"
        />
      </el-form-item>
      <el-form-item label="技能内容">
        <div class="skill-md-editor">
          <el-radio-group v-model="skillContentMode" size="small" class="skill-md-editor__tabs">
            <el-radio-button value="edit">编辑</el-radio-button>
            <el-radio-button value="preview">预览</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="skillContentMode === 'edit'"
            v-model="skillForm.content"
            type="textarea"
            :rows="8"
            placeholder="Markdown 指令/使用说明，支持 {{变量}}，绑定到智能体后并入系统提示词"
          />
          <div v-else class="skill-md-editor__preview" v-html="renderMd(skillForm.content)"></div>
        </div>
      </el-form-item>
      <el-form-item label="排序">
        <el-input-number v-model="skillForm.sort_order" :min="0" />
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="skillForm.enabled" />
      </el-form-item>
    </el-form>

    <!-- 导入：粘贴 SKILL.md -->
    <template v-else-if="importTab === 'paste'">
      <el-input
        v-model="importForm.content"
        type="textarea"
        :rows="12"
        placeholder="粘贴技能文档全文（可含 --- YAML frontmatter ---），例如 SkillHub 技能详情页的 SKILL.md 内容"
      />
      <el-form label-width="80px" class="import-meta">
        <el-form-item label="技能名">
          <el-input v-model="importForm.name" placeholder="留空则用文档中的 name" maxlength="128" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input
            v-model="importForm.category"
            placeholder="如：办公效率（留空归入「导入技能」）"
            maxlength="64"
          />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="importForm.source" placeholder="SkillHub" maxlength="64" />
        </el-form-item>
      </el-form>
    </template>

    <!-- 导入：上传 Zip -->
    <template v-else>
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".zip"
        :file-list="zipFiles"
        :on-change="onZipChange"
        :on-remove="() => (zipFiles = [])"
      >
        <el-icon class="upload-icon"><Upload /></el-icon>
        <div class="el-upload__text">
          把技能 Zip 拖到此处，或
          <em>点击选择</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">平台只读取其中的 SKILL.md 与文本文件，不落盘、不执行脚本</div>
        </template>
      </el-upload>
      <el-form label-width="80px" class="import-meta">
        <el-form-item label="分类">
          <el-input
            v-model="importForm.category"
            placeholder="如：办公效率（留空归入「导入技能」）"
            maxlength="64"
          />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="importForm.source" placeholder="SkillHub" maxlength="64" />
        </el-form-item>
      </el-form>
    </template>

    <el-alert
      v-if="!props.realId && importTab !== 'form'"
      type="info"
      :closable="false"
      show-icon
      title="导入后技能默认停用：请先检查内容与附带脚本，确认无误再启用（平台不会执行导入的脚本）。"
    />

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import MarkdownIt from "markdown-it";

import {
  createAiSkill,
  getAiSkillDetail,
  importAiSkill,
  importAiSkillZip,
  updateAiSkill,
} from "@/api/module_ai/skill";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
function renderMd(text: string) {
  return md.render(text || "");
}

const saving = ref(false);
const importTab = ref("form");
const skillContentMode = ref("edit");
const skillForm = reactive<any>({});
const importForm = reactive({ content: "", name: "", category: "", source: "SkillHub" });
const zipFiles = ref<any[]>([]);

function resetForm() {
  importTab.value = "form";
  skillContentMode.value = "edit";
  Object.assign(skillForm, {
    name: "",
    skill_type: "instruction",
    category: "",
    author: "",
    version: "1.0",
    icon: "",
    description: "",
    content: "",
    sort_order: 0,
    enabled: true,
  });
  Object.assign(importForm, { content: "", name: "", category: "", source: "SkillHub" });
  zipFiles.value = [];
}

async function loadForEdit() {
  if (!props.realId) return;
  try {
    const res: any = await getAiSkillDetail(props.realId);
    const s = res.data?.data;
    if (!s) return;
    importTab.value = "form";
    Object.assign(skillForm, {
      name: s.name,
      skill_type: s.skill_type,
      category: s.category || "",
      author: s.author || "",
      version: s.version || "1.0",
      icon: s.icon || "",
      description: s.description || "",
      content: s.content || "",
      sort_order: s.sort_order || 0,
      enabled: s.enabled,
    });
  } catch {
    /* 详情加载失败时保留空表单 */
  }
}

function onZipChange(file: any) {
  zipFiles.value = [file];
}

async function handleSave() {
  saving.value = true;
  try {
    let res: any;
    if (props.realId) {
      if (!skillForm.name) {
        ElMessage.warning("请填写技能名称");
        return;
      }
      await updateAiSkill(props.realId, {
        name: skillForm.name,
        skill_type: skillForm.skill_type,
        category: skillForm.category || null,
        author: skillForm.author || null,
        version: skillForm.version || "1.0",
        icon: skillForm.icon || null,
        description: skillForm.description,
        content: skillForm.content,
        sort_order: skillForm.sort_order || 0,
        enabled: skillForm.enabled,
      });
      ElMessage.success("保存成功");
      visible.value = false;
      emit("saved");
      return;
    }

    if (importTab.value === "form") {
      if (!skillForm.name) {
        ElMessage.warning("请填写技能名称");
        return;
      }
      await createAiSkill({
        name: skillForm.name,
        skill_type: skillForm.skill_type,
        category: skillForm.category || null,
        author: skillForm.author || null,
        version: skillForm.version || "1.0",
        icon: skillForm.icon || null,
        description: skillForm.description,
        content: skillForm.content,
        sort_order: skillForm.sort_order || 0,
        enabled: skillForm.enabled,
      });
      ElMessage.success("创建成功");
    } else if (importTab.value === "zip") {
      const raw = zipFiles.value[0]?.raw;
      if (!raw) {
        ElMessage.warning("请先选择 Zip 包");
        return;
      }
      res = await importAiSkillZip(raw, importForm.category || undefined, importForm.source);
      const name = res.data?.data?.name || "技能";
      ElMessage.success(`已导入「${name}」（默认停用，请检查后启用）`);
    } else {
      if (!importForm.content.trim()) {
        ElMessage.warning("请粘贴技能文档内容");
        return;
      }
      res = await importAiSkill({
        content: importForm.content,
        name: importForm.name || undefined,
        category: importForm.category || undefined,
        source: importForm.source || undefined,
      });
      const name = res.data?.data?.name || "技能";
      ElMessage.success(`已导入「${name}」（默认停用，请检查后启用）`);
    }
    visible.value = false;
    emit("saved");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

defineExpose({ loadForEdit });

watch(
  () => props.modelValue,
  (v) => {
    if (v) loadForEdit();
  }
);
</script>

<style scoped>
.skill-md-editor {
  width: 100%;
}
.skill-md-editor__tabs {
  margin: 6px 0 8px;
}
.skill-md-editor__preview {
  min-height: 160px;
  line-height: 1.7;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  word-break: break-word;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px;
  max-height: 40vh;
  overflow: auto;
}
.import-meta {
  margin-top: 12px;
}
.upload-icon {
  font-size: 40px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
</style>
