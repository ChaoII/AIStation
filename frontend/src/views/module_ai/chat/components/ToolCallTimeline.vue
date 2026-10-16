<template>
  <div class="tool-timeline">
    <div v-for="(part, i) in parts" :key="part.toolCallId || i" class="tool-item">
      <div class="tool-item__header" @click="toggle(i)">
        <el-icon class="tool-item__icon" :class="`is-${meta(part).tag}`">
          <component :is="meta(part).icon" />
        </el-icon>
        <span class="tool-item__name">{{ toolNameOf(part) }}</span>
        <el-tag size="small" :type="meta(part).tag" effect="light">
          {{ meta(part).label }}
        </el-tag>
        <el-icon class="tool-item__caret">
          <ArrowUp v-if="isOpen(i)" />
          <ArrowDown v-else />
        </el-icon>
      </div>
      <div v-show="isOpen(i)" class="tool-item__body">
        <div v-if="part.input != null" class="tool-io">
          <div class="tool-io__label">输入</div>
          <JsonPretty :data="normalize(part.input)" />
        </div>
        <div v-if="part.output != null" class="tool-io">
          <div class="tool-io__label">输出</div>
          <JsonPretty :data="normalize(part.output)" />
        </div>
        <div v-if="part.errorText" class="tool-io tool-io--error">
          <el-icon><CircleClose /></el-icon>
          <span>{{ part.errorText }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, type Component } from "vue";
import { Loading, CircleCheck, CircleClose, ArrowUp, ArrowDown } from "@element-plus/icons-vue";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import { toolNameOf, type AiUIPart } from "@/composables/ai/uiMessage";

interface Props {
  /** 消息里的 tool parts（按出现顺序）。 */
  parts: AiUIPart[];
}

defineProps<Props>();

const open = ref<Record<number, boolean>>({});

const isOpen = (i: number) => !!open.value[i];
const toggle = (i: number) => {
  open.value[i] = !open.value[i];
};

interface StateMeta {
  label: string;
  tag: "primary" | "success" | "danger";
  icon: Component;
}

function meta(part: AiUIPart): StateMeta {
  switch (part.state) {
    case "output-available":
      return { label: "完成", tag: "success", icon: CircleCheck };
    case "output-error":
      return { label: "失败", tag: "danger", icon: CircleClose };
    default:
      return { label: "进行中", tag: "primary", icon: Loading };
  }
}

/** 把可能为 JSON 字符串的输入/输出转成对象（vue-json-pretty 展示用）。 */

function normalize(value: unknown): any {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}
</script>

<style lang="scss" scoped>
.tool-timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 0;

  .tool-item {
    overflow: hidden;
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 6px;

    .tool-item__header {
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 6px 10px;
      cursor: pointer;
      user-select: none;

      .tool-item__icon {
        font-size: var(--el-font-size-medium);

        &.is-primary {
          color: var(--el-color-primary);
        }
        &.is-success {
          color: var(--el-color-success);
        }
        &.is-danger {
          color: var(--el-color-danger);
        }
      }

      .tool-item__name {
        flex: 1;
        font-size: var(--el-font-size-small);
        font-weight: 600;
        color: var(--el-text-color-primary);
      }

      .tool-item__caret {
        font-size: var(--el-font-size-medium);
        color: var(--el-text-color-secondary);
      }
    }

    .tool-item__body {
      padding: 0 10px 10px;

      .tool-io {
        margin-top: 8px;

        .tool-io__label {
          margin-bottom: 4px;
          font-size: var(--el-font-size-small);
          color: var(--el-text-color-secondary);
        }

        &--error {
          display: flex;
          gap: 6px;
          align-items: center;
          padding: 8px;
          font-size: var(--el-font-size-small);
          color: var(--el-color-danger);
          background: var(--el-color-danger-light-9);
          border-radius: 4px;
        }
      }
    }
  }
}
</style>
