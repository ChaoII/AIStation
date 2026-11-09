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
      <div class="av-bar">
        <span class="av-bar__hint">
          {{ t("ai_workflow.ig_diffSelected", { n: selected.length }) }}
        </span>
        <el-button type="primary" size="small" :disabled="selected.length !== 2" @click="openDiff">
          {{ t("ai_workflow.ig_diffCompare") }}
        </el-button>
      </div>
      <el-table
        :data="versions"
        size="small"
        border
        max-height="60vh"
        stripe
        row-key="id"
        @selection-change="onSelectionChange"
      >
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_assetVersionsEmpty')" :image-size="60" />
        </template>
        <el-table-column type="selection" width="42" reserve-selection />
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

  <el-dialog
    v-model="diffVisible"
    :title="t('ai_workflow.ig_diffTitle')"
    width="760px"
    append-to-body
  >
    <el-alert
      v-if="diffData"
      :type="diffData.changed_count ? 'warning' : 'success'"
      :closable="false"
      show-icon
      :title="
        diffData.changed_count
          ? t('ai_workflow.ig_diffCount', { n: diffData.changed_count })
          : t('ai_workflow.ig_diffNone')
      "
      :description="
        diffData ? `V${diffData.version_a} ↔ V${diffData.version_b} · ${diffData.table || ''}` : ''
      "
    />
    <el-table
      v-if="diffData && diffData.changed?.length"
      :data="diffData.changed"
      size="small"
      border
      stripe
      max-height="50vh"
      style="margin-top: 12px"
    >
      <el-table-column
        prop="key"
        :label="t('ai_workflow.ig_diffField')"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column :label="t('ai_workflow.ig_diffFrom')" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ fmt(row.from) }}</template>
      </el-table-column>
      <el-table-column :label="t('ai_workflow.ig_diffTo')" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ fmt(row.to) }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="diffVisible = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";

import {
  getAssetVersionDiff,
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

const selected = ref<any[]>([]);
const diffVisible = ref(false);
const diffData = ref<any>(null);

function onSelectionChange(rows: any[]) {
  // 只允许对比两个版本：超过 2 个时保留最近选中的两个
  selected.value = rows.length <= 2 ? rows : rows.slice(-2);
}

function fmt(v: any) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

async function openDiff() {
  if (selected.value.length !== 2) {
    ElMessage.warning(t("ai_workflow.ig_diffNeedTwo"));
    return;
  }
  const [a, b] = selected.value;
  try {
    const r: any = await getAssetVersionDiff(a.id, b.id);
    const d = r.data?.data || null;
    if (!d || d.ok === false) {
      ElMessage.warning(d?.msg || t("ai_workflow.ig_loadFail"));
      return;
    }
    diffData.value = d;
    diffVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_workflow.ig_loadFail"));
  }
}

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
    if (open) {
      selected.value = [];
      diffData.value = null;
      load();
    }
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
.av-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.av-bar__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
