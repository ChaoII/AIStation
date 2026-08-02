<template>
  <div ref="chartRef" :style="{ height: height }" />
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import * as echarts from "echarts/core";
import { LineChart, BarChart, PieChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

const props = defineProps<{ option: Record<string, unknown>; height?: string }>();
const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

function render() {
  if (chartRef.value) {
    if (!chart) chart = echarts.init(chartRef.value);
    chart.setOption(props.option as any);
  }
}

onMounted(() => {
  render();
  window.addEventListener("resize", handleResize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
  chart = null;
});
function handleResize() {
  chart?.resize();
}
watch(() => props.option, () => render(), { deep: true });
</script>
