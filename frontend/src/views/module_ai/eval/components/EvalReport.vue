<template>
  <div class="ev-report">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>{{ $t("ai_workflow.eval_reportTitle") }}</span>
          <div class="ev-head__ops">
            <el-select
              v-model="selected"
              size="small"
              :placeholder="$t('ai_workflow.eval_selectRun')"
              style="width: 260px"
              @change="loadReport"
            >
              <el-option
                v-for="r in runs"
                :key="r.run_id"
                :label="
                  $t('ai_workflow.eval_runOptionLabel', {
                    runId: r.run_id,
                    status: r.status,
                    done: r.done,
                    total: r.total,
                  })
                "
                :value="r.run_id"
              />
            </el-select>
            <el-button size="small" :disabled="!selected" @click="loadReport">
              {{ $t("ai_workflow.eval_refresh") }}
            </el-button>
          </div>
        </div>
      </template>

      <el-empty
        v-if="!selected"
        :description="$t('ai_workflow.eval_selectRunEmpty')"
        :image-size="70"
      />

      <template v-else>
        <el-alert
          v-if="degenerateNote"
          type="warning"
          :closable="false"
          show-icon
          :title="degenerateNote"
          class="ev-degenerate"
        />
        <el-row :gutter="12">
          <el-col v-for="s in stats" :key="s.label" :xs="12" :sm="8" :md="4">
            <el-card shadow="never" class="ev-stat">
              <el-statistic :title="s.label" :value="s.value" :suffix="s.suffix" />
            </el-card>
          </el-col>
        </el-row>

        <el-divider content-position="left">{{ $t("ai_workflow.eval_dimAccuracy") }}</el-divider>
        <el-tabs v-model="dimTab" type="border-card">
          <el-tab-pane v-for="d in dims" :key="d.field" :label="dimLabels[d.field]" :name="d.field">
            <el-table :data="groupRows(d.field)" size="small" border stripe>
              <el-table-column
                prop="key"
                :label="$t('ai_workflow.eval_group')"
                min-width="160"
                show-overflow-tooltip
              />
              <el-table-column prop="total" :label="$t('ai_workflow.eval_qCount')" width="90" />
              <el-table-column prop="correct" :label="$t('ai_workflow.eval_correct')" width="90" />
              <el-table-column :label="$t('ai_workflow.eval_accuracy')" min-width="200">
                <template #default="{ row }">
                  <el-progress
                    :percentage="Math.round(row.accuracy * 100)"
                    :stroke-width="12"
                    :status="
                      row.accuracy === 1 ? 'success' : row.accuracy === 0 ? 'exception' : undefined
                    "
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <el-divider content-position="left">{{ $t("ai_workflow.eval_trace") }}</el-divider>
        <div class="ev-trace-filter">
          <el-radio-group v-model="only" size="small">
            <el-radio-button label="all">
              {{ $t("ai_workflow.eval_allFilter", { count: results.length }) }}
            </el-radio-button>
            <el-radio-button label="fail">{{ $t("ai_workflow.eval_onlyFail") }}</el-radio-button>
            <el-radio-button label="slow">{{ $t("ai_workflow.eval_onlySlow") }}</el-radio-button>
          </el-radio-group>
        </div>
        <el-table v-loading="loading" :data="filteredResults" size="small" border stripe>
          <el-table-column type="expand">
            <template #default="{ row }">
              <el-descriptions :column="2" size="small" border class="ev-exp">
                <el-descriptions-item :label="$t('ai_workflow.eval_expectedMetric')">
                  {{ row.expected_metric || "-" }}
                </el-descriptions-item>
                <el-descriptions-item :label="$t('ai_workflow.eval_hitMetric')">
                  {{ row.metric_key || "-" }}
                </el-descriptions-item>
                <el-descriptions-item :label="$t('ai_workflow.eval_recallGold')">
                  <el-tag
                    v-for="tg in parseJson(row.recall_hit).expected || []"
                    :key="tg"
                    size="small"
                    type="success"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ tg }}
                  </el-tag>
                  <span v-if="!(parseJson(row.recall_hit).expected || []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item :label="$t('ai_workflow.eval_actualRecall')">
                  <el-tag
                    v-for="tg in parseJson(row.recall_hit).recalled || []"
                    :key="tg"
                    size="small"
                    type="info"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ tg }}
                  </el-tag>
                  <span v-if="!(parseJson(row.recall_hit).recalled || []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item :label="$t('ai_workflow.eval_ontologyTables')" :span="2">
                  <el-tag
                    v-for="tg in parseJson(row.ontology_used, [])"
                    :key="tg"
                    size="small"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ tg }}
                  </el-tag>
                  <span v-if="!parseJson(row.ontology_used, []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item :label="$t('ai_workflow.eval_genSql')" :span="2">
                  <el-input
                    :model-value="row.sql || $t('ai_workflow.eval_none')"
                    type="textarea"
                    :rows="4"
                    readonly
                  />
                </el-descriptions-item>
              </el-descriptions>
            </template>
          </el-table-column>
          <el-table-column type="index" label="#" width="52" />
          <el-table-column
            prop="question"
            :label="$t('ai_workflow.eval_question')"
            min-width="240"
            show-overflow-tooltip
          />
          <el-table-column prop="path" :label="$t('ai_workflow.eval_path')" width="90">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.path === 'fast' ? 'success' : 'warning'"
                effect="plain"
              >
                {{
                  row.path === "fast"
                    ? $t("ai_workflow.eval_fastPath")
                    : $t("ai_workflow.eval_slowPath")
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('ai_workflow.eval_result')" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_error" size="small" type="danger">
                {{ $t("ai_workflow.eval_error") }}
              </el-tag>
              <el-tag v-else-if="row.gold_match" size="small" type="success">
                {{ $t("ai_workflow.eval_correct") }}
              </el-tag>
              <el-tag v-else size="small" type="warning">
                {{ $t("ai_workflow.eval_mismatch") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="n_rows" :label="$t('ai_workflow.eval_rows')" width="80" />
          <el-table-column prop="took_ms" :label="$t('ai_workflow.eval_ms')" width="100" />
          <el-table-column label="Recall@8" width="110">
            <template #default="{ row }">{{ pct(row.recall) }}</template>
          </el-table-column>
          <el-table-column
            prop="scenario"
            :label="$t('ai_workflow.eval_scenario')"
            width="140"
            show-overflow-tooltip
          />
          <el-table-column
            prop="datasource"
            :label="$t('ai_workflow.eval_datasource')"
            width="100"
          />
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { getEvalReport, getEvalRuns } from "@/api/module_ai/query";
import { pct, type EvalReport, type EvalResultRow, type EvalRunItem } from "../types";

defineOptions({ name: "AiEvalReport" });

const { t } = useI18n();

const props = defineProps<{ runId?: string }>();
const emit = defineEmits<{ (e: "update:runId", id: string): void }>();

const runs = ref<EvalRunItem[]>([]);
const selected = ref<string>("");
const report = ref<EvalReport | null>(null);
const loading = ref(false);
const dimTab = ref("difficulty");
const only = ref<"all" | "fail" | "slow">("all");

const dims = [
  { field: "difficulty", labelKey: "eval_difficulty" },
  { field: "form", labelKey: "eval_form" },
  { field: "scenario", labelKey: "eval_scenario" },
  { field: "datasource", labelKey: "eval_datasource" },
];

const dimLabels = computed(() =>
  Object.fromEntries(dims.map((d) => [d.field, t("ai_workflow." + d.labelKey)]))
);

const results = computed<EvalResultRow[]>(() => report.value?.results || []);

const stats = computed(() => {
  const s = report.value?.summary;
  if (!s) return [];
  return [
    {
      label: t("ai_workflow.eval_genAccuracy"),
      value: +((s.generation_accuracy ?? 0) * 100).toFixed(1),
      suffix: "%",
    },
    {
      label: t("ai_workflow.eval_metricAccuracy"),
      value: +((s.metric_accuracy ?? 0) * 100).toFixed(1),
      suffix: "%",
    },
    {
      label: t("ai_workflow.eval_dataAccuracy"),
      value: +(s.data_accuracy * 100).toFixed(1),
      suffix: "%",
    },
    {
      label: t("ai_workflow.eval_semanticAccuracy"),
      value: +(s.semantic_accuracy * 100).toFixed(1),
      suffix: "%",
    },
    { label: t("ai_workflow.eval_fastRate"), value: +(s.fast_rate * 100).toFixed(1), suffix: "%" },
    { label: "Recall@8", value: +(s.recall_at_k * 100).toFixed(1), suffix: "%" },
    { label: t("ai_workflow.eval_avgTime"), value: s.avg_ms, suffix: "ms" },
    {
      label: t("ai_workflow.eval_errorRate"),
      value: +(s.error_rate * 100).toFixed(1),
      suffix: "%",
    },
  ];
});

/** 退化题说明：金标结果为空/NULL/单值 0，答对答错都没信息量 → 不计入精度分母。 */
const degenerateNote = computed(() => {
  const s = report.value?.summary;
  if (!s || !s.degenerate_n) return "";
  const all = s.all_total ?? s.total + s.degenerate_n;
  return t("ai_workflow.eval_degenerate", {
    all,
    degenerate: s.degenerate_n,
    total: s.total,
  });
});

const filteredResults = computed(() => {
  if (only.value === "fail") return results.value.filter((r) => !r.gold_match);
  if (only.value === "slow") return results.value.filter((r) => r.path === "slow");
  return results.value;
});

function groupRows(field: string) {
  const g = (report.value as any)?.[`by_${field}`] || {};
  return Object.entries(g).map(([key, v]: [string, any]) => ({
    key,
    total: v.total,
    correct: v.correct,
    accuracy: v.accuracy,
  }));
}

function parseJson(s: any, fallback: any = {}) {
  if (!s) return fallback;
  if (typeof s === "object") return s;
  try {
    return JSON.parse(s);
  } catch {
    return fallback;
  }
}

async function loadRuns() {
  try {
    const r = await getEvalRuns(30);
    runs.value = r.data?.data || [];
    if (!selected.value && runs.value.length) {
      selected.value = runs.value[0].run_id;
    }
  } catch {
    runs.value = [];
  }
}

async function loadReport() {
  if (!selected.value) return;
  loading.value = true;
  try {
    const r = await getEvalReport(selected.value);
    report.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_loadFail"));
    report.value = null;
  } finally {
    loading.value = false;
  }
}

// 父组件（运行页）跑完会把 runId 传进来 → 切换选中项并加载
watch(
  () => props.runId,
  async (id) => {
    if (!id) return;
    await loadRuns();
    selected.value = id;
    await loadReport();
  }
);

onMounted(async () => {
  await loadRuns();
  if (props.runId && props.runId !== selected.value) {
    selected.value = props.runId;
  }
  await loadReport();
  if (selected.value) emit("update:runId", selected.value);
});
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
.ev-stat {
  margin-bottom: 12px;
}
.ev-degenerate {
  margin-bottom: 12px;
}
.ev-trace-filter {
  margin-bottom: 10px;
}
.ev-exp {
  padding: 4px 8px;
}
.ev-tag {
  margin: 0 4px 4px 0;
}
</style>
