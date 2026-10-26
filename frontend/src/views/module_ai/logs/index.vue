<!-- AI 调用日志 -->
<template>
  <div class="app-container ai-logs-page">
    <!-- 统计卡片 -->
    <el-row :gutter="12" class="log-cards">
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="log-card">
          <el-statistic title="总调用" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="log-card">
          <el-statistic
            title="成功率"
            :value="stats.success_rate * 100"
            :precision="1"
            suffix="%"
          />
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="log-card">
          <el-statistic title="平均耗时" :value="stats.avg_latency_ms" suffix="ms" />
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never" class="log-card">
          <el-statistic title="失败数" :value="stats.error" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表：刷新统计/导出 归入统计区头部（不再单独占一行游离按钮条） -->
    <el-row :gutter="12" class="log-charts">
      <el-col v-if="stats.trend?.length" :md="14">
        <el-card shadow="never" class="log-chart-card">
          <template #header>
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
          </template>
          <div ref="trendRef" class="log-chart" />
        </el-card>
      </el-col>
      <el-col v-if="stats.by_model?.length" :md="10">
        <el-card shadow="never" class="log-chart-card">
          <template #header>模型调用分布</template>
          <div ref="modelRef" class="log-chart" />
        </el-card>
      </el-col>
    </el-row>

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
            <el-table-column
              prop="model_name"
              label="智能体 / 模型"
              min-width="180"
              show-overflow-tooltip
            >
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

<style scoped>
.ai-logs-page {
  /* 继承 .app-container 的 16px padding（此前 padding:0 让内容紧贴侧边栏） */
  padding: 16px;
}
/* 覆盖全局 `.app-container > .el-row { flex:1 }`（那是给单行栅格页的）：
   统计行/图表行按内容高度排列，表格区仍由 PageContent 撑满剩余 */
.ai-logs-page > .el-row {
  flex: 0 0 auto;
}
.log-cards {
  margin-bottom: 16px;
}
.log-card {
  margin-bottom: 12px;
}
.log-charts {
  margin-bottom: 16px;
}
.log-chart-card {
  margin-bottom: 12px;
}
.log-chart {
  height: 220px;
}
/* 图表卡头部：标题 + 统计操作（同一区域，符合「统计区」场景） */
.log-chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.log-chart-head__ops {
  display: flex;
  gap: 8px;
  align-items: center;
}
.log-error {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: var(--el-font-size-base);
  color: var(--el-color-danger);
}
</style>
