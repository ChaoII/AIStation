<template>
  <VChart v-if="points.length" :option="option" :style="{ height: height + 'px' }" autoresize />
  <div v-else class="mini-empty" :style="{ height: height + 'px' }">暂无数据</div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent]);

/**
 * 单指标趋势小图（训练详情 / 评估详情共用）。
 *
 * 页面上会有 N 张这样的图（N ≈ 指标数），所以这里**刻意做轻**：
 * - `animation: false`：N 张图同时跑过渡动画会持续占用主线程；
 * - 不注册 legend：每图只有 1 条线，图例占地方且每图都要算布局；
 * - `sampling: "lttb"`：按视觉保真抽稀，保留尖峰（等间隔丢点会把 loss 突刺抹平）；
 * - `connectNulls: true`：单条曲线间歇缺值时仍连成完整趋势，避免线碎成一段段。
 */
const props = withDefaults(
  defineProps<{
    /** [[x, y], ...]，x 可为 null（该行没有 step） */
    points: [number | null, number][];
    color?: string;
    height?: number;
    /**
     * tooltip 里的 x 轴维度名。不传则按「有没有点」自动给 step / epoch；
     * 评估详情页的历史趋势 x 是「评估次序」，需要覆盖成自定义文案。
     */
    xLabel?: string;
  }>(),
  {
    color: "#409eff",
    height: 140,
    xLabel: "",
  }
);

const option = computed(() => {
  const pts = props.points;
  // 只要有任一点带 step 就整体用 step 轴，避免同一张图混两套量纲
  const stepAxis = pts.some((p) => p[0] != null);
  const unit = props.xLabel || (stepAxis ? "step" : "epoch");
  return {
    animation: false,
    grid: { left: 8, right: 14, top: 10, bottom: 22, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      confine: true,
      formatter: (params: any) => {
        const p = params?.[0];
        if (!p) return "";
        const x = p.value?.[0];
        const head = x == null ? "" : `${unit} ${x}<br/>`;
        return `${head}${p.seriesName}：<b>${p.value?.[1]}</b>`;
      },
    },
    xAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { fontSize: 10, color: "#909399", margin: 8 },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#f0f2f5" } },
      axisLabel: { fontSize: 10, color: "#909399" },
    },
    series: [
      {
        name: "值",
        type: "line",
        showSymbol: false,
        connectNulls: true,
        sampling: "lttb",
        lineStyle: { width: 1.5, color: props.color },
        itemStyle: { color: props.color },
        areaStyle: { color: props.color, opacity: 0.08 },
        data: pts,
      },
    ],
  };
});
</script>

<style scoped lang="scss">
.mini-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
  font-size: var(--el-font-size-base);
  background: var(--el-fill-color-blank);
  border-radius: var(--el-border-radius-base);
}
</style>
