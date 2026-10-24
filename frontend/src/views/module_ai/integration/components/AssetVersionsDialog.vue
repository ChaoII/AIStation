<!-- 资产版本管理：展示某表的版本历史，可发布、可回滚（复用后端 /assets/{table}/versions 等接口） -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="`${t('ai_workflow.ig_assetVersionsTitle')} · ${table || ''}`"
    width="900px"
    append-to-body
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-loading="loading">
      <el-alert
        v-if="!releases.length"
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_workflow.ig_assetVersionsHint')"
        style="margin-bottom: 12px"
      />
      <div v-if="releases.length" class="av-releases">
        <span class="av-releases__label">{{ t("ai_workflow.ig_assetVersionsReleased") }}</span>
        <el-tag
          v-for="r in releases"
          :key="r.id"
          size="small"
          type="success"
          effect="plain"
          style="margin: 0 2px"
        >
          V{{ r.version }}
        </el-tag>
      </div>
      <el-table :data="versions" size="small" border max-height="60vh" stripe>
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_assetVersionsEmpty')" :image-size="60" />
        </template>
        <el-table-column :label="t('ai_workflow.ig_version')" width="80" align="center">
          <template #default="{ row }">V{{ row.version }}</template>
        </el-table-column>
        <el-table-column
          :label="t('ai_workflow.ig_chineseName')"
          min-width="110"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.snapshot?.alias || "-" }}</template>
        </el-table-column>
        <el-table-column
          :label="t('ai_workflow.ig_businessDomain')"
          width="90"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.snapshot?.domain || "-" }}</template>
        </el-table-column>
        <el-table-column
          :label="t('ai_workflow.ig_description')"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.snapshot?.description || "-" }}</template>
        </el-table-column>
        <el-table-column prop="operator" :label="t('ai_workflow.ig_operator')" width="80" />
        <el-table-column
          prop="time"
          :label="t('ai_workflow.ig_time')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          :label="t('ai_workflow.ig_action')"
          width="180"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button icon="Upload" link type="primary" size="small" @click="publish(row)">
              {{ t("ai_workflow.ig_publish") }}
            </el-button>
            <el-button icon="RefreshLeft" link type="danger" size="small" @click="rollback(row)">
              {{ t("ai_workflow.ig_rollback") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";

import {
  getAssetVersions,
  getAssetReleases,
  publishAsset,
  rollbackAssetVersion,
} from "@/api/module_ai/query";

defineOptions({ name: "AssetVersionsDialog" });

const props = defineProps<{ modelValue: boolean; table?: string }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();
const { t } = useI18n();

const loading = ref(false);
const versions = ref<any[]>([]);
const releases = ref<any[]>([]);

async function load() {
  loading.value = true;
  try {
    const [v, r] = await Promise.all([
      getAssetVersions(props.table || ""),
      getAssetReleases(props.table || ""),
    ]);
    versions.value = v.data?.data || [];
    releases.value = r.data?.data || [];
  } catch {
    versions.value = [];
    releases.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load();
  }
);

function publish(row: any) {
  ElMessageBox.confirm(
    t("ai_workflow.ig_publishConfirm", { version: row.version }),
    t("ai_workflow.ig_publishConfirmTitle"),
    {
      confirmButtonText: t("ai_workflow.ig_publish"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
      type: "warning",
    }
  ).then(async () => {
    await publishAsset(props.table || "", row.id);
    ElMessage.success(t("ai_workflow.ig_published"));
    load();
  });
}

function rollback(row: any) {
  ElMessageBox.confirm(
    t("ai_workflow.ig_rollbackConfirm", { version: row.version }),
    t("ai_workflow.ig_rollbackConfirmTitle"),
    {
      confirmButtonText: t("ai_workflow.ig_rollback"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
      type: "warning",
    }
  ).then(async () => {
    await rollbackAssetVersion(row.id);
    ElMessage.success(t("ai_workflow.ig_rolledBack"));
    load();
  });
}
</script>

<style lang="scss" scoped>
.av-releases {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
  font-size: 12px;
}
.av-releases__label {
  color: var(--el-text-color-secondary);
}
</style>
