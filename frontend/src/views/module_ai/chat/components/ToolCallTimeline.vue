<template>
  <div class="tool-timeline" :class="{ 'is-grouped': grouped }">
    <!-- 工具一多（≥3），一排同样宽的卡片会把消息撑得很碎；
         收成一个可展开的分组，头部只留「工具调用 3 · 完成 2 · 失败 1」。 -->
    <div v-if="grouped" class="tool-group__head" @click="groupOpen = !groupOpen">
      <el-icon class="tool-group__icon"><Tools /></el-icon>
      <span class="tool-group__title">{{ t("ai_chat.toolTimeline_title") }}</span>
      <el-tag size="small" effect="plain">{{ parts.length }}</el-tag>
      <span class="tool-group__sum">{{ summary }}</span>
      <el-icon class="tool-group__caret">
        <ArrowUp v-if="groupOpen" />
        <ArrowDown v-else />
      </el-icon>
    </div>

    <div v-show="!grouped || groupOpen" class="tool-group__body">
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
          <div class="tool-io__label">{{ t("ai_chat.toolTimeline_input") }}</div>
          <JsonPretty :data="normalize(part.input)" />
        </div>
        <div v-if="part.output != null" class="tool-io">
          <div class="tool-io__label">{{ t("ai_chat.toolTimeline_output") }}</div>
          <JsonPretty :data="normalize(part.output)" />
        </div>
        <div v-if="part.errorText" class="tool-io tool-io--error">
          <el-icon><CircleClose /></el-icon>
          <span>{{ part.errorText }}</span>
        </div>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { type Component } from "vue";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { Loading, CircleCheck, CircleClose, ArrowUp, ArrowDown, Tools } from "@element-plus/icons-vue";
import JsonPretty from "vue-json-pretty";
import "vue-json-pretty/lib/styles.css";
import { toolNameOf, type AiUIPart } from "@/composables/ai/uiMessage";

interface Props {
  /** 消息里的 tool parts（按出现顺序）。 */
  parts: AiUIPart[];
}

const props = defineProps<Props>();

/** ≥3 个工具时折叠成一组 */
const grouped = computed(() => (props.parts || []).length >= 3);
const groupOpen = ref(false);

const summary = computed(() => {
  const list = props.parts || [];
  const done = list.filter((p: AiUIPart) => p.state === "output-available").length;
  const failed = list.filter((p: AiUIPart) => p.state === "output-error").length;
  return [done ? `完成 ${done}` : "", failed ? `失败 ${failed}` : ""].filter(Boolean).join(" · ");
});

const { t } = useI18n();

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
      return { label: t("ai_chat.toolTimeline_done"), tag: "success", icon: CircleCheck };
    case "output-error":
      return { label: t("ai_chat.toolTimeline_failed"), tag: "danger", icon: CircleClose };
    default:
      return { label: t("ai_chat.toolTimeline_running"), tag: "primary", icon: Loading };
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
.tool-group__head {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.tool-group__icon {
  color: var(--el-text-color-secondary);
}

.tool-group__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tool-group__sum {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tool-group__caret {
  margin-left: auto;
  color: var(--el-text-color-secondary);
}

.tool-group__body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

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
