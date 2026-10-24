<!--
  对象类型 → 导入 / 导出 子页
  说明：导出/导入作用于「当前整个本体（domain）」，不限于本对象类型；在详情页提供入口仅为集中管理。
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">{{ i18nT("ai_ontology.importExportTitle") }}</span>
    </div>
    <el-alert
      type="warning"
      :closable="false"
      class="ont-obj__note"
      :title="i18nT('ai_ontology.exportImportDomainNote', { name: currentDomainName })"
    />

    <!-- 导出 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">{{ i18nT("ai_ontology.exportOntology") }}</div>
      <el-button size="small" type="primary" :loading="transferLoading" @click="doExport">
        {{ i18nT("ai_ontology.exportJson") }}
      </el-button>
      <span class="ont-hint">{{ i18nT("ai_ontology.exportJsonHint") }}</span>
    </div>

    <!-- 导入 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">{{ i18nT("ai_ontology.importOntology") }}</div>
      <el-upload :show-file-list="false" :auto-upload="false" accept=".json" @change="onImportFile">
        <el-button size="small" :icon="Upload">{{ i18nT("ai_ontology.selectJsonFile") }}</el-button>
      </el-upload>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="6"
        class="ont-imp__area"
        :placeholder="i18nT('ai_ontology.importTextPlaceholder')"
      />
      <div class="ont-imp__actions">
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :loading="transferLoading"
          @click="doImport('stage')"
        >
          {{ i18nT("ai_ontology.stageImport") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          type="danger"
          :loading="transferLoading"
          @click="doImport('apply')"
        >
          {{ i18nT("ai_ontology.importDirectly") }}
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-obj__note"
        :title="i18nT('ai_ontology.stageImportNote')"
      />
    </div>

    <!-- 数据源批量导入 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">{{ i18nT("ai_ontology.batchImportFromDataSource") }}</div>
      <div class="ont-imp__row">
        <el-select
          v-model="impDs"
          size="small"
          filterable
          :placeholder="i18nT('ai_ontology.selectDataSource')"
          style="width: 260px"
          @change="onImportDsChange"
        >
          <el-option
            v-for="d in datasources"
            :key="d.id"
            :label="i18nT('ai_ontology.tableCountOption', { name: d.name, count: d.table_count })"
            :value="d.id"
          />
        </el-select>
        <el-tag v-if="impDs" size="small" effect="plain">
          {{ i18nT("ai_ontology.tablesCount", { count: impTableCount }) }}
        </el-tag>
        <el-checkbox v-model="impIncludeTechnical" size="small">
          {{ i18nT("ai_ontology.includeTechnicalFields") }}
        </el-checkbox>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          type="primary"
          :disabled="!impDs"
          :loading="impLoading"
          @click="doBatchImport"
        >
          {{ i18nT("ai_ontology.startImport") }}
        </el-button>
      </div>
      <span class="ont-hint">
        {{ i18nT("ai_ontology.generateObjectTypesAndPropertiesByMappingDataSourceColumns") }}
      </span>
    </div>

    <!-- 行业模板 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">{{ i18nT("ai_ontology.applyIndustryTemplate") }}</div>
      <div v-for="t in industryTemplates" :key="t.id" class="ont-imp__template">
        <div class="ont-imp__template-info">
          <div class="ont-imp__template-name">{{ t.name }}</div>
          <div class="ont-hint">{{ t.description }}</div>
        </div>
        <el-button
          size="small"
          type="primary"
          :loading="tplLoading === t.id"
          @click="applyTemplate(t)"
        >
          {{ i18nT("ai_ontology.apps") }}
        </el-button>
      </div>
      <el-empty
        v-if="!industryTemplates.length"
        :image-size="40"
        :description="i18nT('ai_ontology.noIndustryTemplates')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import { exportOntology, importOntology } from "@/api/module_ai/ontology";
import {
  getQueryDatasources,
  getQueryDatasourceSchema,
  importDsAsOntologyBatch,
  getIndustryTemplates,
  applyIndustryTemplate,
} from "@/api/module_ai/query";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

defineProps<{ code: string }>();

const { currentDomain, currentDomainName, reloadAll, refreshWip } = useOntologyData();

const transferLoading = ref(false);
const importText = ref("");

const datasources = ref<any[]>([]);
const impDs = ref<number | null>(null);
const impTableCount = ref(0);
const impIncludeTechnical = ref(false);
const impLoading = ref(false);

const industryTemplates = ref<any[]>([]);
const tplLoading = ref("");

async function doExport() {
  transferLoading.value = true;
  try {
    const r = await exportOntology(currentDomain.value || undefined);
    const data = r.data?.data || {};
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ontology-${data.domain_code || "all"}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    const c = data.counts || {};
    ElMessage.success(
      i18nT("ai_ontology.exportSummary", {
        objects: c.objects || 0,
        properties: c.properties || 0,
        links: c.links || 0,
        actions: c.actions || 0,
      })
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.exportFailed"));
  } finally {
    transferLoading.value = false;
  }
}

async function doImport(mode: "stage" | "apply") {
  let payload: any;
  try {
    payload = JSON.parse(importText.value || "{}");
  } catch {
    return ElMessage.error(i18nT("ai_ontology.jsonParseFailedCheckContent"));
  }
  if (!payload.objects) return ElMessage.error(i18nT("ai_ontology.notValidOntologyMissingObjects"));
  if (mode === "apply") {
    try {
      await ElMessageBox.confirm(
        i18nT("ai_ontology.importDirectlyConfirm"),
        i18nT("ai_ontology.importDirectly"),
        {
          type: "warning",
          confirmButtonText: i18nT("ai_ontology.importDirectly"),
          cancelButtonText: i18nT("ai_ontology.cancel"),
        }
      );
    } catch {
      return;
    }
  }
  transferLoading.value = true;
  try {
    const r = await importOntology(payload, mode);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.imported"));
    await reloadAll();
    await refreshWip();
    if (mode === "stage") importText.value = "";
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.importFailed"));
  } finally {
    transferLoading.value = false;
  }
}

async function onImportFile(uploadFile: UploadFile) {
  const f = uploadFile.raw;
  if (!f) return;
  importText.value = await f.text();
}

async function loadPanel() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
    if (!impDs.value && datasources.value.length) {
      const best = [...datasources.value].sort(
        (a: any, b: any) => (b.table_count || 0) - (a.table_count || 0)
      )[0];
      impDs.value = best.id;
      await onImportDsChange(impDs.value);
    }
  } catch {
    datasources.value = [];
  }
  try {
    const t = await getIndustryTemplates();
    industryTemplates.value = t.data?.data || [];
  } catch {
    industryTemplates.value = [];
  }
}

async function onImportDsChange(id: number | null) {
  if (!id) {
    impTableCount.value = 0;
    return;
  }
  try {
    const r = await getQueryDatasourceSchema(id);
    impTableCount.value = (r.data?.data || []).length;
  } catch {
    impTableCount.value = 0;
  }
}

async function doBatchImport() {
  if (!impDs.value) return;
  impLoading.value = true;
  try {
    const r = await importDsAsOntologyBatch(impDs.value, null, impIncludeTechnical.value);
    const d = r.data?.data || {};
    ElMessage.success(
      r.data?.msg || i18nT("ai_ontology.importedObjects", { count: d.imported ?? 0 })
    );
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.importFailed"));
  } finally {
    impLoading.value = false;
  }
}

async function applyTemplate(t: any) {
  tplLoading.value = t.id;
  try {
    const r = await applyIndustryTemplate(t.id);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.appliedTemplate", { name: t.name }));
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.applyFailed"));
  } finally {
    tplLoading.value = "";
  }
}

onMounted(loadPanel);
</script>

<style scoped lang="scss">
.ont-obj__note {
  margin-bottom: 8px;
}
.ont-imp__block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.ont-imp__area {
  margin-top: 8px;
}
.ont-imp__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.ont-imp__row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 8px;
}
.ont-imp__template {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ont-imp__template-name {
  font-size: var(--el-font-size-base);
  font-weight: 500;
}
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
</style>
