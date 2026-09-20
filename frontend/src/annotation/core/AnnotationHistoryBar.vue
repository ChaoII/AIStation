<template>
  <footer class="ann-footer">
    <span v-if="hint" class="hint">{{ hint }}</span>
    <span v-if="unsaved" class="unsaved-dot" title="未保存" />
    <span class="mono">X:{{ cursorX }} Y:{{ cursorY }}</span>
    <span class="mono">Z:{{ Math.round(zoom * 100) }}% | cw:{{ cw }}</span>
    <div class="sep" />
    <el-button size="small" :disabled="!canPrev" circle @click="$emit('prev')">
      <el-icon><ArrowLeft /></el-icon>
    </el-button>
    <span class="nav-text">{{ currentIndex + 1 }}/{{ total }}</span>
    <el-button size="small" :disabled="!canNext" circle @click="$emit('next')">
      <el-icon><ArrowRight /></el-icon>
    </el-button>
    <div class="sep" />
    <el-button
      size="small"
      type="primary"
      :disabled="!hasCurrentImage || locked"
      @click="$emit('save')"
    >
      保存
    </el-button>
    <div class="sep" />
    <el-button size="small" :disabled="!hasCurrentImage" @click="$emit('history')">历史</el-button>
    <div class="sep" />
    <el-button size="small" circle @click="$emit('help')">
      <el-icon><QuestionFilled /></el-icon>
    </el-button>
  </footer>
</template>

<script setup lang="ts">
import { ArrowLeft, ArrowRight, QuestionFilled } from "@element-plus/icons-vue";

defineProps<{
  hasCurrentImage: boolean;
  currentIndex: number;
  total: number;
  unsaved: boolean;
  cursorX: number;
  cursorY: number;
  zoom: number;
  cw: number;
  hint: string;
  canPrev: boolean;
  canNext: boolean;
  locked?: boolean;
}>();
defineEmits<{
  (e: "save"): void;
  (e: "prev"): void;
  (e: "next"): void;
  (e: "history"): void;
  (e: "help"): void;
}>();
</script>

<style scoped>
.ann-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-top: 1px solid var(--el-border-color-light);
  font-size: 12px;
}
.hint {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mono {
  color: #909399;
  font-family: monospace;
  white-space: nowrap;
}
.collab-online {
  color: var(--el-color-success);
  font-size: 12px;
}
.nav-text {
  color: #909399;
  font-size: 13px;
}
.unsaved-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-warning);
  flex-shrink: 0;
}
.sep {
  width: 1px;
  height: 16px;
  background: var(--el-border-color-lighter);
  flex-shrink: 0;
}
</style>
