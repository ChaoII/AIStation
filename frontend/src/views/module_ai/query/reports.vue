<template>
  <div class="app-container ai-query-reports">
    <el-card shadow="never">
      <template #header>
        <div class="r-head">
          <span>{{ t("ai_logs.reportTemplates") }}</span>
          <div class="r-head__ops">
            <el-select
              v-model="datasource"
              size="small"
              clearable
              :placeholder="t('ai_logs.allDatasources')"
              style="width: 180px"
              @change="load"
            >
              <el-option :label="t('ai_logs.systemDsLabel')" value="system" />
              <el-option
                v-for="d in datasources"
                :key="d.code || d.id"
                :label="d.name"
                :value="d.code || `ds:${d.id}`"
              />
            </el-select>
            <el-checkbox v-model="verifiedOnly" size="small" @change="load">
              {{ t("ai_logs.onlyConfirmed") }}
            </el-checkbox>
            <el-button size="small" @click="load">{{ t("ai_logs.refresh") }}</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.reportOrigTip')"
        class="r-tip"
      />

      <el-table v-loading="loading" :data="rows" size="small" border stripe>
        <el-table-column type="index" :label="t('ai_logs.noSign')" width="52" />
        <el-table-column
          prop="name"
          :label="t('ai_logs.reportName')"
          min-width="170"
          show-overflow-tooltip
        />
        <el-table-column
          prop="key"
          :label="t('ai_logs.reportKey')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column prop="datasource" :label="t('ai_logs.datasource')" width="90" />
        <el-table-column
          prop="question"
          :label="t('ai_logs.sourceQuestion')"
          min-width="190"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.params')" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.params || []).length" size="small" effect="plain">
              {{ row.params.length }} {{ t("ai_logs.countUnit") }}
            </el-tag>
            <span v-else class="r-dim">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.status')" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.verified" size="small" type="success">
              {{ t("ai_logs.confirmed") }}
            </el-tag>
            <el-tag v-else size="small" type="warning">{{ t("ai_logs.draft") }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.operation')" width="220" fixed="right">
          <template #default="{ row }">
            <el-button icon="VideoPlay" link type="primary" size="small" @click="openRun(row)">
              {{ t("ai_logs.run") }}
            </el-button>
            <el-button icon="Setting" link size="small" @click="openParams(row)">
              {{ t("ai_logs.params") }}
            </el-button>
            <el-button
              v-if="!row.verified"
              icon="Check"
              link
              type="success"
              size="small"
              @click="verify(row)"
            >
              {{ t("ai_logs.confirm") }}
            </el-button>
            <el-button icon="delete" link type="danger" size="small" @click="remove(row)">
              {{ t("ai_logs.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="r-total">{{ t("ai_logs.totalReports", { count: rows.length }) }}</div>
    </el-card>

    <el-dialog
      v-model="runVisible"
      :title="t('ai_logs.runReportTitle', { name: cur?.name || '' })"
      width="900px"
      append-to-body
    >
      <el-alert
        v-if="runError"
        type="error"
        :closable="false"
        show-icon
        :title="runError"
        class="r-tip"
      />
      <el-form v-if="(cur?.params || []).length" label-width="110px">
        <el-form-item
          v-for="p in cur?.params || []"
          :key="p.key"
          :label="p.label || p.key"
          :required="p.required !== false"
        >
          <el-input-number
            v-if="p.type === 'number'"
            v-model="paramValues[p.key]"
            :controls="false"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
          <el-date-picker
            v-else-if="p.type === 'date'"
            v-model="paramValues[p.key]"
            type="date"
            value-format="YYYY-MM-DD"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
          <el-input
            v-else
            v-model="paramValues[p.key]"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-else
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.noParamsTip')"
        class="r-tip"
      />
      <el-button type="primary" size="small" :loading="running" @click="doRun">
        {{ t("ai_logs.execute") }}
      </el-button>
      <el-table
        v-if="result.columns.length"
        :data="resultRows"
        size="small"
        border
        max-height="360"
        class="r-result"
        stripe
      >
        <el-table-column
          v-for="c in result.columns"
          :key="c"
          :prop="c"
          :label="c"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <template #footer>
        <el-button @click="runVisible = false">{{ t("ai_logs.close") }}</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="paramVisible"
      :title="t('ai_logs.paramDefTitle', { name: cur?.name || '' })"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.paramOriginTip')"
        class="r-tip"
      />
      <el-table :data="paramDefs" size="small" border stripe>
        <el-table-column :label="t('ai_logs.placeholderKey')" width="150">
          <template #default="{ row }">
            <el-input
              v-model="row.key"
              size="small"
              :placeholder="t('ai_logs.placeholderKeyHint')"
            />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.chineseName')" width="140">
          <template #default="{ row }">
            <el-input v-model="row.label" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.type')" width="120">
          <template #default="{ row }">
            <el-select v-model="row.type" size="small">
              <el-option :label="t('ai_logs.typeText')" value="text" />
              <el-option :label="t('ai_logs.typeNumber')" value="number" />
              <el-option :label="t('ai_logs.typeDate')" value="date" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.required')" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.required" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.defaultValue')" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.default" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.operation')" width="70" align="center">
          <template #default="{ $index }">
            <el-button
              icon="delete"
              link
              type="danger"
              size="small"
              @click="paramDefs.splice($index, 1)"
            >
              {{ t("ai_logs.remove") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button icon="Plus" link type="primary" size="small" class="r-addparam" @click="addParam">
        + {{ t("ai_logs.addParam") }}
      </el-button>
      <template #footer>
        <el-button @click="paramVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :loading="paramSaving" @click="saveParams">
          {{ t("ai_logs.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteQueryReports,
  getQueryDatasources,
  getQueryReports,
  runQueryReport,
  saveQueryReport,
  verifyQueryReport,
} from "@/api/module_ai/query";

defineOptions({ name: "AiQueryReports" });

const { t } = useI18n();

const rows = ref<any[]>([]);
const datasources = ref<any[]>([]);
const loading = ref(false);
const datasource = ref("");
const verifiedOnly = ref(false);

const runVisible = ref(false);
const running = ref(false);
const cur = ref<any>(null);
const paramValues = ref<Record<string, any>>({});
const result = ref<{ columns: string[]; rows: any[][] }>({ columns: [], rows: [] });

const resultRows = computed(() =>
  (result.value.rows || []).map((r) => {
    const o: Record<string, any> = {};
    (result.value.columns || []).forEach((c, i) => {
      o[c] = r[i];
    });
    return o;
  })
);

async function load() {
  loading.value = true;
  try {
    const params: any = {};
    if (datasource.value) params.datasource = datasource.value;
    if (verifiedOnly.value) params.verified_only = true;
    const r = await getQueryReports(params);
    rows.value = r.data?.data || [];
  } catch {
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

function openRun(row: any) {
  cur.value = row;
  runError.value = "";
  paramValues.value = {};
  (row.params || []).forEach((p: any) => {
    const hasDefault = p.default !== "" && p.default != null;
    paramValues.value[p.key] = hasDefault ? p.default : p.type === "number" ? undefined : "";
  });
  result.value = { columns: [], rows: [] };
  runVisible.value = true;
}

async function doRun() {
  if (!cur.value) return;
  // 前端先校验必填（后端同样校验：双保险，且提示更贴近操作）
  const missing = (cur.value.params || []).find((p: any) => {
    if (p.required === false) return false;
    const v = paramValues.value[p.key];
    return v === undefined || v === null || String(v).trim() === "";
  });
  if (missing) {
    runError.value = t("ai_logs.requiredParam", { name: missing.label || missing.key });
    return;
  }
  runError.value = "";
  running.value = true;
  try {
    const r = await runQueryReport(cur.value.id, paramValues.value);
    const d = r.data?.data || {};
    result.value = { columns: d.columns || [], rows: d.rows || [] };
    ElMessage.success(t("ai_logs.runDoneRows", { count: result.value.rows.length }));
  } catch (e: any) {
    runError.value = e?.msg || t("ai_logs.runFailed");
    ElMessage.error(runError.value);
  } finally {
    running.value = false;
  }
}

// —— 参数定义（占位符 key / 中文名 / 类型 / 必填 / 默认值）——
const paramVisible = ref(false);
const paramSaving = ref(false);
const paramDefs = ref<any[]>([]);
const runError = ref("");

function openParams(row: any) {
  cur.value = row;
  paramDefs.value = (row.params || []).map((p: any) => ({
    key: p.key || "",
    label: p.label || "",
    type: p.type || "text",
    required: p.required !== false,
    default: p.default ?? "",
  }));
  paramVisible.value = true;
}

function addParam() {
  paramDefs.value = [
    ...paramDefs.value,
    { key: "", label: "", type: "text", required: true, default: "" },
  ];
}

async function saveParams() {
  if (!cur.value) return;
  if (paramDefs.value.some((p) => !String(p.key || "").trim())) {
    ElMessage.warning(t("ai_logs.paramKeyRequired"));
    return;
  }
  paramSaving.value = true;
  try {
    await saveQueryReport({
      key: cur.value.key,
      name: cur.value.name,
      description: cur.value.description,
      datasource: cur.value.datasource,
      question: cur.value.question,
      sql_template: cur.value.sql_template,
      columns: cur.value.columns,
      chart: cur.value.chart,
      params: paramDefs.value,
      verified: cur.value.verified,
    });
    ElMessage.success(t("ai_logs.paramsSaved"));
    paramVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.saveFailed"));
  } finally {
    paramSaving.value = false;
  }
}

async function verify(row: any) {
  await ElMessageBox.confirm(
    t("ai_logs.confirmReportMsg", { name: row.name }),
    t("ai_logs.confirmReport"),
    {
      type: "warning",
      confirmButtonText: t("ai_logs.confirm"),
      cancelButtonText: t("ai_logs.cancel"),
    }
  );
  try {
    await verifyQueryReport(row.id);
    ElMessage.success(t("ai_logs.confirmed"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.confirmFailed"));
  }
}

async function remove(row: any) {
  await ElMessageBox.confirm(
    t("ai_logs.deleteReportMsg", { name: row.name }),
    t("ai_logs.deleteReport"),
    {
      type: "warning",
      confirmButtonText: t("ai_logs.delete"),
      cancelButtonText: t("ai_logs.cancel"),
    }
  );
  try {
    await deleteQueryReports([row.id]);
    ElMessage.success(t("ai_logs.deleted"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.deleteFailed"));
  }
}

onMounted(async () => {
  await load();
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
});
</script>

<style scoped>
.r-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.r-head__ops {
  display: flex;
  align-items: center;
  gap: 12px;
}
.r-tip {
  margin-bottom: 12px;
}
.r-total {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.r-result {
  margin-top: 12px;
}
.r-dim {
  color: var(--el-text-color-placeholder);
}
.r-param {
  width: 100%;
}
.r-addparam {
  margin-top: 8px;
}
</style>
