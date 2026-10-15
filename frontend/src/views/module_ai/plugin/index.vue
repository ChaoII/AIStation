<!-- AI 能力插件：内置能力包列表 + 启停 + 配置 -->
<template>
  <div class="app-container ai-plugin-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="search-input"
          :prefix-icon="Search"
          placeholder="搜索插件名称或标识"
          clearable
        />
        <el-button
          v-hasPerm="['module_ai:plugin:create']"
          type="primary"
          :icon="Plus"
          @click="openDialog()"
        >
          新增插件
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          共 {{ filtered.length }} 个 · 启用 {{ enabledCount }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="filtered" border stripe>
        <el-table-column label="插件" min-width="200">
          <template #default="{ row }">
            <span class="plugin-label">{{ row.label || row.key }}</span>
            <div class="plugin-key">{{ row.key }}</div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.kind === "builtin" ? "内置" : "自定义" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行器" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.executor_ready ? 'success' : 'info'" effect="plain">
              {{ row.executor_ready ? "已就绪" : "未实现" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || "—" }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :disabled="!canUpdate"
              @change="(v: any) => toggle(row as any, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-hasPerm="['module_ai:plugin:update']"
              size="small"
              :icon="Edit"
              @click="openDialog(row as any)"
            >
              编辑
            </el-button>
            <el-button
              v-hasPerm="['module_ai:plugin:delete']"
              size="small"
              type="danger"
              :icon="Delete"
              @click="removePlugin(row as any)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filtered.length" description="暂无能力插件" />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑能力插件' : '新增能力插件'"
      width="560px"
      append-to-body
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
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Delete, Edit, Plus, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type FormInstance } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import {
  createPlugin,
  deletePlugin,
  getPluginList,
  togglePlugin,
  updatePlugin,
  type AiPlugin,
} from "@/api/module_ai/plugin";
import { ROLE_ROOT } from "@/constants";
import { useUserStore } from "@/store";

defineOptions({ name: "AiPlugin" });

const userStore = useUserStore();
const canUpdate = computed(() => {
  const roles = userStore.basicInfo.roles?.map((r) => r.code) || [];
  return roles.includes(ROLE_ROOT) || userStore.prems.includes("module_ai:plugin:update");
});

const loading = ref(false);
const rows = ref<AiPlugin[]>([]);
const keyword = ref("");

const dialogVisible = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ id: 0, key: "", label: "", description: "", enabled: true });
const configText = ref("{}");

const rules = {
  key: [{ required: true, message: "请输入插件标识", trigger: "blur" }],
  label: [{ required: true, message: "请输入名称", trigger: "blur" }],
};

const filtered = computed(() =>
  rows.value.filter(
    (r) =>
      !keyword.value || r.key.includes(keyword.value) || (r.label || "").includes(keyword.value)
  )
);
const enabledCount = computed(() => rows.value.filter((r) => r.enabled).length);

async function load() {
  loading.value = true;
  try {
    const res: any = await getPluginList();
    rows.value = res.data || [];
  } finally {
    loading.value = false;
  }
}

function openDialog(row?: AiPlugin) {
  if (row) {
    form.id = row.id;
    form.key = row.key;
    form.label = row.label;
    form.description = row.description;
    form.enabled = row.enabled;
    configText.value = JSON.stringify(row.config || {}, null, 2);
  } else {
    form.id = 0;
    form.key = "";
    form.label = "";
    form.description = "";
    form.enabled = true;
    configText.value = "{}";
  }
  dialogVisible.value = true;
}

async function save() {
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
    dialogVisible.value = false;
    load();
  } finally {
    saving.value = false;
  }
}

async function toggle(row: AiPlugin, value: any) {
  const enabled = Boolean(value);
  await togglePlugin(row.id, enabled);
  row.enabled = enabled;
  ElMessage.success(enabled ? "已启用" : "已停用");
}

async function removePlugin(row: AiPlugin) {
  await ElMessageBox.confirm(
    `将删除能力插件「${row.label || row.key}」，已启用它的智能体将失去该能力。是否继续？`,
    "删除确认",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  );
  await deletePlugin([row.id]);
  ElMessage.success("删除成功");
  load();
}

onMounted(load);
</script>

<style lang="scss" scoped>
.toolbar-card {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  width: 240px;
}

.plugin-label {
  font-weight: 500;
}

.plugin-key {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
