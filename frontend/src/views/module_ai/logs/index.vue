<!-- AI 调用日志 -->
<template>
  <div class="app-container ai-logs-page">
    <el-card shadow="never" class="ai-logs-shell">
      <div class="ai-logs-shell__body">
        <!-- 统计 -->
        <div class="log-stats">
          <div class="log-stat">
            <div class="log-stat__title">总调用</div>
            <div class="log-stat__value">{{ stats.total }}</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">成功率</div>
            <div class="log-stat__value">{{ (stats.success_rate * 100).toFixed(1) }}%</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">平均耗时</div>
            <div class="log-stat__value">{{ stats.avg_latency_ms }} ms</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">失败数</div>
            <div class="log-stat__value">{{ stats.error }}</div>
          </div>
        </div>

        <!-- 图表 -->
        <div class="log-charts">
          <div v-if="stats.trend?.length" class="log-chart-block">
            <div class="log-chart-head">
              <span>调用趋势（近 {{ statsDays }} 天）</span>
              <div class="log-chart-head__ops">
                <el-button size="small" :loading="statsLoading" @click="loadStats">
                  刷新统计
                </el-button>
                <el-button size="small" type="primary" plain :loading="exporting" @click="doExport">
                  导出 CSV
                </el-button>
              </div>
            </div>
            <div ref="trendRef" class="log-chart" />
          </div>
          <div v-if="stats.by_model?.length" class="log-chart-block log-chart-block--model">
            <div class="log-chart-head"><span>模型调用分布</span></div>
            <div ref="modelRef" class="log-chart" />
          </div>
        </div>

        <!-- 搜索 + 表格 -->
        <PageSearch
          ref="searchRef"
          :search-config="searchConfig"
          @query-click="handleQueryClick"
          @reset-click="handleResetClick"
        />

        <PageContent ref="contentRef" :content-config="contentConfig">
          <template #table="{ data, loading, tableRef, pagination }">
            <div class="data-table__content">
              <el-table
                :ref="tableRef as any"
                v-loading="loading"
                :data="data"
                height="100%"
                border
                stripe
                @row-click="openDetail"
              >
                <template #empty>
                  <el-empty :image-size="80" description="暂无调用日志" />
                </template>
                <el-table-column fixed label="序号" min-width="60">
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="created_time"
                  label="时间"
                  min-width="180"
                  show-overflow-tooltip
                />
                <el-table-column prop="model_name" label="模型" min-width="180" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.model_name || "—" }}</template>
                </el-table-column>
                <el-table-column prop="usage" label="用途" min-width="100" align="center" />
                <el-table-column prop="latency_ms" label="耗时" min-width="100" align="center">
                  <template #default="{ row }">{{ row.latency_ms }} ms</template>
                </el-table-column>
                <el-table-column label="结果" min-width="90" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
                      {{ row.result === "success" ? "成功" : "失败" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="error" label="错误" min-width="240" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.error || "—" }}</template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </div>
    </el-card>

    <!-- 日志详情抽屉 -->
    <el-drawer v-model="detailVisible" title="调用详情" size="480px" append-to-body>
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item label="时间">{{ detail.created_time }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ detail.model_name || "—" }}</el-descriptions-item>
        <el-descriptions-item label="用途">{{ detail.usage || "—" }}</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ detail.latency_ms }} ms</el-descriptions-item>
        <el-descriptions-item label="结果">
          <el-tag :type="detail.result === 'success' ? 'success' : 'danger'" size="small">
            {{ detail.result === "success" ? "成功" : "失败" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="应用ID">{{ detail.app_id ?? "—" }}</el-descriptions-item>
        <el-descriptions-item label="用户ID">{{ detail.user_id ?? "—" }}</el-descriptions-item>
        <el-descriptions-item label="错误">
          <pre v-if="detail.error" class="log-error">{{ detail.error }}</pre>
          <span v-else>—</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import * as echarts from "echarts";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { getAiLogExport, getAiLogList, getAiLogStats } from "@/api/module_ai/logs";

defineOptions({
  name: "AiLogs",
  inheritAttrs: false,
});

const { searchRef, contentRef, handleQueryClick, handleResetClick } = useCrudList();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:assistant",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "usage",
      label: "用途",
      type: "select",
      options: [
        { label: "聊天", value: "chat" },
        { label: "应用", value: "app" },
        { label: "助手", value: "assistant" },
      ],
      attrs: { placeholder: "请选择用途", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "result",
      label: "结果",
      type: "select",
      options: [
        { label: "成功", value: "success" },
        { label: "失败", value: "error" },
      ],
      attrs: { placeholder: "请选择结果", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "keyword",
      label: "关键字",
      type: "input",
      attrs: { placeholder: "模型名或错误信息", clearable: true },
    },
  ],
});

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:assistant",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAiLogList(params);
    return {
      total: res.data.data?.total ?? 0,
      list: res.data.data?.items ?? [],
    };
  },
});

// ---- 统计 / 图表 / 详情 / 导出 ----
const stats = reactive<any>({
  total: 0,
  success_rate: 0,
  avg_latency_ms: 0,
  error: 0,
  by_model: [],
  trend: [],
});
const statsDays = ref(7);
const statsLoading = ref(false);
const trendRef = ref<HTMLElement>();
const modelRef = ref<HTMLElement>();
let trendChart: echarts.ECharts | null = null;
let modelChart: echarts.ECharts | null = null;

async function loadStats() {
  statsLoading.value = true;
  try {
    const r = await getAiLogStats(statsDays.value);
    Object.assign(stats, r.data?.data || {});
    await nextTick();
    renderCharts();
  } catch {
    // 统计失败不阻断列表
  } finally {
    statsLoading.value = false;
  }
}

function renderCharts() {
  if (trendRef.value) {
    trendChart = trendChart || echarts.init(trendRef.value);
    trendChart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["调用", "失败"], top: 0, right: 8 },
      grid: { left: 44, right: 20, top: 36, bottom: 26 },
      xAxis: { type: "category", data: (stats.trend || []).map((t: any) => t.date) },
      yAxis: { type: "value" },
      series: [
        {
          name: "调用",
          type: "line",
          smooth: true,
          data: (stats.trend || []).map((t: any) => t.count),
        },
        {
          name: "失败",
          type: "line",
          smooth: true,
          data: (stats.trend || []).map((t: any) => t.error),
        },
      ],
    });
  }
  if (modelRef.value) {
    modelChart = modelChart || echarts.init(modelRef.value);
    modelChart.setOption({
      tooltip: { trigger: "item" },
      // 模型数量多、名称长：隐藏外部标签，统一用滚动图例，避免标签互相遮挡
      legend: {
        type: "scroll",
        bottom: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { fontSize: 12 },
      },
      series: [
        {
          type: "pie",
          radius: ["34%", "62%"],
          center: ["50%", "44%"],
          data: (stats.by_model || []).map((m: any) => ({ name: m.name, value: m.count })),
          label: { show: false },
          labelLine: { show: false },
        },
      ],
    });
  }
}

function resizeCharts() {
  trendChart?.resize();
  modelChart?.resize();
}

const detailVisible = ref(false);
const detail = ref<any>(null);
function openDetail(row: any) {
  detail.value = row;
  detailVisible.value = true;
}

const exporting = ref(false);
async function doExport() {
  exporting.value = true;
  try {
    const r: any = await getAiLogExport(30);
    const rows = r.data?.data || [];
    const cols = [
      "id",
      "created_time",
      "model_name",
      "usage",
      "latency_ms",
      "result",
      "error",
      "app_id",
      "user_id",
    ];
    const esc = (v: any) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv =
      "\ufeff" +
      cols.join(",") +
      "\n" +
      rows.map((x: any) => cols.map((c) => esc(x[c])).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ai_call_logs.csv";
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success(`已导出 ${rows.length} 条日志`);
  } catch {
    ElMessage.error("导出失败");
  } finally {
    exporting.value = false;
  }
}

onMounted(() => {
  loadStats();
  window.addEventListener("resize", resizeCharts);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCharts);
  trendChart?.dispose();
  modelChart?.dispose();
});
</script>

<style lang="scss">
/* 非 scoped：全局 .app-container 为 flex column + height:100% + overflow:auto，
   用 scoped 覆盖在 keep-alive/HMR 下曾出现 hash 不同步（项目已踩过），故用非 scoped + 唯一类名。 */
.app-container.ai-logs-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 16px;
  box-sizing: border-box;
}

/* 白色面板：铺满剩余高度，蓝灰色边框（market-shell 同款） */
.ai-logs-page .ai-logs-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
}

.ai-logs-page .ai-logs-shell > .el-card__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
}

.ai-logs-page .ai-logs-shell__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 搜索/表格卡片融入白色面板：去掉内层卡片边框，做到一整块白底 */
.ai-logs-page .search-container,
.ai-logs-page .data-table {
  border: none;
  box-shadow: none;
}

/* 统计：一排浅色块 */
.ai-logs-page .log-stats {
  flex: 0 0 auto;
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.ai-logs-page .log-stat {
  flex: 1 1 0;
  min-width: 0;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
  padding: 16px;
}
.ai-logs-page .log-stat__title {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.ai-logs-page .log-stat__value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--el-text-color-primary);
}

/* 图表：两个带边框的块 */
.ai-logs-page .log-charts {
  flex: 0 0 auto;
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.ai-logs-page .log-chart-block {
  flex: 1.6 1 0;
  min-width: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  padding: 12px;
}
.ai-logs-page .log-chart-block--model {
  flex: 1 1 0;
}
.ai-logs-page .log-chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.ai-logs-page .log-chart-head__ops {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ai-logs-page .log-chart {
  height: 220px;
}

.ai-logs-page .log-error {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: var(--el-font-size-base);
  color: var(--el-color-danger);
}
</style>
