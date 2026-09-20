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
import { h, defineComponent } from "vue";
import {
  Rank,
  ZoomIn,
  Crop,
  Refresh,
  Grid,
  CirclePlus,
  Document,
  Collection,
  RefreshLeft,
  RefreshRight,
  Delete,
} from "@element-plus/icons-vue";

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

const CursorIcon = defineComponent({
  name: "CursorIcon",
  render() {
    return h("i", { class: "ri-cursor-fill" });
  },
});

const ICONS: Record<string, any> = {
  select: CursorIcon,
  pan: Rank,
  zoom: ZoomIn,
  box: Crop,
  rotated_box: Refresh,
  polygon: Grid,
  keypoint: CirclePlus,
  ocr: Document,
  classification: Collection,
};

function iconOf(t: any) {
  return ICONS[t.name] || t.icon || Grid;
}
function titleOf(t: any) {
  return t.title || t.label;
}
</script>

<style scoped>
.ann-leftbar {
  width: 52px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 2px;
  gap: 2px;
  flex-shrink: 0;
}
.tool-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: all 0.12s;
  border: 1px solid transparent;
}
.tool-btn :deep(svg path) {
  stroke-width: 2;
}
.tool-btn :deep(.ri-cursor-fill) {
  font-size: 18px;
}
.tool-btn:hover {
  background: #f0f2f5;
}
.tool-btn.active {
  background: #ecf5ff;
  border-color: #409eff;
  color: #409eff;
}
.tool-btn.danger:hover {
  background: #fef0f0;
  color: #f56c6c;
}
.tool-sep {
  width: 28px;
  height: 1px;
  margin: 4px 0;
  background: #e4e7ed;
}
.tool-label {
  font-size: 9px;
  margin-top: 1px;
  line-height: 1;
}
</style>
