<template>
  <div class="time-series-canvas">
    <v-chart
      ref="chartRef"
      class="time-series-canvas__chart"
      :option="option"
      autoresize
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @click="onChartClick"
    />
    <div v-if="!data.length" class="time-series-canvas__empty">
      <el-empty description="暂无序列数据" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkAreaComponent,
} from "echarts/components";
import type { TimeSeriesSegment } from "../../../api/module_annotation/timeSeries";
import { clampTimeRange, type TimeRange } from "./useTimeSeriesEventTool";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent]);

/** 已创建区间（由用户拖选产生，尚未落入外部 segments）。 */
export interface CreatedRegion extends TimeRange {
  id: string;
}

/** 已更新/移除的区间（经用户拖拽调整/删除）。 */
export interface ChangedRegion extends TimeRange {
  id: string;
}

/** 序列数据点：time 为时间列原始值（time_unit 决定的单位），value 为数值列值。 */
export interface SeriesPoint {
  time: number;
  value: number;
}

const props = withDefaults(
  defineProps<{
    /** 序列数据（已解析为 {time, value} 数组，x 轴时间为原始值，非日期统一换算）。 */
    data?: SeriesPoint[];
    /** 外部时间序列片段（映射为 markArea 高亮）。 */
    segments?: TimeSeriesSegment[];
    /** 事件类别列表（供默认取色）。 */
    classes?: any[];
    /** 当前选中片段 id（高亮描边）。 */
    selectedId?: string;
    /** 片段颜色函数：入参 `(segment, classes)`，返回 CSS 颜色。缺省用配色表。 */
    colorFor?: (segment: TimeSeriesSegment, classes: any[]) => string;
    /** 序列时间范围 `[start_time, end_time]`，用于钳制拖选区间与 x 轴刻度。缺省取数据最小/最大值。 */
    range?: TimeRange;
  }>(),
  {
    data: () => [],
    segments: () => [],
    classes: () => [],
    selectedId: "",
    colorFor: undefined,
    range: undefined,
  }
);

const emit = defineEmits<{
  /** 用户拖选生成新区间（尚未落入外部 segments）。 */
  (e: "createRegion", region: CreatedRegion): void;
  /** 用户修改已有区间（界面预留，由工作台驱动编辑）。 */
  (e: "updateRegion", region: ChangedRegion): void;
  /** 用户删除已有区间（界面预留，由工作台驱动删除）。 */
  (e: "removeRegion", region: ChangedRegion): void;
  /** 点击已有区间（选中）。 */
  (e: "regionClick", region: ChangedRegion): void;
}>();

const chartRef = ref<InstanceType<typeof VChart> | null>(null);

/** 缺省取色板：使用 Element 语义色变量，避免写死主题色。 */
const PALETTE = [
  "var(--el-color-primary)",
  "var(--el-color-success)",
  "var(--el-color-warning)",
  "var(--el-color-danger)",
  "var(--el-color-info)",
];

function colorOf(segment: TimeSeriesSegment): string {
  if (props.colorFor) return props.colorFor(segment, props.classes);
  return PALETTE[Math.abs(segment.label_id) % PALETTE.length];
}

/** 序列时间范围（钳制与 x 轴刻度用）。 */
const rangeStart = computed(() => {
  if (props.range) return props.range.start;
  const times = props.data.map((d) => d.time);
  return times.length ? Math.min(...times) : 0;
});
const rangeEnd = computed(() => {
  if (props.range) return props.range.end;
  const times = props.data.map((d) => d.time);
  return times.length ? Math.max(...times) : 1;
});

/** 拖选过程中的临时预览区间（以 markArea 渲染）。 */
const previewRange = ref<TimeRange | null>(null);

/** echarts 折线图 option：x 轴为时间（原始值），y 轴为数值；markArea 渲染区间高亮。 */
const option = computed(() => {
  const markAreaData: any[] = props.segments.map((seg) => [
    {
      name: seg.id,
      xAxis: seg.start,
      itemStyle: { color: colorOf(seg), opacity: 0.35 },
      label: { show: false },
    },
    { xAxis: seg.end },
  ]);
  if (previewRange.value) {
    markAreaData.push([
      {
        xAxis: previewRange.value.start,
        itemStyle: { color: "var(--el-color-primary)", opacity: 0.25 },
        label: { show: false },
      },
      { xAxis: previewRange.value.end },
    ]);
  }
  return {
    backgroundColor: "transparent",
    grid: { left: 16, right: 16, top: 16, bottom: 40, containLabel: true },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      min: rangeStart.value,
      max: rangeEnd.value,
      axisLabel: { formatter: (v: number) => `${v}` },
    },
    yAxis: { type: "value", scale: true },
    dataZoom: [
      { type: "inside", xAxisIndex: 0, filterMode: "none", moveOnMouseMove: false },
      {
        type: "slider",
        xAxisIndex: 0,
        filterMode: "none",
        height: 18,
        bottom: 4,
      },
    ],
    series: [
      {
        type: "line",
        showSymbol: false,
        symbol: "none",
        data: props.data.map((d) => [d.time, d.value]),
        lineStyle: { color: "var(--el-color-primary)", width: 1.5 },
        itemStyle: { color: "var(--el-color-primary)" },
        markArea: { silent: false, data: markAreaData },
      },
    ],
  };
});

/** 取当前 echarts 实例（vue-echarts 挂载在组件实例的 chart prop）。 */
function getChart() {
  return (chartRef.value as any)?.chart;
}

/** 将画布像素换算为 x 轴数据值（时间原始值）。越界/非数值返回 null。 */
function toDataTime(px: number, py: number): number | null {
  const chart = getChart();
  if (!chart) return null;
  const vals = chart.convertFromPixel({ gridIndex: 0 }, [px, py]) as number[] | null;
  if (!vals || !Array.isArray(vals) || !vals.length) return null;
  const t = vals[0];
  if (typeof t !== "number" || !Number.isFinite(t)) return null;
  return t;
}

/** 拖选状态：起点像素与是否正在拖选。 */
let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
/** 判定「点击」与「拖选」的像素距离阈值：按下/释放点距离小于该值视为点击，否则视为拖选。 */
const CLICK_DISTANCE = 5;

function onMouseDown(params: any) {
  // 点在区间高亮上：记录起点像素供 click 判别，不启动拖选（避免与区间选中/编辑冲突）。
  if (params?.componentType === "markArea") {
    dragging = false;
    const evt = params?.event;
    if (evt) {
      dragStartX = evt.offsetX;
      dragStartY = evt.offsetY;
    }
    return;
  }
  const evt = params?.event;
  if (!evt) return;
  dragging = true;
  dragStartX = evt.offsetX;
  dragStartY = evt.offsetY;
}

function onMouseMove(params: any) {
  if (!dragging) return;
  const evt = params?.event;
  if (!evt) return;
  const startT = toDataTime(dragStartX, dragStartY);
  const endT = toDataTime(evt.offsetX, evt.offsetY);
  if (startT == null || endT == null) return;
  previewRange.value = clampTimeRange(startT, endT, rangeStart.value, rangeEnd.value);
}

function onMouseUp(params: any) {
  if (!dragging) return;
  dragging = false;
  const evt = params?.event;
  const endT = evt ? toDataTime(evt.offsetX, evt.offsetY) : null;
  const startT = toDataTime(dragStartX, dragStartY);
  previewRange.value = null;
  if (startT == null || endT == null) return;
  const range = clampTimeRange(startT, endT, rangeStart.value, rangeEnd.value);
  // 仅生成长度 > 0 的区间，避免点击产生零宽事件。
  if (range.end - range.start > 0) {
    emit("createRegion", { id: crypto.randomUUID(), start: range.start, end: range.end });
  }
}

function onChartClick(params: any) {
  if (params?.componentType !== "markArea") return;
  // 用按下/释放像素距离阈值区分「点击」与「拖选」：拖选跨越一定距离视为生成区间，不触发选中。
  const evt = params?.event;
  if (evt && Math.hypot(evt.offsetX - dragStartX, evt.offsetY - dragStartY) > CLICK_DISTANCE) {
    return;
  }
  const id = (params.data as any)?.name as string | undefined;
  const seg = props.segments.find((s) => s.id === id);
  if (seg) emit("regionClick", { id: seg.id, start: seg.start, end: seg.end });
}

/** 卸载时清空拖选状态（避免跨实例残留）。 */
function cleanup() {
  dragging = false;
  previewRange.value = null;
}

watch(
  () => props.data,
  () => {
    // 数据变化时清空拖选中的临时区间，避免残留预览。
    if (!dragging) previewRange.value = null;
  }
);

onMounted(cleanup);
onUnmounted(cleanup);
</script>

<style scoped>
.time-series-canvas {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}

.time-series-canvas__chart {
  width: 100%;
  height: 100%;
  min-height: 240px;
}

.time-series-canvas__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
