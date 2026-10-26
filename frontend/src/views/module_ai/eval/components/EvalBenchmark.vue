<template>
  <div class="ev-bench">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>{{ $t("ai_workflow.eval_benchmark") }}</span>
          <div class="ev-head__ops">
            <el-button size="small" type="primary" :loading="running" @click="run">
              {{ $t("ai_workflow.eval_runBenchmark") }}
            </el-button>
            <el-tag v-if="status" size="small" type="info" effect="plain">
              {{ statusText }}
            </el-tag>
          </div>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="ev-alert"
        :title="$t('ai_workflow.eval_benchAlert')"
      />
      <el-progress
        v-if="status"
        :percentage="pct"
        :status="
          status.status === 'error' ? 'exception' : status.status === 'done' ? 'success' : undefined
        "
        style="margin-bottom: 12px"
      />
      <div v-if="status" class="ev-bench__cur">
        <span>{{ status.stage }}</span>
        <span v-if="status.current">· {{ status.current }}</span>
        <span>{{ status.done }} / {{ status.total }}</span>
      </div>
      <el-descriptions v-if="report" :column="2" border size="small" style="margin-top: 12px">
        <el-descriptions-item :label="$t('ai_workflow.eval_fastCount')">
          {{ report.fast?.total ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('ai_workflow.eval_fastAccuracy')">
          {{ fmt(report.fast?.semantic_accuracy) }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('ai_workflow.eval_nl2sqlCount')">
          {{ report.nl2sql?.total ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item :label="$t('ai_workflow.eval_nl2sqlAccuracy')">
          {{ fmt(report.nl2sql?.accuracy) }}
        </el-descriptions-item>
      </el-descriptions>
      <el-table
        v-if="report?.nl2sql?.results?.length"
        :data="report.nl2sql.results"
        size="small"
        border
        style="margin-top: 12px"
        max-height="360"
        stripe
      >
        <el-table-column
          prop="q"
          :label="$t('ai_workflow.eval_question')"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column :label="$t('ai_workflow.eval_result')" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.correct ? 'success' : 'danger'" effect="plain">
              {{
                row.correct
                  ? $t("ai_workflow.eval_correctShort")
                  : $t("ai_workflow.eval_wrongShort")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ms" :label="$t('ai_workflow.eval_ms')" width="100" align="center" />
      </el-table>
      <el-empty v-if="!status" :description="$t('ai_workflow.eval_clickRun')" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { getQueryBenchmarkStatus, runQueryBenchmark } from "@/api/module_ai/query";

defineOptions({ name: "AiEvalBenchmark" });

const { t } = useI18n();

const running = ref(false);
const status = ref<any>(null);
const report = ref<any>(null);
let timer: ReturnType<typeof setInterval> | null = null;

const pct = computed(() => {
  const s = status.value;
  if (!s || !s.total) return 0;
  return Math.min(100, Math.round((s.done / s.total) * 100));
});
const statusText = computed(() => {
  const s = status.value;
  if (!s) return "";
  if (s.status === "done") return t("ai_workflow.eval_done");
  if (s.status === "error") return t("ai_workflow.eval_failed");
  return t("ai_workflow.eval_running");
});

function fmt(v: any) {
  if (v == null) return "-";
  return typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v);
}

function stop() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

async function poll(runId: string) {
  try {
    const r = await getQueryBenchmarkStatus(runId);
    const d = r.data?.data;
    if (!d) return;
    status.value = d;
    if (d.status === "done") {
      report.value = d.report || null;
      running.value = false;
      stop();
      ElMessage.success(t("ai_workflow.eval_benchDone"));
    } else if (d.status === "error") {
      running.value = false;
      stop();
      ElMessage.error(d.error || t("ai_workflow.eval_benchFail"));
    }
  } catch {
    /* 轮询失败忽略，下一轮重试 */
  }
}

async function run() {
  running.value = true;
  report.value = null;
  status.value = null;
  try {
    const r = await runQueryBenchmark();
    const runId = r.data?.data?.run_id;
    if (!runId) throw new Error("未返回 run_id");
    status.value = { status: "running", stage: "fast", done: 0, total: 0, current: "" };
    stop();
    timer = setInterval(() => poll(runId), 2000);
    await poll(runId);
  } catch (e: any) {
    running.value = false;
    ElMessage.error(e?.msg || t("ai_workflow.eval_startFail"));
  }
}

onBeforeUnmount(stop);
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
  margin-bottom: 10px;
}
.ev-bench__cur {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
