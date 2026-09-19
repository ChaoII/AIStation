<template>
  <div class="ann-footer">
    <el-button size="small" :disabled="!hasCurrentImage || locked" @click="$emit('save')">保存</el-button>
    <span class="nav-text">{{ currentIndex + 1 }}/{{ total }}</span>
    <el-button size="small" @click="$emit('prev')">上一张</el-button>
    <el-button size="small" @click="$emit('next')">下一张</el-button>
    <el-button size="small" :disabled="!hasCurrentImage" @click="$emit('history')">历史</el-button>
    <el-button size="small" circle @click="$emit('help')">?</el-button>
    <span class="footer-spacer" />
    <span v-if="unsaved" class="unsaved-dot" title="有未保存的修改" />
    <span class="footer-meta">X:{{ cursorX }} Y:{{ cursorY }} | Z:{{ Math.round(zoom * 100) }}%</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  hasCurrentImage: boolean;
  currentIndex: number;
  total: number;
  unsaved: boolean;
  cursorX: number;
  cursorY: number;
  zoom: number;
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
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-light);
}
.footer-spacer {
  flex: 1;
}
.unsaved-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-warning);
}
.footer-meta {
  color: #c0c4cc;
  font-size: 12px;
}
.nav-text {
  color: #909399;
  font-size: 13px;
}
</style>
