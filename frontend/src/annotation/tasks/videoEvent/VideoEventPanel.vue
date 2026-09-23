<template>
  <aside class="video-event-panel">
    <div class="vep-head">
      <span>事件片段（{{ segments.length }}）</span>
      <el-button link type="primary" size="small" @click="$emit('new')">+ 新建</el-button>
    </div>
    <div class="vep-body">
      <div
        v-for="s in segments"
        :key="s.id"
        class="vep-item"
        :class="{ active: s.id === selectedId }"
        @click="$emit('select', s.id)"
      >
        <span class="dot-color" :style="{ background: colorOf(s) }" />
        <span class="vep-range">{{ formatTime(s.start) }} - {{ formatTime(s.end) }}</span>
        <span class="vep-type">{{ typeName(s) }}</span>
        <span class="vep-actions">
          <el-button text size="small" class="vep-btn" @click.stop="$emit('edit', s.id)">
            <el-icon :size="12"><Edit /></el-icon>
          </el-button>
          <el-button text size="small" class="vep-btn vep-del" @click.stop="onDelete(s)">
            <el-icon :size="12"><Delete /></el-icon>
          </el-button>
        </span>
      </div>
      <div v-if="segments.length === 0" class="empty-hint">在时间轴上拖选区间生成事件</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Edit, Delete } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import type { VideoSegment } from "@/api/module_annotation/videoEvent";

const props = defineProps<{
  segments: VideoSegment[];
  classes: any[];
  selectedId: string;
}>();

const emit = defineEmits<{
  (e: "select", id: string): void;
  (e: "new"): void;
  (e: "edit", id: string): void;
  (e: "delete", id: string): void;
}>();

function typeName(s: VideoSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.name ?? `#${s.label_id}`;
}

function colorOf(s: VideoSegment): string {
  return props.classes.find((c) => c.id === s.label_id)?.color || "var(--el-color-primary)";
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const sec = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
}

async function onDelete(s: VideoSegment) {
  try {
    await ElMessageBox.confirm(
      `将删除事件片段「${formatTime(s.start)} - ${formatTime(s.end)}」（${typeName(s)}），且不可恢复。`,
      "删除确认",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        confirmButtonClass: "el-button--danger",
      }
    );
  } catch {
    return;
  }
  emit("delete", s.id);
}
</script>

<style scoped>
.video-event-panel {
  width: 260px;
  border-left: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}
.vep-head {
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
.vep-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 6px;
  scrollbar-width: thin;
}
.vep-body::-webkit-scrollbar {
  width: 6px;
}
.vep-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 2px;
}
.vep-item:hover {
  background: var(--el-color-primary-light-9);
}
.vep-item.active {
  background: var(--el-color-primary-light-8);
}
.vep-item.active .vep-range {
  color: var(--el-color-primary);
  font-weight: 500;
}
.dot-color {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.vep-range {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.vep-type {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-color-info);
}
.vep-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.vep-btn {
  padding: 0 2px;
}
.vep-del {
  color: var(--el-color-danger);
}
.empty-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  padding: 4px;
}
</style>
