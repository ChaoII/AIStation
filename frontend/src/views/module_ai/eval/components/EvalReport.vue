<template>
  <div class="ev-report">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>评测报表</span>
          <div class="ev-head__ops">
            <el-select
              v-model="selected"
              size="small"
              placeholder="选择一次运行"
              style="width: 260px"
              @change="loadReport"
            >
              <el-option
                v-for="r in runs"
                :key="r.run_id"
                :label="`${r.run_id}（${r.status} ${r.done}/${r.total}）`"
                :value="r.run_id"
              />
            </el-select>
            <el-button size="small" :disabled="!selected" @click="loadReport">刷新</el-button>
          </div>
        </div>
      </template>

      <el-empty
        v-if="!selected"
        description="请选择一次运行（或在「运行」页启动评测）"
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

        <el-divider content-position="left">分维度准确率</el-divider>
        <el-tabs v-model="dimTab" type="border-card">
          <el-tab-pane v-for="d in dims" :key="d.field" :label="d.label" :name="d.field">
            <el-table :data="groupRows(d.field)" size="small" border>
              <el-table-column prop="key" label="分组" min-width="160" show-overflow-tooltip />
              <el-table-column prop="total" label="题数" width="90" />
              <el-table-column prop="correct" label="正确" width="90" />
              <el-table-column label="准确率" min-width="200">
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

        <el-divider content-position="left">逐题 trace</el-divider>
        <div class="ev-trace-filter">
          <el-radio-group v-model="only" size="small">
            <el-radio-button label="all">全部（{{ results.length }}）</el-radio-button>
            <el-radio-button label="fail">仅失败</el-radio-button>
            <el-radio-button label="slow">仅慢路径</el-radio-button>
          </el-radio-group>
        </div>
        <el-table v-loading="loading" :data="filteredResults" size="small" border>
          <el-table-column type="expand">
            <template #default="{ row }">
              <el-descriptions :column="2" size="small" border class="ev-exp">
                <el-descriptions-item label="预期指标">
                  {{ row.expected_metric || "-" }}
                </el-descriptions-item>
                <el-descriptions-item label="命中指标">
                  {{ row.metric_key || "-" }}
                </el-descriptions-item>
                <el-descriptions-item label="召回金标表">
                  <el-tag
                    v-for="t in parseJson(row.recall_hit).expected || []"
                    :key="t"
                    size="small"
                    type="success"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ t }}
                  </el-tag>
                  <span v-if="!(parseJson(row.recall_hit).expected || []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item label="实际召回表">
                  <el-tag
                    v-for="t in parseJson(row.recall_hit).recalled || []"
                    :key="t"
                    size="small"
                    type="info"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ t }}
                  </el-tag>
                  <span v-if="!(parseJson(row.recall_hit).recalled || []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item label="本体物化表" :span="2">
                  <el-tag
                    v-for="t in parseJson(row.ontology_used, [])"
                    :key="t"
                    size="small"
                    effect="plain"
                    class="ev-tag"
                  >
                    {{ t }}
                  </el-tag>
                  <span v-if="!parseJson(row.ontology_used, []).length">-</span>
                </el-descriptions-item>
                <el-descriptions-item label="生成 SQL" :span="2">
                  <el-input :model-value="row.sql || '（无）'" type="textarea" :rows="4" readonly />
                </el-descriptions-item>
              </el-descriptions>
            </template>
          </el-table-column>
          <el-table-column type="index" label="#" width="52" />
          <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="path" label="路径" width="90">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.path === 'fast' ? 'success' : 'warning'"
                effect="plain"
              >
                {{ row.path === "fast" ? "快路径" : "慢路径" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.is_error" size="small" type="danger">报错</el-tag>
              <el-tag v-else-if="row.gold_match" size="small" type="success">正确</el-tag>
              <el-tag v-else size="small" type="warning">不符</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="n_rows" label="行数" width="80" />
          <el-table-column prop="took_ms" label="耗时(ms)" width="100" />
          <el-table-column label="Recall@8" width="110">
            <template #default="{ row }">{{ pct(row.recall) }}</template>
          </el-table-column>
          <el-table-column prop="scenario" label="场景" width="140" show-overflow-tooltip />
          <el-table-column prop="datasource" label="数据源" width="100" />
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { getEvalReport, getEvalRuns } from "@/api/module_ai/query";
import { pct, type EvalReport, type EvalResultRow, type EvalRunItem } from "../types";

defineOptions({ name: "AiEvalReport" });

const props = defineProps<{ runId?: string }>();
const emit = defineEmits<{ (e: "update:runId", id: string): void }>();

const runs = ref<EvalRunItem[]>([]);
const selected = ref<string>("");
const report = ref<EvalReport | null>(null);
const loading = ref(false);
const dimTab = ref("difficulty");
const only = ref<"all" | "fail" | "slow">("all");

const dims = [
  { field: "difficulty", label: "难度" },
  { field: "form", label: "形式" },
  { field: "scenario", label: "场景" },
  { field: "datasource", label: "数据源" },
];

const results = computed<EvalResultRow[]>(() => report.value?.results || []);

const stats = computed(() => {
  const s = report.value?.summary;
  if (!s) return [];
  return [
    { label: "生成题准确率", value: +((s.generation_accuracy ?? 0) * 100).toFixed(1), suffix: "%" },
    { label: "指标题准确率", value: +((s.metric_accuracy ?? 0) * 100).toFixed(1), suffix: "%" },
    { label: "数据准确率", value: +(s.data_accuracy * 100).toFixed(1), suffix: "%" },
    { label: "语义准确率", value: +(s.semantic_accuracy * 100).toFixed(1), suffix: "%" },
    { label: "快路径占比", value: +(s.fast_rate * 100).toFixed(1), suffix: "%" },
    { label: "Recall@8", value: +(s.recall_at_k * 100).toFixed(1), suffix: "%" },
    { label: "平均耗时", value: s.avg_ms, suffix: "ms" },
    { label: "错误率", value: +(s.error_rate * 100).toFixed(1), suffix: "%" },
  ];
});

/** 退化题说明：金标结果为空/NULL/单值 0，答对答错都没信息量 → 不计入精度分母。 */
const degenerateNote = computed(() => {
  const s = report.value?.summary;
  if (!s || !s.degenerate_n) return "";
  const all = s.all_total ?? s.total + s.degenerate_n;
  return `共 ${all} 题，其中 ${s.degenerate_n} 题为退化题（金标为空/NULL/单值 0），`
    + `已排除在准确率之外；实际参与统计 ${s.total} 题。`;
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
    ElMessage.error(e?.msg || "加载报表失败");
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
