<template>
  <div class="ev-abl">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>{{ $t("ai_workflow.eval_ablTitle") }}</span>
          <div class="ev-head__ops">
            <el-button
              size="small"
              type="primary"
              :loading="starting"
              :disabled="running"
              @click="start"
            >
              {{ $t("ai_workflow.eval_startAblation") }}
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="$t('ai_workflow.eval_ablAlert')"
        class="ev-alert"
      />

      <el-form :model="form" label-width="96px">
        <el-form-item :label="$t('ai_workflow.eval_ablSwitches')">
          <el-checkbox-group v-model="form.keys">
            <el-checkbox v-for="k in ABLATION_KEYS" :key="k.key" :label="k.key">
              {{ $t("ai_workflow." + k.label) }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_datasource')">
          <el-select
            v-model="form.datasource"
            size="small"
            clearable
            :placeholder="$t('ai_workflow.eval_all')"
            style="width: 190px"
          >
            <el-option :label="$t('ai_workflow.eval_systemDs')" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_perGroupLimit')">
          <el-input-number v-model="form.limit" :min="1" :max="100" />
          <span class="ev-hint">{{ $t("ai_workflow.eval_groupHint") }}</span>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_forceSlow')">
          <el-switch v-model="form.force_slow" size="small" />
          <span class="ev-hint">{{ $t("ai_workflow.eval_slowHint") }}</span>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="report"
        :type="report.status === 'error' ? 'error' : 'info'"
        :closable="false"
        show-icon
        :title="
          report.status === 'error'
            ? $t('ai_workflow.eval_ablFail')
            : $t('ai_workflow.eval_currentPrefix', { current: report.current || '-' })
        "
        class="ev-alert"
      />
      <el-progress
        v-if="report && report.status === 'running'"
        :percentage="progressPct"
        :stroke-width="14"
      />
      <el-alert
        v-if="report?.error"
        type="error"
        :closable="false"
        show-icon
        :title="report.error"
        class="ev-alert"
      />

      <el-table
        v-if="tableRows.length"
        :data="tableRows"
        size="small"
        border
        class="ev-table"
        stripe
      >
        <el-table-column
          prop="name"
          :label="$t('ai_workflow.eval_group')"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column :label="$t('ai_workflow.eval_dataAccuracy')" width="130">
          <template #default="{ row }">{{ pct(row.data_accuracy) }}</template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_deltaAccuracy')" width="110">
          <template #default="{ row }">
            <span v-if="row.delta === null || row.delta === undefined">-</span>
            <el-tag
              v-else
              size="small"
              :type="row.delta < 0 ? 'danger' : row.delta > 0 ? 'success' : 'info'"
            >
              {{ (row.delta * 100).toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Recall@8" width="110">
          <template #default="{ row }">{{ pct(row.recall_at_k) }}</template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_fastRate')" width="120">
          <template #default="{ row }">{{ pct(row.fast_rate) }}</template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_avgTime')" width="130">
          <template #default="{ row }">{{ row.avg_ms }}</template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_deltaMs')" width="110">
          <template #default="{ row }">{{ row.delta_avg_ms ?? "-" }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { getEvalAblation, getQueryDatasources, startEvalAblation } from "@/api/module_ai/query";
import { ABLATION_KEYS, pct, type EvalAblationReport } from "../types";

defineOptions({ name: "AiEvalAblation" });

const { t } = useI18n();

const datasources = ref<any[]>([]);
const form = ref<any>({
  keys: ["recall_enabled", "agno_semantic_enabled"],
  datasource: "",
  limit: 20,
  force_slow: false,
});
const starting = ref(false);
const report = ref<EvalAblationReport | null>(null);

let timer: ReturnType<typeof setInterval> | null = null;

const running = computed(() => report.value?.status === "running");

const progressPct = computed(() => {
  const r = report.value;
  const total = (r?.groups || []).length;
  if (!total) return 0;
  const done = Object.keys(r?.table || {}).length;
  return Math.min(100, Math.round((done / total) * 100));
});

const tableRows = computed(() => {
  const table = report.value?.table || {};
  const nameOf = (k: string) => {
    if (k === "baseline") return t("ai_workflow.eval_baseline");
    const hit = ABLATION_KEYS.find((x) => x.key === k);
    return hit ? t("ai_workflow.eval_offPrefix", { label: t("ai_workflow." + hit.label) }) : k;
  };
  return Object.entries(table).map(([k, v]: [string, any]) => ({
    name: nameOf(k),
    data_accuracy: v.data_accuracy,
    recall_at_k: v.recall_at_k,
    fast_rate: v.fast_rate,
    avg_ms: v.avg_ms,
    delta: v.delta_data_accuracy,
    delta_avg_ms: v.delta_avg_ms,
  }));
});

function stopPolling() {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

async function poll(runId: string) {
  try {
    const r = await getEvalAblation(runId);
    const d: EvalAblationReport | null = r.data?.data || null;
    report.value = d;
    if (!d || d.status !== "running") {
      stopPolling();
      if (d && d.status === "done") ElMessage.success(t("ai_workflow.eval_ablDone"));
      else if (d && d.status === "error") ElMessage.error(d.error || t("ai_workflow.eval_ablFail"));
    }
  } catch {
    // 单次失败不终止
  }
}

async function start() {
  if (!form.value.keys.length) {
    ElMessage.warning(t("ai_workflow.eval_selectSwitch"));
    return;
  }
  starting.value = true;
  try {
    const filter: any = { limit: form.value.limit };
    if (form.value.datasource) filter.datasource = form.value.datasource;
    if (form.value.force_slow) filter.force_slow = true;
    const r = await startEvalAblation({ keys: form.value.keys, filter });
    const runId: string = r.data?.data?.run_id;
    if (!runId) {
      ElMessage.error(t("ai_workflow.eval_startFailNoRun"));
      return;
    }
    report.value = { run_id: runId, status: "running", current: "", table: {} };
    stopPolling();
    timer = setInterval(() => poll(runId), 2000);
    await poll(runId);
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_startFail"));
  } finally {
    starting.value = false;
  }
}

onMounted(async () => {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
});

onUnmounted(stopPolling);
</script>

<style scoped>
.ev-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.ev-head__ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ev-alert {
  margin-bottom: 12px;
}
.ev-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ev-table {
  margin-top: 12px;
}
</style>
