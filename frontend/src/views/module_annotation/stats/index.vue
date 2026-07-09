<template>
  <div class="app-container annotation-stats-page">
    <!-- Metric Cards -->
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :xs="12" :sm="6" v-for="card in metricCards" :key="card.key">
        <el-card shadow="never" class="stat-card" :class="`stat-card--${card.color}`">
          <div class="stat-card__label">{{ card.label }}</div>
          <div class="stat-card__value">{{ formatNum(card.value) }}</div>
          <div class="stat-card__hint">{{ card.hint }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Dataset Selector + Charts -->
    <el-row :gutter="16">
      <el-col :span="24" style="margin-bottom:16px">
        <el-card shadow="never">
          <template #header>
            <span style="font-weight:600;font-size:14px">数据集详情</span>
            <el-select v-model="selectedDatasetId" placeholder="选择数据集" style="width:240px;margin-left:12px" clearable @change="loadDatasetStats">
              <el-option v-for="ds in datasetOptions" :key="ds.id" :label="ds.name" :value="ds.id" />
            </el-select>
          </template>
          <div v-if="!selectedDatasetId" style="text-align:center;padding:40px 0;color:#c0c4cc">请选择数据集查看详情</div>
          <div v-else-if="dsLoading" style="text-align:center;padding:40px 0">加载中...</div>
          <template v-else>
            <el-row :gutter="16">
              <el-col :xs="24" :sm="8">
                <div class="chart-box">
                  <div class="chart-title">类别分布</div>
                  <v-chart v-if="classChartOption" :option="classChartOption" style="height:260px" autoresize />
                  <div v-else class="chart-empty">暂无数据</div>
                </div>
              </el-col>
              <el-col :xs="24" :sm="8">
                <div class="chart-box">
                  <div class="chart-title">图片标注状态</div>
                  <v-chart v-if="statusChartOption" :option="statusChartOption" style="height:260px" autoresize />
                  <div v-else class="chart-empty">暂无数据</div>
                </div>
              </el-col>
              <el-col :xs="24" :sm="8">
                <div class="chart-box">
                  <div class="chart-title">分辨率分布</div>
                  <v-chart v-if="resChartOption" :option="resChartOption" style="height:260px" autoresize />
                  <div v-else class="chart-empty">暂无数据</div>
                </div>
              </el-col>
            </el-row>
            <el-row :gutter="16" style="margin-top:16px">
              <el-col :span="24">
                <div class="chart-box">
                  <div class="chart-title">每日标注趋势（近30天）</div>
                  <v-chart v-if="trendChartOption" :option="trendChartOption" style="height:240px" autoresize />
                  <div v-else class="chart-empty">暂无数据</div>
                </div>
              </el-col>
            </el-row>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "AnnotationStats", inheritAttrs: false });

import { ref, reactive, computed, onMounted } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { PieChart, BarChart, LineChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";

use([PieChart, BarChart, LineChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent]);

const overview = reactive<any>({});
const selectedDatasetId = ref<number | undefined>();
const dsStats = ref<any>(null);
const dsLoading = ref(false);
const datasetOptions = ref<any[]>([]);

const metricCards = computed(() => [
  { key: "ds", label: "数据集", value: overview.dataset_count || 0, hint: "已注册数据集", color: "primary" },
  { key: "task", label: "标注任务", value: overview.task_count || 0, hint: "全部标注任务", color: "success" },
  { key: "img", label: "图片总数", value: overview.image_count || 0, hint: "所有数据集图片", color: "warning" },
  { key: "ann", label: "已标注图片", value: overview.annotated_image_count || 0, hint: "已完成标注", color: "danger" },
]);

function formatNum(n: number) {
  if (n >= 10000) return (n / 10000).toFixed(1) + "w";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

const classChartOption = computed(() => {
  const dist = dsStats.value?.class_distribution || [];
  if (!dist.length) return null;
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { type: "scroll", orient: "vertical", right: 10, top: 10, bottom: 10, textStyle: { fontSize: 11 } },
    series: [{
      type: "pie", radius: ["30%", "70%"], center: ["35%", "50%"],
      label: { show: false },
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0,0,0,0.5)" } },
      data: dist.slice(0, 20).map((d: any) => ({ name: d.class_name, value: d.count })),
    }],
  };
});

const statusChartOption = computed(() => {
  const s = dsStats.value;
  if (!s) return null;
  const data = [
    { name: "未标注", value: s.unannotated_count || 0 },
    { name: "标注中", value: s.in_progress_count || 0 },
    { name: "已标注", value: s.annotated_count || 0 },
  ];
  if (!data.some(d => d.value > 0)) return null;
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    series: [{
      type: "pie", radius: ["40%", "70%"], center: ["50%", "50%"],
      label: { show: true, formatter: "{b}\n{d}%" },
      color: ["#c0c4cc", "#e6a23c", "#67c23a"],
      data,
    }],
  };
});

const resChartOption = computed(() => {
  const dist = dsStats.value?.resolution_distribution || [];
  if (!dist.length) return null;
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: dist.map((d: any) => `${d.width}x${d.height}`), axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: "value" },
    series: [{ type: "bar", data: dist.map((d: any) => d.count), itemStyle: { color: "#409eff" }, barMaxWidth: 40 }],
  };
});

const trendChartOption = computed(() => {
  const trend = overview.daily_trend || [];
  if (!trend.length) return null;
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: trend.map((d: any) => d.date), axisLabel: { fontSize: 10 } },
    yAxis: { type: "value", minInterval: 1 },
    series: [{
      type: "line", data: trend.map((d: any) => d.count), smooth: true,
      areaStyle: { color: "rgba(64,158,255,0.12)" },
      lineStyle: { color: "#409eff", width: 2 },
      itemStyle: { color: "#409eff" },
    }],
  };
});

async function loadDatasetStats() {
  if (!selectedDatasetId.value) { dsStats.value = null; return; }
  dsLoading.value = true;
  try {
    const r = await AnnotationAPI.getDatasetStats(selectedDatasetId.value);
    dsStats.value = r.data?.data || null;
  } catch { dsStats.value = null; }
  finally { dsLoading.value = false; }
}

onMounted(async () => {
  try {
    const [ov, ds] = await Promise.all([
      AnnotationAPI.getOverview(),
      AnnotationAPI.getDatasetList({ page_no: 1, page_size: 999 }),
    ]);
    Object.assign(overview, ov.data?.data || {});
    datasetOptions.value = ds.data?.data?.items || ds.data?.data || [];
  } catch {}
});
</script>

<style>
.annotation-stats-page { padding: 16px; }
.stat-card { border: 1px solid #e8e8e8; border-radius: 8px; height: 100%; }
.stat-card__label { font-size: 13px; color: #909399; margin-bottom: 6px; }
.stat-card__value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; letter-spacing: -.02em; }
.stat-card__hint { font-size: 12px; color: #c0c4cc; margin-top: 6px; }
.stat-card--primary .stat-card__value { color: #409eff; }
.stat-card--success .stat-card__value { color: #67c23a; }
.stat-card--warning .stat-card__value { color: #e6a23c; }
.stat-card--danger .stat-card__value { color: #f56c6c; }
.chart-box { border: 1px solid #ebeef5; border-radius: 6px; padding: 16px; background: #fff; }
.chart-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 12px; }
.chart-empty { height: 260px; display: flex; align-items: center; justify-content: center; color: #c0c4cc; font-size: 13px; }
</style>
