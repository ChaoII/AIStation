<!-- 能力插件创建/编辑对话框：JSON 配置。
     由「能力市场 → 我的资产」挂载，复用原能力插件逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="props.realId ? '编辑能力插件' : '新增能力插件'"
    width="560px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
      <el-form-item label="标识" prop="key">
        <el-input
          v-model="form.key"
          :disabled="!!form.id"
          maxlength="64"
          placeholder="如：web_fetch"
        />
      </el-form-item>
      <el-form-item label="名称" prop="label">
        <el-input v-model="form.label" maxlength="128" placeholder="展示名" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
      <el-form-item label="配置">
        <el-input
          v-model="configText"
          type="textarea"
          :rows="4"
          placeholder='JSON 配置，例如：{"timeout": 15}'
        />
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, type FormInstance } from "element-plus";

import { createPlugin, getPluginList, updatePlugin } from "@/api/module_ai/plugin";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const saving = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ id: 0, key: "", label: "", description: "", enabled: true });
const configText = ref("{}");

const rules = {
  key: [{ required: true, message: "请输入插件标识", trigger: "blur" }],
  label: [{ required: true, message: "请输入名称", trigger: "blur" }],
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
    ElMessage.warning("配置必须是合法 JSON");
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
      ElMessage.success("修改成功");
    } else {
      await createPlugin({
        key: form.key,
        label: form.label,
        description: form.description,
        enabled: form.enabled,
        config,
        kind: "custom",
      });
      ElMessage.success("创建成功");
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
