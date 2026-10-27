<!-- 折线趋势图：调用日志（近7天调用）/ MCP 会话（近N天工具调用）共用。
     趋势一律用折线图（line）表达，不用柱状；紧凑高度、无图例。 -->
<template>
  <VChart v-if="points.length" :option="option" :style="{ height: height + 'px' }" autoresize />
  <div v-else class="trend-line-empty" :style="{ height: height + 'px' }">
    {{ emptyText }}
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent]);

const props = withDefaults(
  defineProps<{
    /** [{ label, value }, ...]，label 为 x 轴（如日期），value 为数值 */
    points: { label: string; value: number }[];
    /** 折线颜色 */
    color?: string;
    height?: number;
    emptyText?: string;
  }>(),
  {
    color: "#4080FF",
    height: 120,
    emptyText: "",
  }
);

const option = computed(() => ({
  animation: false,
  grid: { left: 8, right: 14, top: 14, bottom: 22, containLabel: true },
  tooltip: {
    trigger: "axis",
    axisPointer: { type: "line" },
    confine: true,
  },
  xAxis: {
    type: "category",
    boundaryGap: false,
    data: props.points.map((p) => p.label),
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { fontSize: 10, color: "#909399", margin: 8 },
  },
  yAxis: {
    type: "value",
    scale: true,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: "rgba(144,147,153,0.2)" } },
    axisLabel: { fontSize: 10, color: "#909399" },
  },
  series: [
    {
      type: "line",
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: props.color },
      itemStyle: { color: props.color },
      areaStyle: { color: props.color, opacity: 0.08 },
      data: props.points.map((p) => p.value),
    },
  ],
}));
</script>

<style scoped>
.trend-line-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
  font-size: var(--el-font-size-base);
  background: var(--el-fill-color-blank);
  border-radius: var(--el-border-radius-base);
}
</style>
