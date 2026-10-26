<!-- MCP 服务器创建/编辑对话框：stdio/sse/http + 连接测试。
     由「能力市场 → 我的资产」挂载，复用原 MCP 管理逻辑并精简为对话框形态。 -->
<template>
  <el-dialog
    v-model="visible"
    :title="props.realId ? t('ai_market.editMcp') : t('ai_market.createMcp')"
    width="600px"
    append-to-body
    destroy-on-close
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item :label="t('ai_market.nameLabel')" prop="name">
        <el-input
          v-model="form.name"
          maxlength="128"
          :placeholder="t('ai_market.mcpNamePlaceholder')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_market.transportLabel')" prop="transport">
        <el-radio-group v-model="form.transport">
          <el-radio-button value="stdio">stdio</el-radio-button>
          <el-radio-button value="sse">sse</el-radio-button>
          <el-radio-button value="streamable-http">streamable-http</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <template v-if="form.transport === 'stdio'">
        <el-form-item :label="t('ai_market.commandLabel')" prop="command">
          <el-input v-model="form.command" :placeholder="t('ai_market.commandPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_market.argsLabel')">
          <el-input
            v-model="argsText"
            type="textarea"
            :rows="2"
            :placeholder="t('ai_market.argsPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.envLabel')">
          <el-input
            v-model="envText"
            type="textarea"
            :rows="2"
            :placeholder="t('ai_market.envPlaceholder')"
          />
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item :label="t('ai_market.urlLabel')" prop="url">
          <el-input v-model="form.url" placeholder="https://example.com/mcp" />
        </el-form-item>
        <el-form-item :label="t('ai_market.requestHeaders')">
          <el-input
            v-model="headersText"
            type="textarea"
            :rows="2"
            :placeholder="t('ai_market.headersPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.authLabel')">
          <el-select v-model="form.auth_type" class="full-width">
            <el-option :label="t('ai_market.authNone')" value="none" />
            <el-option label="Bearer Token" value="bearer" />
            <el-option :label="t('ai_market.authCustom')" value="custom" />
          </el-select>
        </el-form-item>
      </template>

      <el-form-item :label="t('ai_market.description')">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
      </el-form-item>
      <el-form-item :label="t('ai_market.enableLabel')">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button v-if="props.realId" :loading="testing" @click="handleTest">
        {{ t("ai_market.test") }}
      </el-button>
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

import { createMcp, getMcpDetail, testMcp, updateMcp } from "@/api/module_ai/mcp";

const props = defineProps<{ modelValue: boolean; realId?: number | null }>();
const emit = defineEmits<{ "update:modelValue": [v: boolean]; saved: [] }>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const saving = ref(false);
const testing = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({
  id: 0,
  name: "",
  transport: "streamable-http",
  command: "",
  url: "",
  auth_type: "none",
  description: "",
  enabled: true,
});
const argsText = ref("");
const envText = ref("");
const headersText = ref("");

const rules = {
  name: [{ required: true, message: t("ai_market.requiredName"), trigger: "blur" }],
  command: [{ required: true, message: t("ai_market.requireStdioCommand"), trigger: "blur" }],
  url: [{ required: true, message: t("ai_market.requireUrl"), trigger: "blur" }],
};

function parseLines(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseKv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of parseLines(text)) {
    const idx = line.indexOf("=");
    if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return out;
}

function resetForm() {
  form.id = 0;
  form.name = "";
  form.transport = "streamable-http";
  form.command = "";
  form.url = "";
  form.auth_type = "none";
  form.description = "";
  form.enabled = true;
  argsText.value = "";
  envText.value = "";
  headersText.value = "";
}

async function loadForEdit() {
  if (!props.realId) return;
  try {
    const res: any = await getMcpDetail(props.realId);
    const row = res.data?.data;
    if (!row) return;
    form.id = row.id;
    form.name = row.name;
    form.transport = row.transport;
    form.command = row.command;
    form.url = row.url;
    form.auth_type = row.auth_type;
    form.description = row.description;
    form.enabled = row.enabled;
    argsText.value = (row.args || []).join("\n");
    envText.value = Object.entries(row.env || {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
    headersText.value = Object.entries(row.headers || {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
  } catch {
    /* 详情加载失败时保留空表单 */
  }
}

async function handleSave() {
  if (!formRef.value) return;
  await formRef.value.validate();
  const payload: any = {
    name: form.name,
    transport: form.transport,
    command: form.command,
    url: form.url,
    auth_type: form.auth_type,
    description: form.description,
    enabled: form.enabled,
  };
  if (form.transport === "stdio") {
    payload.args = parseLines(argsText.value);
    payload.env = parseKv(envText.value);
    payload.url = "";
  } else {
    payload.headers = parseKv(headersText.value);
    payload.command = "";
    payload.args = [];
  }
  saving.value = true;
  try {
    if (form.id) {
      await updateMcp(form.id, payload);
      ElMessage.success(t("ai_market.updateSuccess"));
    } else {
      await createMcp(payload);
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

async function handleTest() {
  if (!form.id) return;
  testing.value = true;
  try {
    const res: any = await testMcp(form.id);
    const data = res.data?.data || {};
    if (data.reachable) {
      ElMessage.success(t("ai_market.connectOk", { detail: data.detail }));
    } else {
      ElMessage.warning(t("ai_market.connectFail", { detail: data.detail }));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_market.testFailed"));
  } finally {
    testing.value = false;
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
.full-width {
  width: 100%;
}
</style>
