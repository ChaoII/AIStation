<template>
  <div class="app-container ai-console">
    <div class="ai-head">
      <div>
        <div class="ai-eyebrow">AI · Mission Control</div>
        <h1>大模型控制台</h1>
        <div class="ai-sub">模型、提示词、应用与运行观测的统一入口</div>
      </div>
      <div class="ai-signal">
        <span class="dot" :class="stats.errors ? 'err' : 'on'" />
        {{ stats.errors ? `${stats.errors} 次异常` : "系统正常" }}
        <span>· 平均 {{ stats.avg_latency_ms }}ms</span>
      </div>
    </div>

    <div class="ai-grid">
      <div class="ai-metric">
        <div class="k">提供商</div>
        <div class="v cyan">{{ stats.providers }}</div>
      </div>
      <div class="ai-metric">
        <div class="k">模型</div>
        <div class="v violet">{{ stats.models }}</div>
      </div>
      <div class="ai-metric">
        <div class="k">调用次数</div>
        <div class="v">{{ stats.calls }}</div>
      </div>
      <div class="ai-metric">
        <div class="k">报告</div>
        <div class="v amber">{{ stats.reports }}</div>
      </div>
    </div>

    <div class="ai-cols">
      <div class="ai-panel">
        <div class="ai-panel-hd">
          <span>最近调用</span>
          <el-button size="small" text @click="load">刷新</el-button>
        </div>
        <div class="ai-panel-bd">
          <table class="ai-table">
            <thead>
              <tr><th>模型</th><th>用途</th><th>耗时</th><th>结果</th><th>时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in stats.recent_calls" :key="c.id">
                <td>{{ c.model_name || "—" }}</td>
                <td>{{ c.usage }}</td>
                <td>{{ c.latency_ms }}ms</td>
                <td>
                  <span class="ai-tag" :class="c.result === 'success' ? 'ok' : 'err'">
                    {{ c.result === "success" ? "成功" : "失败" }}
                  </span>
                </td>
                <td>{{ c.created_time }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!stats.recent_calls.length" class="ai-empty">暂无调用记录，去运行台问一句试试</div>
        </div>
      </div>

      <div class="ai-panel">
        <div class="ai-panel-hd"><span>快捷入口</span></div>
        <div class="ai-panel-bd">
          <el-space direction="vertical" alignment="flex-start" :size="10" style="width: 100%">
            <el-button class="quick" @click="go('/ai/provider')">配置提供商 / API Key</el-button>
            <el-button class="quick" @click="go('/ai/model')">添加并启用模型</el-button>
            <el-button class="quick" @click="go('/ai/playground')">打开运行台试运行</el-button>
            <el-button class="quick" @click="go('/ai/report')">查看 AI 报告</el-button>
          </el-space>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getAiOverviewStats } from "@/api/module_ai/overview";

const router = useRouter();
const stats = reactive<any>({
  providers: 0,
  models: 0,
  reports: 0,
  calls: 0,
  errors: 0,
  avg_latency_ms: 0,
  recent_calls: [],
});

async function load() {
  try {
    const res = await getAiOverviewStats();
    Object.assign(stats, res.data?.data || {});
  } catch {
    /* 静默 */
  }
}

function go(path: string) {
  router.push(path);
}

onMounted(load);
</script>

<style scoped>
.quick {
  width: 100%;
  justify-content: flex-start;
}
</style>
