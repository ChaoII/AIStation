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
          <span class="ont-sec__title">演示数据</span>
          <el-tag
            size="small"
            effect="plain"
            :type="demoStatus?.loaded ? 'success' : 'info'"
          >
            {{ demoStatus?.loaded ? `已载入 ${demoStatus?.total ?? 0} 项` : "未载入" }}
          </el-tag>
        </div>
      </template>
      <div class="ont-overview__row">
        <el-button size="small" type="primary" :loading="demoBusy" @click="doLoadDemo(false)">
          载入演示数据
        </el-button>
        <el-button size="small" :loading="demoBusy" @click="doLoadDemo(true)">
          先清除再载入
        </el-button>
        <el-button
          size="small"
          type="danger"
          plain
          :disabled="!demoStatus?.loaded"
          :loading="demoBusy"
          @click="doClearDemo"
        >
          清除演示数据
        </el-button>
      </div>
      <el-alert
        v-if="demoReport"
        type="info"
        :closable="false"
        class="ont-overview__hint"
        title="已载入的演示资源"
      >
        <template #default>
          <span v-for="(n, k) in demoReport" :key="k" class="ont-overview__hint-item">
            {{ labelOfReport(k) }}：<b>{{ n }}</b>
          </span>
        </template>
      </el-alert>
    </el-card>

    <!-- 统计 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head"><span class="ont-sec__title">统计</span></div>
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
        <div class="ont-sec__head"><span class="ont-sec__title">数据源导入</span></div>
      </template>
      <el-form label-width="90px" label-position="left" size="small">
        <el-form-item label="数据源">
          <el-select v-model="impDs" placeholder="选择数据源" style="width: 100%" @change="onImportDsChange">
            <el-option
              v-for="d in datasources"
              :key="d.id"
              :label="`${d.name}（${d.table_count ?? 0} 表）`"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="待导入">
          <span class="ont-overview__muted">{{ impTableCount }} 张表</span>
        </el-form-item>
        <el-form-item label="">
          <el-checkbox v-model="impIncludeTechnical">包含技术字段</el-checkbox>
        </el-form-item>
        <el-form-item label="">
          <el-button size="small" type="primary" :loading="impLoading" @click="doBatchImport">
            按数据源导入对象
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 行业模板 -->
    <el-card shadow="never" class="ont-overview__card">
      <template #header>
        <div class="ont-sec__head"><span class="ont-sec__title">行业模板</span></div>
      </template>
      <div class="ont-overview__tpl">
        <div v-for="t in industryTemplates" :key="t.id" class="ont-overview__tpl-item">
          <div class="ont-overview__tpl-info">
            <div class="ont-overview__tpl-name">{{ t.name }}</div>
            <div class="ont-overview__muted">{{ t.description || "—" }}</div>
          </div>
          <el-button
            size="small"
            :loading="tplLoading === t.id"
            @click="applyTemplate(t)"
          >
            应用
          </el-button>
        </div>
        <el-empty v-if="!industryTemplates.length" :image-size="40" description="暂无行业模板" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
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
  { label: "对象类型", value: scopedObjects.value.length },
  { label: "属性", value: scopedProperties.value },
  { label: "关系类型", value: scopedLinks.value.length },
  { label: "动作类型", value: scopedActions.value.length },
  { label: "函数", value: scopedFunctions.value.length },
  { label: "健康问题", value: healthIssues.value.length },
]);

/* ---------------- 演示数据 ---------------- */
const demoStatus = ref<any>(null);
const demoReport = ref<any>(null);
const demoBusy = ref(false);

const reportLabel: Record<string, string> = {
  objects: "对象",
  links: "关系",
  actions: "动作",
  functions: "函数",
  domains: "本体",
  views: "视图",
  indexes: "索引",
  proposals: "提案",
  scenarios: "场景",
  decisions: "决策",
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
      "将先清除已载入的演示数据，再重新载入一份新的。你自己建的东西不受影响。确认？",
      "先清除再载入",
      { type: "warning", confirmButtonText: "继续", cancelButtonText: "取消" }
    );
  }
  demoBusy.value = true;
  try {
    const r = await loadOntDemo(force);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || "已载入");
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "载入失败");
  } finally {
    demoBusy.value = false;
  }
}
async function doClearDemo() {
  await ElMessageBox.confirm(
    `将删除已载入的 ${demoStatus.value?.total ?? 0} 项演示数据` +
      "（含演示用的对象视图、索引、提案、场景、决策、行级策略与资源权限）。" +
      "只删登记过的演示项，你自己建的东西不动。确认清除？",
    "清除演示数据",
    { type: "warning", confirmButtonText: "清除", cancelButtonText: "取消" }
  );
  demoBusy.value = true;
  try {
    const r = await clearOntDemo();
    ElMessage.success(r.data?.msg || "已清除");
    await refreshDemo();
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "清除失败");
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
    ElMessage.success(r.data?.msg || `已导入 ${d.imported ?? 0} 个对象`);
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
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
    ElMessage.success(r.data?.msg || `已应用模板「${t.name}」`);
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "应用失败");
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
  font-size: 12px;
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
