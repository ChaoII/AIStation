<!-- 能力插件创建/编辑对话框：JSON 配置。
     由「能力市场 → 我的资产」挂载，复用原能力插件逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="props.realId ? t('ai_market.editPlugin') : t('ai_market.createPlugin')"
    width="600px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
      <el-form-item :label="t('ai_market.keyLabel')" prop="key">
        <el-input
          v-model="form.key"
          :disabled="!!form.id"
          maxlength="64"
          :placeholder="t('ai_market.pluginKeyPlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.nameLabel')" prop="label">
        <el-input
          v-model="form.label"
          maxlength="128"
          :placeholder="t('ai_market.displayNamePlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
      <el-form-item :label="t('ai_market.configLabel')">
        <el-input
          v-model="configText"
          type="textarea"
          :rows="4"
          :placeholder="t('ai_market.jsonConfigPlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.enableLabel')">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </el-form>

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
import { ElMessage, type FormInstance } from "element-plus";

import { createPlugin, getPluginList, updatePlugin } from "@/api/module_ai/plugin";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const saving = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ id: 0, key: "", label: "", description: "", enabled: true });
const configText = ref("{}");

const rules = {
  key: [{ required: true, message: t("ai_market.requirePluginKey"), trigger: "blur" }],
  label: [{ required: true, message: t("ai_market.requiredName"), trigger: "blur" }],
};

function resetForm() {
  form.id = 0;
  form.key = "";
  form.label = "";
  form.description = "";
  form.enabled = true;
  configText.value = "{}";
}

async function loadForEdit() {
  if (!props.realId) return;
  try {
    const res: any = await getPluginList();
    const row = (res.data?.data || []).find((r: any) => r.id === props.realId);
    if (!row) return;
    form.id = row.id;
    form.key = row.key;
    form.label = row.label;
    form.description = row.description;
    form.enabled = row.enabled;
    configText.value = JSON.stringify(row.config || {}, null, 2);
  } catch {
    /* 详情加载失败时保留空表单 */
  }
}

async function handleSave() {
  if (!formRef.value) return;
  await formRef.value.validate();
  let config: Record<string, any> = {};
  try {
    config = configText.value.trim() ? JSON.parse(configText.value) : {};
  } catch {
    ElMessage.warning(t("ai_market.invalidJson"));
    return;
  }
  saving.value = true;
  try {
    if (form.id) {
      await updatePlugin(form.id, {
        label: form.label,
        description: form.description,
        enabled: form.enabled,
        config,
      });
      ElMessage.success(t("ai_market.updateSuccess"));
    } else {
      await createPlugin({
        key: form.key,
        label: form.label,
        description: form.description,
        enabled: form.enabled,
        config,
        kind: "custom",
      });
      ElMessage.success(t("ai_market.createSuccess"));
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
