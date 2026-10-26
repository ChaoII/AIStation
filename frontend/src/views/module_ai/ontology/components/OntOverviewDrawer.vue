<!--
  本体概览抽屉
  收纳原本体页「概览」内容：演示数据 / 统计 / 数据源导入 / 行业模板。
  数据与动作走 useOntologyData 与现有 API，暂存/落库逻辑复用。
-->
<template>
  <div class="ont-overview">
    <!-- 演示数据 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.demoData") }}</span>
          <el-tag size="small" effect="plain" :type="demoStatus?.loaded ? 'success' : 'info'">
            {{
              demoStatus?.loaded
                ? i18nT("ai_ontology.demoLoadedCount", { count: demoStatus?.total ?? 0 })
                : i18nT("ai_ontology.demoNotLoaded")
            }}
          </el-tag>
        </div>
      </template>
      <div class="ont-overview__row">
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          type="primary"
          :loading="demoBusy"
          @click="doLoadDemo(false)"
        >
          {{ i18nT("ai_ontology.loadDemoData") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          :loading="demoBusy"
          @click="doLoadDemo(true)"
        >
          {{ i18nT("ai_ontology.clearThenLoad") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          type="danger"
          plain
          :disabled="!demoStatus?.loaded"
          :loading="demoBusy"
          @click="doClearDemo"
        >
          {{ i18nT("ai_ontology.clearDemoData") }}
        </el-button>
      </div>
      <el-alert
        v-if="demoReport"
        type="info"
        :closable="false"
        class="ont-overview__hint"
        :title="i18nT('ai_ontology.loadedDemoResources')"
      >
        <template #default>
          <span v-for="(n, k) in demoReport" :key="k" class="ont-overview__hint-item">
            {{ labelOfReport(k) }}：
            <b>{{ n }}</b>
          </span>
        </template>
      </el-alert>
    </el-card>

    <!-- 统计 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.stats") }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col v-for="s in homeStats" :key="s.label" :xs="12" :sm="8" :md="6">
          <div class="ont-overview__stat">
            <div class="ont-overview__stat-value">{{ s.value }}</div>
            <div class="ont-overview__stat-label">{{ s.label }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据源导入 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.dataSourceImport") }}</span>
        </div>
      </template>
      <el-form label-width="90px" label-position="left" size="small">
        <el-form-item :label="i18nT('ai_ontology.dataSource')">
          <el-select
            v-model="impDs"
            :placeholder="i18nT('ai_ontology.selectDataSource')"
            style="width: 100%"
            @change="onImportDsChange"
          >
            <el-option
              v-for="d in datasources"
              :key="d.id"
              :label="
                i18nT('ai_ontology.tableCountOption', { name: d.name, count: d.table_count ?? 0 })
              "
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.toImport')">
          <span class="ont-overview__muted">
            {{ i18nT("ai_ontology.tablesCount", { count: impTableCount }) }}
          </span>
        </el-form-item>
        <el-form-item label="">
          <el-checkbox v-model="impIncludeTechnical">
            {{ i18nT("ai_ontology.includeTechnicalFields2") }}
          </el-checkbox>
        </el-form-item>
        <el-form-item label="">
          <el-button size="small" type="primary" :loading="impLoading" @click="doBatchImport">
            {{ i18nT("ai_ontology.importObjectsByDataSource") }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 行业模板 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.industryTemplate") }}</span>
        </div>
      </template>
      <div class="ont-overview__tpl">
        <div v-for="t in industryTemplates" :key="t.id" class="ont-overview__tpl-item">
          <div class="ont-overview__tpl-info">
            <div class="ont-overview__tpl-name">{{ t.name }}</div>
            <div class="ont-overview__muted">{{ t.description || "—" }}</div>
          </div>
          <el-button size="small" :loading="tplLoading === t.id" @click="applyTemplate(t)">
            {{ i18nT("ai_ontology.apps") }}
          </el-button>
        </div>
        <el-empty
          v-if="!industryTemplates.length"
          :image-size="40"
          :description="i18nT('ai_ontology.noIndustryTemplates')"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useOntologyData } from "../composables/useOntologyData";
import {
  getOntDemoStatus,
  getOntDemoReport,
  loadOntDemo,
  clearOntDemo,
} from "@/api/module_ai/ontology";
import {
  getQueryDatasources,
  getQueryDatasourceSchema,
  importDsAsOntologyBatch,
  getIndustryTemplates,
  applyIndustryTemplate,
} from "@/api/module_ai/query";

const { t: i18nT } = useI18n();

const {
  scopedObjects,
  scopedLinks,
  scopedActions,
  scopedFunctions,
  scopedProperties,
  healthIssues,
  reloadAll,
} = useOntologyData();

/* ---------------- 统计 ---------------- */
const homeStats = computed(() => [
  { label: i18nT("ai_ontology.objectType"), value: scopedObjects.value.length },
  { label: i18nT("ai_ontology.property"), value: scopedProperties.value },
  { label: i18nT("ai_ontology.relationType"), value: scopedLinks.value.length },
  { label: i18nT("ai_ontology.actionType"), value: scopedActions.value.length },
  { label: i18nT("ai_ontology.function"), value: scopedFunctions.value.length },
  { label: i18nT("ai_ontology.healthIssues"), value: healthIssues.value.length },
]);

/* ---------------- 演示数据 ---------------- */
const demoStatus = ref<any>(null);
const demoReport = ref<any>(null);
const demoBusy = ref(false);

const reportLabel: Record<string, string> = {
  objects: i18nT("ai_ontology.object"),
  links: i18nT("ai_ontology.relation"),
  actions: i18nT("ai_ontology.action"),
  functions: i18nT("ai_ontology.function"),
  domains: i18nT("ai_ontology.ontology"),
  views: i18nT("ai_ontology.view"),
  indexes: i18nT("ai_ontology.index"),
  proposals: i18nT("ai_ontology.proposal"),
  scenarios: i18nT("ai_ontology.scenario"),
  decisions: i18nT("ai_ontology.decision"),
};
function labelOfReport(k: string | number) {
  return reportLabel[String(k)] || String(k);
}

async function refreshDemo() {
  try {
    const s = await getOntDemoStatus();
    demoStatus.value = s.data?.data || null;
    if (demoStatus.value?.loaded) {
      const r = await getOntDemoReport();
      demoReport.value = r.data?.data?.pages || null;
    } else {
      demoReport.value = null;
    }
  } catch {
    demoStatus.value = null;
  }
}
async function doLoadDemo(force: boolean) {
  if (force) {
    await ElMessageBox.confirm(
      i18nT("ai_ontology.clearsLoadedDemoDataThenLoadsAFreshCopyYourOwnWorkIsUntouchedConfirm"),
      i18nT("ai_ontology.clearThenLoad"),
      {
        type: "warning",
        confirmButtonText: i18nT("ai_ontology.continue"),
        cancelButtonText: i18nT("ai_ontology.cancel"),
      }
    );
  }
  demoBusy.value = true;
  try {
    const r = await loadOntDemo(force);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || i18nT("ai_ontology.loaded"));
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadFailed2"));
  } finally {
    demoBusy.value = false;
  }
}
async function doClearDemo() {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.willDeleteLoadedDemoItems", { count: demoStatus.value?.total ?? 0 }) +
      i18nT(
        "ai_ontology.includesDemoObjectViewsIndexesProposalsScenariosDecisionsRowPoliciesAndResourcePermissions"
      ) +
      i18nT("ai_ontology.onlyRegisteredDemoItemsAreRemovedYourOwnWorkStaysClear"),
    i18nT("ai_ontology.clearDemoData"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.clear"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  demoBusy.value = true;
  try {
    const r = await clearOntDemo();
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.cleared"));
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.clearFailed"));
  } finally {
    demoBusy.value = false;
  }
}

/* ---------------- 数据源导入 ---------------- */
const datasources = ref<any[]>([]);
const impDs = ref<number | null>(null);
const impTableCount = ref(0);
const impIncludeTechnical = ref(false);
const impLoading = ref(false);

async function loadImportPanel() {
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

/* ---------------- 行业模板 ---------------- */
const industryTemplates = ref<any[]>([]);
const tplLoading = ref("");

async function loadTemplates() {
  try {
    const t = await getIndustryTemplates();
    industryTemplates.value = t.data?.data || [];
  } catch {
    industryTemplates.value = [];
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

onMounted(() => {
  refreshDemo();
  loadImportPanel();
  loadTemplates();
});
</script>

<style scoped lang="scss">
.ont-overview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ont-overview__card :deep(.el-card__header) {
  padding: 10px 14px;
}
.ont-overview__row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.ont-overview__hint {
  margin-top: 10px;
}
.ont-overview__hint-item {
  margin-right: 14px;
}
.ont-overview__stat {
  text-align: center;
  margin-bottom: 10px;
}
.ont-overview__stat-value {
  font-size: var(--el-font-size-large);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-overview__stat-label {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-secondary);
}
.ont-overview__muted {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.ont-overview__tpl {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ont-overview__tpl-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
}
.ont-overview__tpl-info {
  flex: 1;
  min-width: 0;
}
.ont-overview__tpl-name {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}
</style>
