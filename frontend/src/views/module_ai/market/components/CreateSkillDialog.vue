<!-- 技能创建/编辑对话框：新建表单 + 导入 SKILL.md / Zip。
     由「能力市场 → 我的资产」挂载，复用原技能广场逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="props.realId ? t('ai_market.editSkill') : t('ai_market.createSkill')"
    width="600px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <el-tabs v-if="!props.realId" v-model="importTab" class="skill-tabs">
      <el-tab-pane :label="t('ai_market.formCreate')" name="form" />
      <el-tab-pane :label="t('ai_market.pasteSkill')" name="paste" />
      <el-tab-pane :label="t('ai_market.uploadZip')" name="zip" />
    </el-tabs>

    <!-- 表单新建 / 编辑 -->
    <el-form v-if="importTab === 'form'" :model="skillForm" label-width="90px" size="default">
      <el-form-item :label="t('ai_market.nameLabel')" required>
        <el-input v-model="skillForm.name" :placeholder="t('ai_market.skillNamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('ai_market.typeLabel')">
        <el-select v-model="skillForm.skill_type" style="width: 100%">
          <el-option :label="t('ai_market.instructionOption')" value="instruction" />
          <el-option :label="t('ai_market.toolOption')" value="tool" />
          <el-option :label="t('ai_market.customOption')" value="custom" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_market.category')">
        <el-input
          v-model="skillForm.category"
          :placeholder="t('ai_market.categoryTagPlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.author')">
        <el-input v-model="skillForm.author" :placeholder="t('ai_market.authorPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('ai_market.version')">
        <el-input
          v-model="skillForm.version"
          :placeholder="t('ai_market.versionPlaceholder')"
          style="width: 160px"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.iconLabel')">
        <el-input v-model="skillForm.icon" :placeholder="t('ai_market.iconPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('ai_market.description')">
        <el-input
          v-model="skillForm.description"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_market.skillDescPlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.skillContentLabel')">
        <div class="skill-md-editor">
          <el-radio-group v-model="skillContentMode" size="small" class="skill-md-editor__tabs">
            <el-radio-button value="edit">{{ t("ai_market.editLabel") }}</el-radio-button>
            <el-radio-button value="preview">{{ t("ai_market.preview") }}</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="skillContentMode === 'edit'"
            v-model="skillForm.content"
            type="textarea"
            :rows="8"
            :placeholder="t('ai_market.skillContentPlaceholder')"
          />
          <div v-else class="skill-md-editor__preview" v-html="renderMd(skillForm.content)"></div>
        </div>
      </el-form-item>
      <el-form-item :label="t('ai_market.sortLabel')">
        <el-input-number v-model="skillForm.sort_order" :min="0" />
      </el-form-item>
      <el-form-item :label="t('ai_market.enableLabel')">
        <el-switch v-model="skillForm.enabled" />
      </el-form-item>
    </el-form>

    <!-- 导入：粘贴 SKILL.md -->
    <template v-else-if="importTab === 'paste'">
      <el-input
        v-model="importForm.content"
        type="textarea"
        :rows="12"
        :placeholder="t('ai_market.pastePlaceholder')"
      />
      <el-form label-width="80px" class="import-meta">
        <el-form-item :label="t('ai_market.skillName')">
          <el-input
            v-model="importForm.name"
            :placeholder="t('ai_market.nameIfBlankPlaceholder')"
            maxlength="128"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.category')">
          <el-input
            v-model="importForm.category"
            :placeholder="t('ai_market.skillCategoryPlaceholder')"
            maxlength="64"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.sourceLabel')">
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
          {{ t("ai_market.uploadDragText") }}
          <em>{{ t("ai_market.uploadClickText") }}</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">{{ t("ai_market.uploadTip") }}</div>
        </template>
      </el-upload>
      <el-form label-width="80px" class="import-meta">
        <el-form-item :label="t('ai_market.category')">
          <el-input
            v-model="importForm.category"
            :placeholder="t('ai_market.skillCategoryPlaceholder')"
            maxlength="64"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.sourceLabel')">
          <el-input v-model="importForm.source" placeholder="SkillHub" maxlength="64" />
        </el-form-item>
      </el-form>
    </template>

    <el-alert
      v-if="!props.realId && importTab !== 'form'"
      type="info"
      :closable="false"
      show-icon
      :title="t('ai_market.importDisabledAlert')"
    />

    <template #footer>
      <el-button @click="visible = false">{{ t("ai_market.cancel") }}</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ t("ai_market.save") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
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

const { t } = useI18n();

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
        ElMessage.warning(t("ai_market.requireSkillName"));
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
      ElMessage.success(t("ai_market.saveSuccess"));
      visible.value = false;
      emit("saved");
      return;
    }

    if (importTab.value === "form") {
      if (!skillForm.name) {
        ElMessage.warning(t("ai_market.requireSkillName"));
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
      ElMessage.success(t("ai_market.createSuccess"));
    } else if (importTab.value === "zip") {
      const raw = zipFiles.value[0]?.raw;
      if (!raw) {
        ElMessage.warning(t("ai_market.selectZipFirst"));
        return;
      }
      res = await importAiSkillZip(raw, importForm.category || undefined, importForm.source);
      const name = res.data?.data?.name || t("ai_market.skillFallbackName");
      ElMessage.success(t("ai_market.importedSkill", { name }));
    } else {
      if (!importForm.content.trim()) {
        ElMessage.warning(t("ai_market.pasteContentRequired"));
        return;
      }
      res = await importAiSkill({
        content: importForm.content,
        name: importForm.name || undefined,
        category: importForm.category || undefined,
        source: importForm.source || undefined,
      });
      const name = res.data?.data?.name || t("ai_market.skillFallbackName");
      ElMessage.success(t("ai_market.importedSkill", { name }));
    }
    visible.value = false;
    emit("saved");
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || t("ai_market.saveFailed"));
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
