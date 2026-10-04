<template>
  <div class="node-config-panel">
    <div class="panel-header">
      <span>节点配置</span>
      <ElButton type="text" class="close-btn" @click="handleClose">
        <ElIcon><Close /></ElIcon>
      </ElButton>
    </div>

    <div class="panel-content">
      <ElForm :model="formData" label-width="80px" size="small">
        <ElFormItem label="节点类型">
          <ElSelect v-model="formData.type" placeholder="请选择节点类型" @change="handleTypeChange">
            <ElOption
              v-for="type in nodeTypes"
              :key="type.id"
              :label="type.name"
              :value="type.code"
            />
          </ElSelect>
        </ElFormItem>

        <ElFormItem label="节点名称">
          <ElInput v-model="formData.label" placeholder="请输入节点名称" />
        </ElFormItem>

        <ElFormItem label="位置参数">
          <ElInput v-model="formData.args" placeholder="多个参数用逗号分隔，如: arg1, arg2, arg3" />
          <div class="field-hint">多个参数用逗号分隔</div>
        </ElFormItem>

        <ElFormItem label="关键字参数">
          <div class="kv-editor">
            <div v-for="(row, i) in formData.kvRows" :key="i" class="kv-row">
              <ElInput v-model="row.key" placeholder="键" class="kv-row__key" />
              <ElInput
                v-model="row.value"
                :placeholder="'值（支持 {{变量}} 插值）'"
                class="kv-row__val"
              />
              <ElButton text type="danger" :icon="Delete" @click="formData.kvRows.splice(i, 1)" />
            </div>
            <ElButton
              text
              type="primary"
              :icon="Plus"
              @click="formData.kvRows.push({ key: '', value: '' })"
            >
              添加参数
            </ElButton>
          </div>
          <div class="field-hint">键值对形式的关键字参数，可变值可引用其他变量</div>
        </ElFormItem>

        <ElFormItem label="描述">
          <ElInput
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="请输入描述信息"
          />
        </ElFormItem>
      </ElForm>

      <div class="panel-actions">
        <ElButton type="primary" size="small" @click="handleSave">保存</ElButton>
        <ElButton type="danger" size="small" @click="handleDelete">删除节点</ElButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import {
  ElButton,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElMessage,
  ElIcon,
} from "element-plus";
import { Close, Delete, Plus } from "@element-plus/icons-vue";
import WorkflowNodeTypeAPI, {
  type WorkflowNodeTypeOption,
} from "@/api/module_task/workflow/node-type";

const props = defineProps({
  node: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["close", "save", "delete"]);

const nodeTypes = ref<WorkflowNodeTypeOption[]>([]);

const formData = ref({
  type: props.node?.type || "",
  label: props.node?.data?.label || "",
  args: props.node?.data?.args || "",
  kvRows: [] as { key: string; value: string }[],
  description: props.node?.data?.description || "",
});

function objToRows(obj: any): { key: string; value: string }[] {
  if (!obj || typeof obj !== "object") return [];
  return Object.entries(obj).map(([k, v]) => ({ key: k, value: String(v) }));
}
function rowsToObj(rows: { key: string; value: string }[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows || []) {
    const k = (r.key || "").trim();
    if (!k) continue;
    out[k] = r.value;
  }
  return out;
}

const loadNodeTypes = async () => {
  try {
    const res = await WorkflowNodeTypeAPI.getWorkflowNodeTypeOptions();
    if (res.data) {
      nodeTypes.value = res.data.data || [];
    }
  } catch {
    ElMessage.error("加载节点类型失败");
  }
};

const handleTypeChange = async (typeCode: string) => {
  const nodeType = nodeTypes.value.find((t) => t.code === typeCode);
  if (nodeType) {
    formData.value.args = nodeType.args || "";
    formData.value.kvRows = objToRows(nodeType.kwargs);
  }
};

watch(
  () => props.node,
  (newNode) => {
    if (newNode) {
      formData.value = {
        type: newNode.type || "",
        label: newNode.data?.label || "",
        args: newNode.data?.args || "",
        kvRows: objToRows(newNode.data?.kwargs),
        description: newNode.data?.description || "",
      };
    }
  },
  { deep: true, immediate: true }
);

function handleClose() {
  emit("close");
}

function handleSave() {
  emit("save", {
    type: formData.value.type,
    label: formData.value.label,
    args: formData.value.args,
    kwargs: rowsToObj(formData.value.kvRows),
    description: formData.value.description,
  });
  ElMessage.success("保存成功");
}

function handleDelete() {
  emit("delete");
}

onMounted(() => {
  loadNodeTypes();
  if (props.node?.type) {
    handleTypeChange(props.node.type);
  }
});
</script>

<style scoped>
.node-config-panel {
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

.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
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
.kv-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kv-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.kv-row__key {
  width: 40%;
}
.kv-row__val {
  flex: 1;
}
</style>
