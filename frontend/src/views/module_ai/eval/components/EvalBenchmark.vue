<template>
  <div class="ev-bench">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>基准测试</span>
          <div class="ev-head__ops">
            <el-button size="small" type="primary" :loading="running" @click="run">
              运行基准
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
        title="跑内置黄金题集（指标快路径 + NL2SQL），给出准确率与耗时基线，用于回归对比。"
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
        <el-descriptions-item label="指标快路径题数">
          {{ report.fast?.total ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="指标快路径准确率">
          {{ fmt(report.fast?.semantic_accuracy) }}
        </el-descriptions-item>
        <el-descriptions-item label="NL2SQL 题数">
          {{ report.nl2sql?.total ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="NL2SQL 准确率">
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
        <el-table-column prop="q" label="问题" min-width="220" show-overflow-tooltip />
        <el-table-column label="结果" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.correct ? 'success' : 'danger'" effect="plain">
              {{ row.correct ? "对" : "错" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ms" label="耗时(ms)" width="100" align="center" />
      </el-table>
      <el-empty v-if="!status" description="点击「运行基准」开始" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { ElMessage } from "element-plus";
import { getQueryBenchmarkStatus, runQueryBenchmark } from "@/api/module_ai/query";

defineOptions({ name: "AiEvalBenchmark" });

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
  if (s.status === "done") return "已完成";
  if (s.status === "error") return "失败";
  return "运行中";
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
      ElMessage.success("基准测试完成");
    } else if (d.status === "error") {
      running.value = false;
      stop();
      ElMessage.error(d.error || "基准测试失败");
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
    ElMessage.error(e?.msg || "启动失败");
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
