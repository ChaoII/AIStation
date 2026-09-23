<template>
  <aside class="time-series-panel">
    <div class="tsp-head">
      <span>事件区间（{{ segments.length }}）</span>
      <el-button link type="primary" size="small" @click="$emit('new')">+ 新建</el-button>
    </div>
    <div class="tsp-col">
      <span class="tsp-col-label">数值列</span>
      <el-select
        size="small"
        :model-value="valueColumn"
        placeholder="选择数值列"
        style="width: 100%"
        @change="$emit('changeColumn', $event)"
      >
        <el-option v-for="c in valueColumns" :key="c" :label="c" :value="c" />
      </el-select>
    </div>
    <div class="tsp-meta">
      <div class="tsp-meta-item">
        <span class="tsp-meta-label">行数</span>
        <span class="tsp-meta-value">{{ rowCount }}</span>
      </div>
      <div class="tsp-meta-item">
        <span class="tsp-meta-label">时间范围</span>
        <span class="tsp-meta-value">{{ formatStart(rangeStart) }} - {{ formatStart(rangeEnd) }}</span>
      </div>
      <div class="tsp-meta-item">
        <span class="tsp-meta-label">时间单位</span>
        <span class="tsp-meta-value">{{ timeUnit || "-" }}</span>
      </div>
    </div>
    <div class="tsp-body">
      <div
        v-for="s in segments"
        :key="s.id"
        class="tsp-item"
        :class="{ active: s.id === selectedId }"
        @click="$emit('select', s.id)"
      >
        <span class="dot-color" :style="{ background: colorOf(s) }" />
        <span class="tsp-range">{{ formatStart(s.start) }} - {{ formatStart(s.end) }}</span>
        <span class="tsp-type">{{ typeName(s) }}</span>
        <span class="tsp-actions">
          <el-button text size="small" class="tsp-btn" @click.stop="$emit('edit', s.id)">
            <el-icon :size="12"><Edit /></el-icon>
          </el-button>
          <el-button text size="small" class="tsp-btn tsp-del" @click.stop="$emit('delete', s.id)">
            <el-icon :size="12"><Delete /></el-icon>
          </el-button>
        </span>
      </div>
      <div v-if="segments.length === 0" class="empty-hint">在折线图上拖选区间生成事件</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Edit, Delete } from "@element-plus/icons-vue";
import { formatSeriesTime } from "./useTimeSeriesEventTool";
import type { TimeSeriesSegment } from "../../../api/module_annotation/timeSeries";

const props = withDefaults(
  defineProps<{
    segments: TimeSeriesSegment[];
    classes: any[];
    selectedId: string;
    valueColumns: string[];
    valueColumn: string;
    timeUnit: string;
    rowCount: number;
    rangeStart: number;
    rangeEnd: number;
  }>(),
  {
    valueColumns: () => [],
    valueColumn: "",
    timeUnit: "",
    rowCount: 0,
    rangeStart: 0,
    rangeEnd: 0,
  }
);

defineEmits<{
  (e: "select", id: string): void;
  (e: "new"): void;
  (e: "edit", id: string): void;
  (e: "delete", id: string): void;
  (e: "changeColumn", valueColumn: string): void;
}>();

function typeName(s: TimeSeriesSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.name ?? `#${s.label_id}`;
}

function colorOf(s: TimeSeriesSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.color || "var(--el-color-primary)";
}

function formatStart(value: number): string {
  return formatSeriesTime(value, props.timeUnit);
}
</script>

<style scoped>
.time-series-panel {
  width: 260px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.tsp-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 8px;
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-base);
  border-bottom: 1px solid var(--el-border-color-light);
}
.tsp-col {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.tsp-col-label {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.tsp-meta {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.tsp-meta-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}
.tsp-meta-label {
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
}
.tsp-meta-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.tsp-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 6px;
  scrollbar-width: thin;
}
.tsp-body::-webkit-scrollbar {
  width: 6px;
}
.tsp-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 2px;
}
.tsp-item:hover {
  background: var(--el-color-primary-light-9);
}
.tsp-item.active {
  background: var(--el-color-primary-light-8);
}
.tsp-item.active .tsp-range {
  color: var(--el-color-primary);
  font-weight: 500;
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.tsp-range {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.tsp-type {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-color-info);
}
.tsp-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.tsp-btn {
  padding: 0 2px;
}
.tsp-del {
  color: var(--el-color-danger);
}
.empty-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  padding: 4px;
}
</style>
