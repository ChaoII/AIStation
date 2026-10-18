<template>
  <div class="reasoning-block" :class="{ expanded }">
    <div class="reasoning-header" @click="toggle">
      <el-icon class="reasoning-icon" :class="{ spinning: streaming }">
        <Loading v-if="streaming" />
        <CircleCheck v-else />
      </el-icon>
      <span class="reasoning-title">{{ streaming ? "思考中…" : "思考过程" }}</span>
      <el-icon class="reasoning-caret">
        <ArrowUp v-if="expanded" />
        <ArrowDown v-else />
      </el-icon>
    </div>
    <div class="reasoning-body" :class="{ collapsed: !expanded }">
      <div class="reasoning-text">
        {{ text }}
        <span v-if="streaming" class="cursor">▍</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { Loading, CircleCheck, ArrowUp, ArrowDown } from "@element-plus/icons-vue";

interface Props {
  text: string;
  streaming: boolean;
}

const props = defineProps<Props>();

const expanded = ref(true);

// 流式时自动展开，完成后自动收起为摘要
watch(
  () => props.streaming,
  (streaming) => {
    if (streaming) {
      expanded.value = true;
    } else if (props.text) {
      expanded.value = false;
    }
  },
  { immediate: true }
);

const toggle = () => {
  if (props.streaming) return;
  expanded.value = !expanded.value;
};
</script>

<style lang="scss" scoped>
.reasoning-block {
  margin-bottom: 8px;
  overflow: hidden;
  font-size: var(--el-font-size-small);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;

  .reasoning-header {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 6px 10px;
    cursor: pointer;
    user-select: none;

    .reasoning-icon {
      font-size: var(--el-font-size-medium);
      color: var(--el-color-primary);

      &.spinning {
        animation: reasoning-spin 1.2s linear infinite;
      }
    }

    .reasoning-title {
      flex: 1;
      font-weight: 600;
      color: var(--el-text-color-regular);
    }

    .reasoning-caret {
      font-size: var(--el-font-size-medium);
      color: var(--el-text-color-secondary);
      transition: transform 0.2s ease;
    }
  }

  .reasoning-body {
    max-height: 600px;
    overflow: hidden;
    transition: max-height 0.3s ease;

    &.collapsed {
      position: relative;
      max-height: 60px;

      &::after {
        position: absolute;
        right: 0;
        bottom: 0;
        left: 0;
        height: 40px;
        content: "";
        background: linear-gradient(transparent, var(--el-fill-color-light));
      }
    }

    .reasoning-text {
      padding: 0 10px 10px;
      line-height: 1.6;
      color: var(--el-text-color-secondary);
      white-space: pre-wrap;
      word-break: break-word;

      .cursor {
        color: var(--el-color-primary);
        animation: reasoning-blink 0.8s step-end infinite;
      }
    }
  }
}

@keyframes reasoning-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes reasoning-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
</style>
