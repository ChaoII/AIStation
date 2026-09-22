<template>
  <aside class="audio-event-panel">
    <div class="aep-head">
      <span>事件片段（{{ segments.length }}）</span>
      <el-button link type="primary" size="small" @click="$emit('new')">+ 新建</el-button>
    </div>
    <div class="aep-body">
      <div
        v-for="s in segments"
        :key="s.id"
        class="aep-item"
        :class="{ active: s.id === selectedId }"
        @click="$emit('select', s.id)"
      >
        <span class="dot-color" :style="{ background: colorOf(s) }" />
        <span class="aep-range">{{ formatTime(s.start) }} - {{ formatTime(s.end) }}</span>
        <span class="aep-type">{{ typeName(s) }}</span>
        <span class="aep-actions">
          <el-button text size="small" class="aep-btn" @click.stop="$emit('edit', s.id)">
            <el-icon :size="12"><Edit /></el-icon>
          </el-button>
          <el-button text size="small" class="aep-btn aep-del" @click.stop="$emit('delete', s.id)">
            <el-icon :size="12"><Delete /></el-icon>
          </el-button>
        </span>
      </div>
      <div v-if="segments.length === 0" class="empty-hint">在波形上拖选区间生成事件</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Edit, Delete } from "@element-plus/icons-vue";
import type { AudioSegment } from "@/api/module_annotation/audio";

const props = defineProps<{
  segments: AudioSegment[];
  classes: any[];
  selectedId: string;
}>();

defineEmits<{
  (e: "select", id: string): void;
  (e: "new"): void;
  (e: "edit", id: string): void;
  (e: "delete", id: string): void;
}>();

function typeName(s: AudioSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.name ?? `#${s.label_id}`;
}

function colorOf(s: AudioSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.color || "var(--el-color-primary)";
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const sec = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
}
</script>

<style scoped>
.audio-event-panel {
  width: 260px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.aep-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.aep-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 6px;
  scrollbar-width: thin;
}
.aep-body::-webkit-scrollbar {
  width: 6px;
}
.aep-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 2px;
}
.aep-item:hover {
  background: var(--el-color-primary-light-9);
}
.aep-item.active {
  background: var(--el-color-primary-light-8);
}
.aep-item.active .aep-range {
  color: var(--el-color-primary);
  font-weight: 500;
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.aep-range {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.aep-type {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-color-info);
  font-size: 11px;
}
.aep-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.aep-btn {
  padding: 0 2px;
}
.aep-del {
  color: var(--el-color-danger);
}
.empty-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  padding: 4px;
}
</style>
