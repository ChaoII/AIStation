<template>
  <div class="app-container ai-eval-page">
    <el-tabs v-model="tab" type="border-card">
      <el-tab-pane label="测试集" name="cases">
        <EvalCases />
      </el-tab-pane>
      <el-tab-pane label="运行" name="run">
        <EvalRunPanel @started="onStarted" @finished="onFinished" @select="onSelect" />
      </el-tab-pane>
      <el-tab-pane label="报表" name="report">
        <EvalReport :run-id="runId" />
      </el-tab-pane>
      <el-tab-pane label="消融" name="ablation">
        <EvalAblation />
      </el-tab-pane>
      <el-tab-pane label="方差" name="variance">
        <EvalVariance />
      </el-tab-pane>
      <el-tab-pane label="基准测试" name="benchmark">
        <EvalBenchmark />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import EvalCases from "./components/EvalCases.vue";
import EvalRunPanel from "./components/EvalRunPanel.vue";
import EvalReport from "./components/EvalReport.vue";
import EvalAblation from "./components/EvalAblation.vue";
import EvalVariance from "./components/EvalVariance.vue";
import EvalBenchmark from "./components/EvalBenchmark.vue";

defineOptions({ name: "AiEval" });

const tab = ref("cases");
/** 当前关注的运行：由「运行」页发起/选中后传给「报表」页。 */
const runId = ref("");

function onStarted(id: string) {
  runId.value = id;
}

/** 运行完成 → 自动跳到报表页展示结果。 */
function onFinished(id: string) {
  runId.value = id;
  tab.value = "report";
}

function onSelect(id: string) {
  runId.value = id;
  tab.value = "report";
}
</script>

<style scoped>
.ai-eval-page :deep(.el-tabs__content) {
  padding: 0;
}
</style>
