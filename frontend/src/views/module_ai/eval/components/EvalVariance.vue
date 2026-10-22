<!--
  评测·方差：同一批题重复跑 N 次，回答"这个差异是真的吗"。

  为什么要有它：同一配置（代码路径完全相同）三次跑同一批 B 半 53 题，
  data_accuracy = 75.47% / 83.02% / 84.91%（差 10 分）→ 单次 A/B 的差值
  **不能归因给功能**。这里把"噪声带"直接算出来当判据。
-->
<template>
  <div class="ev-wrap">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="同一批题重复跑 N 次：看跨次方差（噪声带）与逐题翻转。任何小于噪声带的差异都不能归因给功能。"
    />

    <el-form :inline="true" class="ev-form">
      <el-form-item label="重复次数">
        <el-select v-model="repeats" size="small" style="width: 110px">
          <el-option v-for="n in [2, 3, 4, 5]" :key="n" :label="`${n} 次`" :value="n" />
        </el-select>
      </el-form-item>
      <el-form-item label="数据源">
        <el-select
          v-model="datasource"
          size="small"
          clearable
          placeholder="全部"
          style="width: 190px"
        >
          <el-option label="系统库" value="system" />
          <el-option
            v-for="d in datasources"
            :key="d.code || d.id"
            :label="d.name"
            :value="d.code || `ds:${d.id}`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="只跑生成">
        <el-switch v-model="forceSlow" size="small" />
      </el-form-item>
      <el-button type="primary" size="small" :loading="running" @click="start">
        开始重复执行
      </el-button>
      <el-button size="small" :disabled="!runId" @click="refresh">刷新进度</el-button>
    </el-form>

    <el-descriptions v-if="runId" :column="4" border size="small" class="ev-desc">
      <el-descriptions-item label="状态">{{ st?.status || "-" }}</el-descriptions-item>
      <el-descriptions-item label="进度">
        {{ st?.done ?? 0 }} / {{ st?.repeats ?? repeats }}
      </el-descriptions-item>
      <el-descriptions-item label="当前">{{ st?.current || "-" }}</el-descriptions-item>
      <el-descriptions-item label="噪声带">
        {{ rep ? `${rep.spread} 分` : "-" }}
      </el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="st?.error"
      type="error"
      :closable="false"
      show-icon
      :title="st.error"
      class="ev-mt"
    />

    <template v-if="rep">
      <el-alert
        :type="rep.spread >= 5 ? 'warning' : 'success'"
        :closable="false"
        show-icon
        class="ev-mt"
        :title="`每次准确率 ${rep.per_run_accuracy.join(' / ')} 均值 ${rep.mean} 标准差 ${rep.std} 极差(噪声带) ${rep.spread} 分`"
      />
      <div class="ev-stat">
        题数 {{ rep.n_questions }} 稳定通过 {{ rep.always_pass }} 稳定失败
        {{ rep.always_fail }} 不稳定 {{ rep.unstable.length }}
      </div>

      <el-table :data="rep.unstable" size="small" border class="ev-mt" stripe>
        <el-table-column label="跨次通过率" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.rate >= 0.5 ? 'warning' : 'danger'">
              {{ row.rate }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="question"
          label="不稳定题（跨次翻转）"
          min-width="360"
          show-overflow-tooltip
        />
      </el-table>

      <el-table :data="rep.pairs" size="small" border class="ev-mt" stripe>
        <el-table-column label="对比" width="100" align="center">
          <template #default="{ row }">第 {{ row.a }} vs {{ row.b }} 次</template>
        </el-table-column>
        <el-table-column label="翻转（前错后对 / 前对后错）" width="220" align="center">
          <template #default="{ row }">{{ row.b01 }} / {{ row.b10 }}</template>
        </el-table-column>
        <el-table-column prop="p" label="p 值" width="100" align="center" />
        <el-table-column label="判定" width="200">
          <template #default="{ row }">
            <el-tag v-if="row.significant" size="small" type="danger">显著</el-tag>
            <el-tag v-else size="small" type="info">不显著（噪声可解释）</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { getEvalVariance, getQueryDatasources, startEvalVariance } from "@/api/module_ai/query";

defineOptions({ name: "AiEvalVariance" });

interface VarianceReport {
  n_runs: number;
  per_run_accuracy: number[];
  mean: number;
  std: number;
  min: number;
  max: number;
  spread: number;
  n_questions: number;
  always_pass: number;
  always_fail: number;
  unstable: { question: string; rate: number; runs: number }[];
  pairs: { a: number; b: number; b01: number; b10: number; p: number; significant: boolean }[];
}

const repeats = ref(3);
const datasource = ref("system");
const forceSlow = ref(true);
const datasources = ref<any[]>([]);
const runId = ref("");
const running = ref(false);
const st = ref<any>(null);
const timer = ref<any>(null);

const rep = computed<VarianceReport | null>(() => st.value?.report || null);

async function start() {
  running.value = true;
  try {
    const filter: any = {};
    if (datasource.value) filter.datasource = datasource.value;
    if (forceSlow.value) filter.force_slow = true;
    const r = await startEvalVariance({ repeats: repeats.value, filter });
    runId.value = r.data?.data?.run_id || "";
    ElMessage.success("已启动，重复执行会比较慢（每次一轮完整评测）");
    schedulePoll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "启动失败");
  } finally {
    running.value = false;
  }
}

async function refresh() {
  if (!runId.value) return;
  try {
    const r = await getEvalVariance(runId.value);
    st.value = r.data?.data || null;
    if (st.value?.status === "done" || st.value?.status === "error") stopPoll();
  } catch {
    /* 轮询失败不打扰用户 */
  }
}

function schedulePoll() {
  stopPoll();
  timer.value = setInterval(refresh, 10_000);
}
function stopPoll() {
  if (timer.value) {
    clearInterval(timer.value);
    timer.value = null;
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
</script>

<style scoped>
.ev-form {
  margin-top: 12px;
}
.ev-desc {
  margin-top: 4px;
}
.ev-mt {
  margin-top: 12px;
}
.ev-stat {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
