<template>
  <div :class="['message-item', message.role]">
    <div class="message-avatar">
      <div v-if="message.role === 'user'" class="user-avatar">
        <el-icon><User /></el-icon>
      </div>
      <div v-else class="ai-avatar">
        <el-icon><ChatDotRound /></el-icon>
      </div>
    </div>
    <div class="message-content">
      <div class="message-header">
        <strong class="sender-name">{{ roleLabel }}</strong>
      </div>
      <div class="message-body">
        <!-- Agent 工具调用时间线（通常先于正文，置于顶部） -->
        <ToolCallTimeline v-if="toolParts.length" :parts="toolParts" class="message-tools" />

        <template v-for="(p, idx) in nonToolParts" :key="idx">
          <ReasoningBlock
            v-if="p.type === 'reasoning'"
            :text="p.text || ''"
            :streaming="streaming === true && p.state === 'streaming'"
          />
          <div
            v-else-if="p.type === 'text'"
            class="message-text"
            :class="{ 'is-user': message.role === 'user' }"
          >
            <RichContent :content="p.text || ''" />
            <span v-if="streaming && p.state === 'streaming'" class="cursor-typing" />
          </div>
          <div
            v-else-if="p.type === 'source-url' || p.type === 'source-document'"
            class="message-source"
          >
            <el-icon class="message-source__icon"><Document /></el-icon>
            <span class="message-source__title">{{ sourceTitle(p) }}</span>
            <a
              v-if="p.type === 'source-url' && p.url"
              class="message-source__link"
              :href="p.url"
              target="_blank"
              rel="noopener noreferrer"
            >
              查看
            </a>
          </div>
          <div v-else-if="isDataPart(p)" class="message-data">
            {{ renderData(p.data) }}
          </div>
        </template>

        <div v-if="message.role === 'assistant' && isLoading && streaming" class="typing-indicator">
          <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
      <div v-if="fullText" class="message-actions">
        <el-tooltip content="复制" placement="top">
          <span class="msg-action" @click="handleCopy">
            <el-icon><CopyDocument /></el-icon>
          </span>
        </el-tooltip>
        <el-tooltip content="点赞" placement="top">
          <span class="msg-action" :class="{ 'is-on': liked }" @click="liked = !liked">
            <el-icon><Star /></el-icon>
          </span>
        </el-tooltip>
        <el-tooltip content="反馈" placement="top">
          <span class="msg-action" @click="feedback">
            <el-icon><EditPen /></el-icon>
          </span>
        </el-tooltip>
        <el-tooltip v-if="message.role === 'user'" content="重新发送" placement="top">
          <span class="msg-action" @click="emit('resend', fullText)">
            <el-icon><Refresh /></el-icon>
          </span>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessage } from "element-plus";
import {
  User,
  ChatDotRound,
  CopyDocument,
  Document,
  Refresh,
  Star,
  EditPen,
} from "@element-plus/icons-vue";
import { ref } from "vue";
import type { UIMessage } from "ai";
import RichContent from "./RichContent.vue";
import ReasoningBlock from "./ReasoningBlock.vue";
import ToolCallTimeline from "./ToolCallTimeline.vue";
import { textOf, toolPartsOf, isToolPart } from "@/composables/ai/uiMessage";
import { useUserStoreHook } from "@/store";

interface Props {
  message: UIMessage;
  /** 是否为当前正在流式生成的消息（仅此时显示光标/「思考中」）。 */
  streaming?: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{ resend: [text: string] }>();

const userStore = useUserStoreHook();

const roleLabel = computed(() =>
  props.message.role === "user" ? userStore.basicInfo.name || "用户" : "FA助手"
);

const fullText = computed(() => textOf(props.message));

const toolParts = computed(() => toolPartsOf(props.message));
const nonToolParts = computed(() => (props.message.parts || []).filter((p: any) => !isToolPart(p)));

const isLoading = computed(() => (props.message.parts || []).length === 0);

/** 类型守卫：SDK `DataUIPart`（type 以 `data-` 开头且含 data）。 */
function isDataPart(p: any): p is { type: string; data: unknown } {
  return typeof p?.type === "string" && p.type.startsWith("data-") && p.data != null;
}

const sourceTitle = (p: any) =>
  p.title || (p.type === "source-url" ? p.url || "" : "") || "引用来源";

const renderData = (data: any) => {
  if (data && typeof data === "object") return JSON.stringify(data);
  return String(data ?? "");
};

const handleCopy = async () => {
  try {
    await navigator.clipboard.writeText(fullText.value);
    ElMessage.success("已复制到剪贴板");
  } catch {
    const textArea = document.createElement("textarea");
    textArea.value = fullText.value;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
    ElMessage.success("已复制到剪贴板");
  }
};

/** 点赞（本地切换）。 */
const liked = ref(false);

/** 反馈：目前先复制内容并提示（可后续接后端反馈接口）。 */
function feedback() {
  handleCopy();
  ElMessage.info("已复制内容，请在反馈中补充说明");
}
</script>

<style lang="scss" scoped>
.message-item {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;

  .message-avatar {
    flex-shrink: 0;

    .user-avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      font-size: 14px;
      color: white;
      background: var(--el-color-primary);
      border-radius: 6px;
    }

    .ai-avatar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      font-size: 14px;
      color: white;
      background: var(--el-color-success);
      border-radius: 6px;
    }
  }

  .message-content {
    flex: 1;
    min-width: 0;

    .message-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;

      .sender-name {
        font-size: 14px;
        font-weight: 600;
        color: var(--el-text-color-primary);
      }
    }

    .message-actions {
      display: flex;
      align-items: center;
      gap: 2px;
      margin-top: 6px;
      opacity: 0.55;
      transition: opacity 0.2s;

      &:hover {
        opacity: 1;
      }

      .msg-action {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        border-radius: 6px;
        font-size: 14px;
        color: var(--el-text-color-secondary);
        cursor: pointer;
        transition: all 0.2s;

        &:hover {
          color: var(--el-color-primary);
          background: var(--el-color-primary-light-9);
        }

        &.is-on {
          color: var(--el-color-primary);
          background: var(--el-color-primary-light-9);
        }
      }
    }

    .message-body {
      .message-tools {
        margin-bottom: 8px;
      }

      .message-text {
        font-size: var(--el-font-size-base);
        line-height: 1.6;
        color: var(--el-text-color-primary);
        word-wrap: break-word;

        &.is-user {
          display: inline-block;
          padding: 10px 14px;
          background: var(--el-color-primary-light-9);
          border: 1px solid var(--el-border-color-light);
          border-radius: 12px;
        }
      }

      .cursor-typing {
        color: var(--el-color-primary);
        animation: cursor-blink 0.8s step-end infinite;
      }

      .message-source {
        display: flex;
        gap: 6px;
        align-items: center;
        padding: 6px 10px;
        margin: 6px 0;
        font-size: 12px;
        background: var(--el-fill-color-light);
        border: 1px solid var(--el-border-color-light);
        border-radius: 6px;

        .message-source__icon {
          color: var(--el-color-primary);
        }

        .message-source__title {
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .message-source__link {
          font-size: 12px;
          color: var(--el-color-primary);
          text-decoration: none;

          &:hover {
            text-decoration: underline;
          }
        }
      }

      .message-data {
        padding: 8px 10px;
        margin: 6px 0;
        font-size: var(--el-font-size-small);
        color: var(--el-text-color-secondary);
        white-space: pre-wrap;
        background: var(--el-fill-color-light);
        border-radius: 6px;
      }

      .typing-indicator {
        display: flex;
        align-items: center;
        padding: 8px 0;

        .typing-dots {
          display: flex;
          gap: 4px;

          span {
            width: 8px;
            height: 8px;
            background: var(--el-text-color-secondary);
            border-radius: 50%;
            animation: typing 1.4s infinite ease-in-out;

            &:nth-child(1) {
              animation-delay: 0s;
            }

            &:nth-child(2) {
              animation-delay: 0.2s;
            }

            &:nth-child(3) {
              animation-delay: 0.4s;
            }
          }
        }
      }
    }
  }

  &.user {
    flex-direction: row-reverse;

    .message-content {
      display: flex;
      flex-direction: column;
      align-items: flex-end;

      .message-header {
        .sender-name {
          text-align: right;
        }
      }
    }
  }

  &.assistant {
    .message-content {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }
  }
}

@keyframes typing {
  0%,
  60%,
  100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-4px);
  }
}

@keyframes cursor-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
</style>
