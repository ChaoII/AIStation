<!-- AI 调用日志 -->
<template>
  <div class="app-container ai-logs-page">
    <el-card shadow="never" class="ai-logs-shell">
      <div class="ai-logs-shell__body">
        <!-- 统计 -->
        <div class="log-stats">
          <div class="log-stat">
            <div class="log-stat__title">{{ t("ai_logs.totalCalls") }}</div>
            <div class="log-stat__value">{{ stats.total }}</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">{{ t("ai_logs.successRate") }}</div>
            <div class="log-stat__value">{{ (stats.success_rate * 100).toFixed(1) }}%</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">{{ t("ai_logs.avgLatency") }}</div>
            <div class="log-stat__value">{{ stats.avg_latency_ms }} ms</div>
          </div>
          <div class="log-stat">
            <div class="log-stat__title">{{ t("ai_logs.errorCount") }}</div>
            <div class="log-stat__value">{{ stats.error }}</div>
          </div>
        </div>

        <!-- 图表 -->
        <div class="log-charts">
          <div v-if="stats.trend?.length" class="log-chart-block">
            <div class="log-chart-head">
              <span>{{ t("ai_logs.callTrend", { days: statsDays }) }}</span>
              <div class="log-chart-head__ops">
                <el-button size="small" :loading="statsLoading" @click="loadStats">
                  {{ t("ai_logs.refreshStats") }}
                </el-button>
                <el-button size="small" type="primary" plain :loading="exporting" @click="doExport">
                  {{ t("ai_logs.exportCsv") }}
                </el-button>
              </div>
            </div>
            <div ref="trendRef" class="log-chart" />
          </div>
          <div v-if="stats.by_model?.length" class="log-chart-block log-chart-block--model">
            <div class="log-chart-head">
              <span>{{ t("ai_logs.modelDist") }}</span>
            </div>
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
                  <el-empty :image-size="80" :description="t('ai_logs.noLogs')" />
                </template>
                <el-table-column fixed :label="t('ai_logs.serial')" min-width="60">
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="created_time"
                  :label="t('ai_logs.time')"
                  min-width="180"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="model_name"
                  :label="t('ai_logs.model')"
                  min-width="180"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{ row.model_name || "—" }}</template>
                </el-table-column>
                <el-table-column
                  prop="usage"
                  :label="t('ai_logs.usage')"
                  min-width="100"
                  align="center"
                />
                <el-table-column
                  prop="latency_ms"
                  :label="t('ai_logs.latency')"
                  min-width="100"
                  align="center"
                >
                  <template #default="{ row }">{{ row.latency_ms }} ms</template>
                </el-table-column>
                <el-table-column
                  prop="prompt_tokens"
                  :label="t('ai_logs.promptTokens')"
                  min-width="110"
                  align="center"
                >
                  <template #default="{ row }">{{ row.prompt_tokens ?? 0 }}</template>
                </el-table-column>
                <el-table-column
                  prop="completion_tokens"
                  :label="t('ai_logs.completionTokens')"
                  min-width="110"
                  align="center"
                >
                  <template #default="{ row }">{{ row.completion_tokens ?? 0 }}</template>
                </el-table-column>
                <el-table-column
                  prop="cost"
                  :label="t('ai_logs.costYuan')"
                  min-width="110"
                  align="center"
                >
                  <template #default="{ row }">
                    {{ row.cost != null ? Number(row.cost).toFixed(4) : "—" }}
                  </template>
                </el-table-column>
                <el-table-column :label="t('ai_logs.result')" min-width="90" align="center">
                  <template #default="{ row }">
                    <el-tag
                      :type="
                        row.result === 'success'
                          ? 'success'
                          : row.result === 'cancelled'
                            ? 'info'
                            : row.result === 'pending'
                              ? 'warning'
                              : 'danger'
                      "
                      size="small"
                    >
                      {{
                        row.result === "success"
                          ? t("ai_logs.success")
                          : row.result === "cancelled"
                            ? t("ai_logs.cancelled")
                            : row.result === "pending"
                              ? t("ai_logs.pendingReview")
                              : t("ai_logs.failed")
                      }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="error"
                  :label="t('ai_logs.error')"
                  min-width="240"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{ row.error || "—" }}</template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </div>
    </el-card>

    <!-- 日志详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="t('ai_logs.callDetail')" size="480px" append-to-body>
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item :label="t('ai_logs.time')">
          {{ detail.created_time }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.model')">
          {{ detail.model_name || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.usage')">
          {{ detail.usage || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.latency')">
          {{ detail.latency_ms }} ms
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.promptTokens')">
          {{ detail.prompt_tokens ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.completionTokens')">
          {{ detail.completion_tokens ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.costYuan')">
          {{ detail.cost != null ? Number(detail.cost).toFixed(4) : "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.result')">
          <el-tag
            :type="
              detail.result === 'success'
                ? 'success'
                : detail.result === 'cancelled'
                  ? 'info'
                  : detail.result === 'pending'
                    ? 'warning'
                    : 'danger'
            "
            size="small"
          >
            {{
              detail.result === "success"
                ? t("ai_logs.success")
                : detail.result === "cancelled"
                  ? t("ai_logs.cancelled")
                  : detail.result === "pending"
                    ? t("ai_logs.pendingReview")
                    : t("ai_logs.failed")
            }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.appId')">
          {{ detail.app_id ?? "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.userId')">
          {{ detail.user_id ?? "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.error')">
          <pre v-if="detail.error" class="log-error">{{ detail.error }}</pre>
          <span v-else>—</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
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

const { t } = useI18n();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:assistant",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "usage",
      label: t("ai_logs.usage"),
      type: "select",
      options: [
        { label: t("ai_logs.chat"), value: "chat" },
        { label: t("ai_logs.app"), value: "app" },
        { label: t("ai_logs.assistant"), value: "assistant" },
      ],
      attrs: {
        placeholder: t("ai_logs.selectUsage"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "result",
      label: t("ai_logs.result"),
      type: "select",
      options: [
        { label: t("ai_logs.success"), value: "success" },
        { label: t("ai_logs.failed"), value: "error" },
      ],
      attrs: {
        placeholder: t("ai_logs.selectResult"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "keyword",
      label: t("ai_logs.keyword"),
      type: "input",
      attrs: { placeholder: t("ai_logs.keywordPlaceholder"), clearable: true },
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
      legend: { data: [t("ai_logs.chartCalls"), t("ai_logs.chartErrors")], top: 0, right: 8 },
      grid: { left: 44, right: 20, top: 36, bottom: 26 },
      xAxis: { type: "category", data: (stats.trend || []).map((t: any) => t.date) },
      yAxis: { type: "value" },
      series: [
        {
          name: t("ai_logs.chartCalls"),
          type: "line",
          smooth: true,
          data: (stats.trend || []).map((t: any) => t.count),
        },
        {
          name: t("ai_logs.chartErrors"),
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
    ElMessage.success(t("ai_logs.exportedRows", { count: rows.length }));
  } catch {
    ElMessage.error(t("ai_logs.exportFailed"));
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
