<template>
  <aside class="ann-leftbar">
    <div class="tool-list">
      <div
        v-for="t in tools"
        :key="t.name"
        class="tool-btn"
        :class="{ active: currentTool === t.name }"
        :title="titleOf(t)"
        @click="$emit('select', t.name)"
      >
        <el-icon :size="20"><component :is="iconOf(t)" /></el-icon>
        <span class="tool-label">{{ t.label }}</span>
      </div>
      <div class="tool-sep" />
      <div class="tool-btn" title="撤销 (Ctrl+Z)" @click="$emit('undo')">
        <el-icon :size="20"><RefreshLeft /></el-icon>
        <span class="tool-label">撤销</span>
      </div>
      <div class="tool-btn" title="重做 (Ctrl+Y)" @click="$emit('redo')">
        <el-icon :size="20"><RefreshRight /></el-icon>
        <span class="tool-label">重做</span>
      </div>
      <div class="tool-btn danger" title="删除选中标注 (Delete)" @click="$emit('delete')">
        <el-icon :size="20"><Delete /></el-icon>
        <span class="tool-label">删除</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { RefreshLeft, RefreshRight, Delete, Box, Refresh } from "@element-plus/icons-vue";

defineProps<{
  tools: { name: string; label: string; icon?: any; title?: string }[];
  currentTool: string;
}>();
defineEmits<{
  (e: "select", name: string): void;
  (e: "undo"): void;
  (e: "redo"): void;
  (e: "delete"): void;
}>();

const TOOL_ICONS: Record<string, any> = { box: Box, rotated_box: Refresh };
function iconOf(t: any) {
  return t.icon || TOOL_ICONS[t.name] || Box;
}
function titleOf(t: any) {
  return t.title || t.label;
}
</script>

<style scoped>
.ann-leftbar {
  width: 56px;
  border-right: 1px solid var(--el-border-color-light);
  padding: 8px 0;
}
.tool-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 48px;
  padding: 6px 0;
  cursor: pointer;
  color: #606266;
}
.tool-btn.active {
  color: var(--el-color-primary);
}
.tool-btn.danger:hover {
  color: var(--el-color-danger);
}
.tool-label {
  font-size: 11px;
}
.tool-sep {
  height: 1px;
  width: 32px;
  background: var(--el-border-color-light);
  margin: 6px 0;
}
</style>
