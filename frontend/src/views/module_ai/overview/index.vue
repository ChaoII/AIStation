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

    <el-card shadow="never" class="ov-recent-card" style="margin-bottom: 12px">
      <template #header>
        <div class="ov-usage-row" style="justify-content: space-between">
          <span>Compass 全局数据目录</span>
          <span style="font-size:12px;color:var(--el-text-color-secondary)">搜索 表 / 对象 / 指标 / 术语</span>
        </div>
      </template>
      <div class="compass-bar">
        <el-input v-model="compassKw" placeholder="输入关键词，如 摄像头 / 告警 / 订单" clearable style="flex:1" @keyup.enter="runCompass" />
        <el-button type="primary" :loading="compassLoading" @click="runCompass">搜索</el-button>
      </div>
      <template v-if="compassResult">
        <div v-if="compassResult.assets?.length" class="gov-section" style="margin-top:8px">表（{{ compassResult.assets.length }}）</div>
        <div><el-tag v-for="a in compassResult.assets" :key="a.table" size="small" effect="plain" style="margin:0 3px 4px 0">{{ a.alias || a.table }}</el-tag></div>
        <div v-if="compassResult.objects?.length" class="gov-section" style="margin-top:8px">对象（{{ compassResult.objects.length }}）</div>
        <div><el-tag v-for="o in compassResult.objects" :key="o.code" size="small" type="warning" effect="plain" style="margin:0 3px 4px 0">{{ o.name }}</el-tag></div>
        <div v-if="compassResult.metrics?.length" class="gov-section" style="margin-top:8px">指标（{{ compassResult.metrics.length }}）</div>
        <div><el-tag v-for="m in compassResult.metrics" :key="m.key" size="small" type="primary" effect="plain" style="margin:0 3px 4px 0">{{ m.name }}</el-tag></div>
        <div v-if="compassResult.terms?.length" class="gov-section" style="margin-top:8px">术语（{{ compassResult.terms.length }}）</div>
        <div><el-tag v-for="t in compassResult.terms" :key="t.term" size="small" type="info" effect="plain" style="margin:0 3px 4px 0">{{ t.term }}</el-tag></div>
        <el-empty v-if="!compassResult.assets?.length && !compassResult.objects?.length && !compassResult.metrics?.length && !compassResult.terms?.length" :image-size="30" description="无匹配结果" />
      </template>
    </el-card>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="15">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>调用趋势（近 7 天）</template>
          <div ref="trendRef" class="ov-chart" />
        </el-card>
      </el-col>
      <el-col :md="9">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>模型用量对比</template>
          <div ref="modelRef" class="ov-chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="12">
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
      <el-col :md="12">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>用量与成本</template>
          <div class="ov-usage-list">
            <div class="ov-usage-row">
              <span>调用模型</span>
              <b>{{ (stats.by_model || []).length }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总输入 token</span>
              <b>{{ sumTokens(stats.by_model, "prompt_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总输出 token</span>
              <b>{{ sumTokens(stats.by_model, "completion_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总成本(元)</span>
              <b>{{ sumCost(stats.by_model) }}</b>
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

    <el-card shadow="never" class="ov-recent-card" style="margin-top: 12px">
      <template #header>系统运行监控</template>
      <el-row :gutter="12" v-if="runtime">
        <el-col :span="4"><el-statistic title="应用" :value="runtime.apps ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="工作流" :value="runtime.workflows ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="模型" :value="runtime.models ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="智能体" :value="runtime.agents ?? 0" /></el-col>
        <el-col :span="4">
          <div class="ov-usage-row">
            <span>AI健康</span>
            <el-tag size="small" :type="runtime.health?.status === 'healthy' ? 'success' : runtime.health?.status === 'warning' ? 'warning' : 'danger'" effect="plain">
              {{ runtime.health?.status === "healthy" ? "健康" : runtime.health?.status === "warning" ? "预警" : "严重" }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="4"><el-statistic title="近7天调用" :value="runtime.health?.calls ?? 0" /></el-col>
      </el-row>
      <div v-if="runtime" class="gov-section" style="margin-top: 8px">管道运行状态</div>
      <div v-if="runtime">
        <el-tag
          v-for="(cnt, st) in runtime.pipeline_status || {}"
          :key="st"
          size="small"
          :type="String(st) === 'success' ? 'success' : String(st) === 'failed' ? 'danger' : 'warning'"
          effect="plain"
          style="margin: 0 3px"
        >
          {{ st }}: {{ cnt }}
        </el-tag>
        <el-tag v-if="!Object.keys(runtime.pipeline_status || {}).length" size="small" type="info" effect="plain">暂无管道运行</el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card" style="margin-top: 12px">
      <template #header>
        <div class="ov-usage-row" style="justify-content: space-between">
          <span>AIP 控制台 · 运行追踪</span>
          <span style="font-size:12px;color:var(--el-text-color-secondary)">
            Agent/AI 调用运行追踪 · 用途分布 · 人工审核队列
          </span>
        </div>
      </template>
      <el-row :gutter="12" style="margin-bottom: 8px" v-if="aip">
        <el-col :span="8"><el-statistic title="运行记录" :value="aip.total ?? 0" /></el-col>
        <el-col :span="8"><el-statistic title="人工审核待办" :value="aip.pending_review ?? 0" /></el-col>
        <el-col :span="8">
          <div style="display:flex;align-items:center;gap:6px">
            <span style="font-size:12px;color:var(--el-text-color-secondary)">用途分布</span>
            <el-tag v-for="(n, u) in aip.usage_dist || {}" :key="u" size="small" type="info" effect="plain">{{ u }}: {{ n }}</el-tag>
          </div>
        </el-col>
      </el-row>
      <el-table :data="aip?.runs || []" size="small" max-height="360">
        <el-table-column prop="time" label="时间" width="100" />
        <el-table-column prop="model" label="模型" min-width="130" show-overflow-tooltip />
        <el-table-column prop="usage" label="用途" width="110" />
        <el-table-column prop="latency_ms" label="耗时(ms)" width="90" />
        <el-table-column label="结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.result === 'success' ? 'success' : 'danger'" effect="plain">{{ row.result }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Tokens" width="110" align="center">
          <template #default="{ row }">{{ row.prompt_tokens ?? 0 }} / {{ row.completion_tokens ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="费用(元)" width="90" align="center">
          <template #default="{ row }">{{ row.cost ?? 0 }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card" style="margin-top: 12px">
      <template #header>
        <div class="ov-usage-row" style="justify-content: space-between">
          <span>Agent 编排运行看板</span>
          <span style="font-size:12px;color:var(--el-text-color-secondary)">
            运行量/错误率/延迟 + 绑定工具·技能·能力矩阵
          </span>
        </div>
      </template>
      <el-row :gutter="12" style="margin-bottom: 8px" v-if="agentDash">
        <el-col :span="8"><el-statistic title="智能体总数" :value="agentDash.total_agents ?? 0" /></el-col>
        <el-col :span="8"><el-statistic title="已启用" :value="agentDash.enabled_agents ?? 0" /></el-col>
        <el-col :span="8"><el-statistic title="累计运行" :value="agentDash.total_runs ?? 0" /></el-col>
      </el-row>
      <el-table :data="agentDash?.agents || []" size="small" max-height="300">
        <el-table-column prop="name" label="智能体" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">{{ row.enabled ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="runs" label="运行" width="70" align="center" />
        <el-table-column label="错误率" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.error_rate > 0.05 ? 'danger' : row.error_rate > 0 ? 'warning' : 'success'" effect="plain">{{ (row.error_rate * 100).toFixed(1) }}%</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="avg_latency" label="延迟(ms)" width="90" align="center" />
        <el-table-column label="编排矩阵" min-width="200">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" style="margin:0 2px 2px 0">工具 {{ row.tools }}</el-tag>
            <el-tag size="small" type="warning" effect="plain" style="margin:0 2px 2px 0">技能 {{ row.skills }}</el-tag>
            <el-tag size="small" type="info" effect="plain" style="margin:0 2px 2px 0">知识 {{ row.knowledge }}</el-tag>
            <el-tag v-for="cap in (row.capabilities || []).slice(0, 3)" :key="cap" size="small" type="primary" effect="plain" style="margin:0 2px 2px 0">{{ cap }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card" style="margin-top: 12px">
      <template #header>
        <div class="ov-usage-row" style="justify-content: space-between">
          <span>AI 能力评估（影子回归）</span>
          <span style="font-size:12px;color:var(--el-text-color-secondary)">
            每行 {input, expected_keywords[], actual}，命中关键断言即通过，输出精度
          </span>
        </div>
      </template>
      <el-input
        v-model="evalSamplesText"
        type="textarea"
        :rows="5"
        placeholder='示例：[{"input":"订单金额总和","expected_keywords":["90500"],"actual":"订单金额总和是 90500"}]'
      />
      <div class="ops-bar" style="margin-top: 8px">
        <el-button type="primary" size="small" :loading="evalLoading" @click="runEval">
          运行评估
        </el-button>
        <el-button size="small" @click="loadEvalTemplate">载入示例</el-button>
        <el-tag v-if="evalResult" size="small" type="info" effect="plain">
          精度 {{ (evalResult.precision * 100).toFixed(1) }}% · {{ evalResult.passed }}/{{
            evalResult.total
          }}
        </el-tag>
      </div>
      <el-table
        v-if="evalResult?.rows?.length"
        :data="evalResult.rows"
        size="small"
        border
        max-height="220"
        style="margin-top: 8px"
      >
        <el-table-column prop="input" label="输入" min-width="180" show-overflow-tooltip />
        <el-table-column label="通过" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ok ? 'success' : 'danger'" effect="plain">
              {{ row.ok ? "通过" : "未过" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="ov-usage-row" style="justify-content: space-between">
              <span>AI 健康（近 {{ health?.days ?? 7 }} 天）</span>
              <el-button size="small" @click="loadHealth">刷新</el-button>
            </div>
          </template>
          <div v-if="health">
            <el-tag size="small" :type="health.status === 'healthy' ? 'success' : health.status === 'warning' ? 'warning' : 'danger'" effect="plain">
              {{ health.status === "healthy" ? "健康" : health.status === "warning" ? "预警" : "严重" }}
            </el-tag>
            <div class="ov-usage-row" style="margin-top: 8px">
              <span>调用</span><b>{{ health.calls }}</b>
              <span>错误率</span><b>{{ (health.error_rate * 100).toFixed(1) }}%</b>
              <span>平均延迟</span><b>{{ health.avg_latency_ms }}ms</b>
              <span>成本</span><b>{{ health.total_cost }}元</b>
            </div>
            <div v-for="(a, i) in health.alerts" :key="i" class="dq-alert__item" style="margin-top:4px">
              <el-tag size="small" :type="a.level === 'critical' ? 'danger' : 'warning'">{{ a.msg }}</el-tag>
            </div>
            <el-empty v-if="!health.alerts.length" :image-size="30" description="无告警" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="ov-usage-row" style="justify-content: space-between">
              <span>合规审计（近 {{ audit?.days ?? 7 }} 天）</span>
              <el-button size="small" @click="loadAudit">刷新</el-button>
            </div>
          </template>
          <div v-if="audit">
            <el-tag size="small" :type="audit.compliant ? 'success' : 'warning'" effect="plain">
              {{ audit.compliant ? "合规" : "存在风险" }}
            </el-tag>
            <div class="ov-usage-row" style="margin-top: 8px">
              <span>调用</span><b>{{ audit.total }}</b>
              <span>未鉴权</span><b style="color:var(--el-color-danger)">{{ audit.anonymous_calls }}</b>
              <span>失败</span><b style="color:var(--el-color-warning)">{{ audit.error_calls }}</b>
              <span>高成本</span><b>{{ audit.high_cost_calls }}</b>
            </div>
            <div v-for="(a, i) in audit.issues" :key="i" class="dq-alert__item" style="margin-top:4px">
              <el-tag size="small" type="warning">{{ a.msg }}</el-tag>
            </div>
            <el-empty v-if="!audit.issues.length" :image-size="30" description="无合规问题" />
          </div>
        </el-card>
      </el-col>
    </el-row>
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
import { getAiOverviewStats, runAiEval, getAiHealth, getAiAudit, getAiRuntime, compassSearch, getAiAipControl } from "@/api/module_ai/overview";
import { getAiAgentDashboard } from "@/api/module_ai/agent";

defineOptions({ name: "AiOverview" });

const stats = reactive<any>({});
const evalSamplesText = ref("");
const evalResult = ref<any>(null);
const evalLoading = ref(false);
const health = ref<any>(null);
const audit = ref<any>(null);
const runtime = ref<any>(null);
const compassKw = ref("");
const compassResult = ref<any>(null);
const compassLoading = ref(false);
const aip = ref<any>(null);
async function loadAip() {
  try { aip.value = (await getAiAipControl(20)).data?.data || null; } catch { aip.value = null; }
}
const agentDash = ref<any>(null);
async function loadAgentDash() {
  try { agentDash.value = (await getAiAgentDashboard()).data?.data || null; } catch { agentDash.value = null; }
}
async function runCompass() {
  if (!compassKw.value.trim()) { compassResult.value = null; return; }
  compassLoading.value = true;
  try { compassResult.value = (await compassSearch(compassKw.value)).data?.data || null; }
  catch { compassResult.value = null; }
  finally { compassLoading.value = false; }
}
async function loadRuntime() {
  try { runtime.value = (await getAiRuntime()).data?.data || null; } catch { runtime.value = null; }
}
async function loadHealth() {
  try { health.value = (await getAiHealth()).data?.data || null; } catch { health.value = null; }
}
async function loadAudit() {
  try { audit.value = (await getAiAudit()).data?.data || null; } catch { audit.value = null; }
}
function loadEvalTemplate() {
  evalSamplesText.value = JSON.stringify([
    { input: "订单金额总和", expected_keywords: ["90500"], actual: "订单金额总和是 90500" },
    { input: "设备健康度", expected_keywords: ["%"], actual: "设备健康度为 95.5%" },
  ]);
}
async function runEval() {
  evalLoading.value = true;
  try {
    let samples: any[] = [];
    try {
      samples = JSON.parse(evalSamplesText.value || "[]");
    } catch {
      ElMessage.warning("样本 JSON 格式有误");
      return;
    }
    const r = await runAiEval(samples);
    evalResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.message || "评估失败");
  } finally {
    evalLoading.value = false;
  }
}
const trendRef = ref<HTMLElement>();
const modelRef = ref<HTMLElement>();
let trendChart: echarts.ECharts | null = null;
let modelChart: echarts.ECharts | null = null;

function sumTokens(list: any[], key: string) {
  return (list || []).reduce((s, x) => s + (x[key] || 0), 0);
}
function sumCost(list: any[]) {
  const v = (list || []).reduce((s, x) => s + (x.cost || 0), 0);
  return v.toFixed(2);
}

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
  if (trendRef.value) {
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
  if (modelRef.value) {
    modelChart = modelChart || echarts.init(modelRef.value);
    const m = stats.by_model || [];
    modelChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 30, bottom: 40 },
      xAxis: { type: "category", data: m.map((x: any) => x.name), axisLabel: { rotate: 20 } },
      yAxis: { type: "value" },
      series: [
        {
          name: "调用",
          type: "bar",
          data: m.map((x: any) => x.count),
          itemStyle: { color: "#67c23a" },
        },
      ],
    });
  }
}

function resize() {
  trendChart?.resize();
  modelChart?.resize();
}

onMounted(() => {
  load();
  loadHealth();
  loadAudit();
  loadRuntime();
  loadAip();
  loadAgentDash();
  window.addEventListener("resize", resize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  trendChart?.dispose();
  modelChart?.dispose();
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
.ov-usage-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
.ov-usage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.ov-usage-row b {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}
.ov-recent-card {
  margin-bottom: 12px;
}
.compass-bar {
  display: flex;
  gap: 8px;
}
</style>

<style lang="scss">
/* 覆盖全局 .app-container(flex column;height:100%)：控制台改为块级自然流，避免卡片被 flex 压缩/重叠 */
.app-container.ai-overview-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>
