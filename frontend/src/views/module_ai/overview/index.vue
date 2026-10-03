<!-- AI 控制台：全局统计聚合 + 调用趋势 + 最近调用 + 快捷入口 -->
<template>
  <div class="app-container ai-overview-page">
    <el-row :gutter="12" class="ov-cards">
      <el-col v-for="c in cards" :key="c.key" :xs="12" :md="6">
        <el-card shadow="never" class="ov-card" @click="go(c.route)">
          <div class="ov-card__inner">
            <el-statistic :title="c.title" :value="stats[c.key]" />
            <div class="ov-card__hint">{{ c.hint }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="15">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>调用趋势（近 7 天）</template>
          <div ref="trendRef" class="ov-chart" />
        </el-card>
      </el-col>
      <el-col :md="9">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>快捷入口</template>
          <div class="ov-entry-list">
            <div v-for="e in entries" :key="e.path" class="ov-entry" @click="$router.push(e.path)">
              <el-icon class="ov-entry__icon"><component :is="e.icon" /></el-icon>
              <div>
                <div class="ov-entry__name">{{ e.name }}</div>
                <div class="ov-entry__desc">{{ e.desc }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="ov-recent-card">
      <template #header>最近调用</template>
      <el-table
        :data="stats.recent_calls || []"
        size="small"
        max-height="320"
        :show-overflow-tooltip="true"
      >
        <el-table-column prop="created_time" label="时间" min-width="160" />
        <el-table-column prop="model_name" label="模型" min-width="150" />
        <el-table-column prop="usage" label="用途" width="100" />
        <el-table-column prop="latency_ms" label="耗时" width="90" align="center">
          <template #default="{ row }">{{ row.latency_ms }} ms</template>
        </el-table-column>
        <el-table-column label="结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
              {{ row.result === "success" ? "成功" : "失败" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import * as echarts from "echarts";
import {
  Collection,
  SetUp,
  Cpu,
  MagicStick,
  Coin,
  Message,
  Files,
  Link,
} from "@element-plus/icons-vue";
import { getAiOverviewStats } from "@/api/module_ai/overview";

defineOptions({ name: "AiOverview" });

const stats = reactive<any>({});
const trendRef = ref<HTMLElement>();
let trendChart: echarts.ECharts | null = null;

const cards = [
  { key: "models", title: "模型配置", hint: "已接入大模型", route: "/ai/model", icon: Cpu },
  { key: "providers", title: "供应商", hint: "模型服务商", route: "/ai/provider", icon: Link },
  {
    key: "knowledge_bases",
    title: "知识库",
    hint: "RAG 知识库",
    route: "/ai/knowledge",
    icon: Collection,
  },
  { key: "apps", title: "组件", hint: "应用/智能体", route: "/ai/app", icon: MagicStick },
  { key: "workflows", title: "工作流", hint: "编排流程", route: "/ai/workflow", icon: SetUp },
  { key: "calls", title: "累计调用", hint: "全部 AI 调用", route: "/ai/logs", icon: Message },
  { key: "today_calls", title: "今日调用", hint: "今日次数", route: "/ai/logs", icon: Coin },
  { key: "success_rate", title: "成功率", hint: "调用成功率", route: "/ai/logs", icon: Files },
];

const entries = [
  { name: "知识库", desc: "RAG + 引用溯源 + 图谱", path: "/ai/knowledge", icon: Collection },
  { name: "组件", desc: "聊天/智能体/工作流/知识库", path: "/ai/app", icon: MagicStick },
  { name: "工作流", desc: "编排/调试/HITL", path: "/ai/workflow", icon: SetUp },
  { name: "模型配置", desc: "接入与管理大模型", path: "/ai/model", icon: Cpu },
  { name: "供应商", desc: "模型服务商管理", path: "/ai/provider", icon: Link },
  { name: "调用日志", desc: "统计/详情/导出", path: "/ai/logs", icon: Message },
];

function go(route?: string) {
  if (route) location.hash = `#${route}`;
}

async function load() {
  try {
    const r = await getAiOverviewStats();
    Object.assign(stats, r.data?.data || {});
    await nextTick();
    render();
  } catch {
    // 统计失败不阻断
  }
}

function render() {
  if (!trendRef.value) return;
  trendChart = trendChart || echarts.init(trendRef.value);
  const t = stats.trend || [];
  trendChart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["调用", "失败"] },
    grid: { left: 40, right: 16, top: 30, bottom: 24 },
    xAxis: { type: "category", data: t.map((x: any) => x.date) },
    yAxis: { type: "value" },
    series: [
      {
        name: "调用",
        type: "bar",
        data: t.map((x: any) => x.count),
        itemStyle: { color: "#409eff" },
      },
      { name: "失败", type: "line", smooth: true, data: t.map((x: any) => x.error) },
    ],
  });
}

function resize() {
  trendChart?.resize();
}

onMounted(() => {
  load();
  window.addEventListener("resize", resize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  trendChart?.dispose();
});
</script>

<style scoped>
.ai-overview-page {
  padding: 12px;
  overflow: auto;
}
.ov-cards {
  margin-bottom: 12px;
}
.ov-card {
  margin-bottom: 12px;
  cursor: pointer;
}
.ov-card__inner {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ov-card__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ov-body {
  margin-bottom: 12px;
}
.ov-chart-card {
  margin-bottom: 12px;
}
.ov-chart {
  height: 300px;
}
.ov-entry-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ov-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
}
.ov-entry:hover {
  background: var(--el-fill-color-light);
}
.ov-entry__icon {
  font-size: 20px;
  color: var(--el-color-primary);
}
.ov-entry__name {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ov-entry__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ov-recent-card {
  margin-bottom: 12px;
}
</style>
