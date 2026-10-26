<template>
  <div class="edge-config-panel">
    <div class="panel-header">
      <span>{{ t("task.edgeConfig") }}</span>
      <ElButton type="text" class="close-btn" @click="handleClose">
        <ElIcon><Close /></ElIcon>
      </ElButton>
    </div>

    <div class="panel-content">
      <ElForm :model="formData" label-width="80px" size="small">
        <ElFormItem :label="t('task.edgeName')">
          <ElInput v-model="formData.label" :placeholder="t('task.inputEdgeName')" />
        </ElFormItem>

        <ElFormItem :label="t('task.edgeType')">
          <ElSelect v-model="formData.type" :placeholder="t('task.selectEdgeType')">
            <ElOption :label="t('task.polyline')" value="smoothstep" />
            <ElOption :label="t('task.curve')" value="default" />
            <ElOption :label="t('task.line')" value="straight" />
          </ElSelect>
        </ElFormItem>

        <ElFormItem :label="t('task.edgeColor')">
          <ElColorPicker v-model="formData.color" />
        </ElFormItem>

        <ElFormItem :label="t('task.lineWidth')">
          <ElInputNumber v-model="formData.strokeWidth" :min="1" :max="10" />
        </ElFormItem>

        <ElFormItem :label="t('task.enableAnimation')">
          <ElSwitch v-model="formData.animated" />
        </ElFormItem>

        <ElFormItem :label="t('task.conditionExpr')">
          <ElInput
            v-model="formData.condition"
            type="textarea"
            :rows="3"
            :placeholder="t('task.inputConditionExpr')"
          />
        </ElFormItem>

        <ElFormItem :label="t('task.descLabel')">
          <ElInput
            v-model="formData.description"
            type="textarea"
            :rows="2"
            :placeholder="t('task.inputDesc')"
          />
        </ElFormItem>
      </ElForm>

      <div class="panel-actions">
        <ElButton type="primary" size="small" @click="handleSave">{{ t("task.save") }}</ElButton>
        <ElButton type="danger" size="small" @click="handleDelete">
          {{ t("task.deleteEdge") }}
        </ElButton>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElInputNumber,
  ElSwitch,
  ElColorPicker,
  ElMessage,
  ElIcon,
} from "element-plus";
import { Close } from "@element-plus/icons-vue";

const props = defineProps({
  edge: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["close", "save", "delete"]);

const { t } = useI18n();

const formData = ref({
  label: props.edge?.label || "",
  type: props.edge?.type || "smoothstep",
  color: props.edge?.style?.stroke || "#000000",
  strokeWidth: props.edge?.style?.strokeWidth || 2,
  animated: props.edge?.animated || false,
  condition: props.edge?.data?.condition || "",
  description: props.edge?.data?.description || "",
});

watch(
  () => props.edge,
  (newEdge) => {
    if (newEdge) {
      formData.value = {
        label: newEdge.label || "",
        type: newEdge.type || "smoothstep",
        color: newEdge.style?.stroke || "#000000",
        strokeWidth: newEdge.style?.strokeWidth || 2,
        animated: newEdge.animated || false,
        condition: newEdge.data?.condition || "",
        description: newEdge.data?.description || "",
      };
    }
  },
  { deep: true }
);

function handleClose() {
  emit("close");
}

function handleSave() {
  emit("save", formData.value);
  ElMessage.success(t("task.saveSuccess"));
}

function handleDelete() {
  emit("delete");
}
</script>

<style scoped>
.edge-config-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  font-weight: 600;
  border-bottom: 1px solid #e5e7eb;
}

.close-btn {
  padding: 4px;
}

.panel-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.panel-actions {
  display: flex;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.panel-actions .el-button {
  flex: 1;
}
</style>
