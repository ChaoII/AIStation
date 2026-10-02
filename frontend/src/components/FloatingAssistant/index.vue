<!-- 全局 AI 悬浮助手：自然语言提问 / 导航 / 智能体入口 -->
<template>
  <div class="ai-floating-assistant">
    <el-dialog
      v-model="visible"
      title="AI 助手"
      append-to-body
      width="420px"
      :modal="false"
      class="ai-float-dialog"
    >
      <div v-if="messages.length === 0 && !loading" class="fa-welcome">
        用一句话提问，例如「帮我打开训练任务页」「今天有多少标注」。
      </div>
      <div ref="scrollRef" class="fa-messages">
        <div v-for="(m, i) in messages" :key="i" :class="['fa-msg', m.role]">
          <div class="fa-bubble">{{ m.content }}</div>
          <div v-if="m.action && m.action.path" class="fa-action">
            <el-button size="small" type="primary" @click="goAction(m.action)">
              前往：{{ m.action.label || m.action.path }}
            </el-button>
          </div>
          <div v-if="m.sources && m.sources.length" class="fa-sources">
            <div v-for="(s, j) in m.sources" :key="j" class="fa-source">
              <el-icon><Document /></el-icon>
              {{ s.title }}
              <el-tag v-if="s.score != null" size="small" type="info">
                {{ Number(s.score).toFixed(2) }}
              </el-tag>
            </div>
          </div>
        </div>
        <div v-if="loading" class="fa-msg assistant">
          <div class="fa-bubble fa-loading">思考中…</div>
        </div>
      </div>
      <div class="fa-input">
        <el-input
          v-model="input"
          :disabled="loading"
          placeholder="用一句话提问…"
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="loading" @click="send">发送</el-button>
      </div>
    </el-dialog>

    <el-tooltip content="AI 助手" placement="left">
      <el-button class="fa-fab" type="primary" circle @click="open">
        <el-icon><ChatDotRound /></el-icon>
      </el-button>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from "vue";
import { useRouter } from "vue-router";
import { ChatDotRound, Document } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { assistantChat, type AssistantResult } from "@/api/module_ai/assistant";

interface FloatMsg {
  role: "user" | "assistant";
  content: string;
  action?: AssistantResult["action"];
  sources?: AssistantResult["sources"];
}

const router = useRouter();
const visible = ref(false);
const loading = ref(false);
const input = ref("");
const messages = ref<FloatMsg[]>([]);
const scrollRef = ref<HTMLElement>();

function open() {
  visible.value = true;
  nextTick(scrollToBottom);
}

function scrollToBottom() {
  if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text || loading.value) return;
  messages.value.push({ role: "user", content: text });
  input.value = "";
  loading.value = true;
  scrollToBottom();
  try {
    const res = await assistantChat(text);
    const result: AssistantResult = res.data?.data;
    if (result?.reply) {
      messages.value.push({
        role: "assistant",
        content: result.reply,
        action: result.action || undefined,
        sources: result.sources?.length ? result.sources : undefined,
      });
    }
  } catch {
    ElMessage.error("AI 助手异常，请稍后再试");
  } finally {
    loading.value = false;
    scrollToBottom();
  }
}

function goAction(action: NonNullable<AssistantResult["action"]>) {
  if (action.path) {
    router.push(action.path);
    visible.value = false;
    ElMessage.success(`已跳转：${action.label || action.path}`);
  } else if (action.api) {
    ElMessage.warning("该操作为提议类操作，请到对应页面确认执行");
  }
}
</script>

<style lang="scss" scoped>
.ai-floating-assistant {
  .fa-fab {
    position: fixed;
    right: 24px;
    bottom: 40px;
    z-index: 3000;
    width: 48px;
    height: 48px;
    font-size: 22px;
    box-shadow: 0 4px 12px var(--el-box-shadow-light);
  }

  .fa-welcome {
    padding: 12px;
    font-size: 13px;
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
    border-radius: 6px;
    margin-bottom: 8px;
  }

  .fa-messages {
    max-height: 320px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 4px 2px;
  }

  .fa-msg {
    display: flex;
    flex-direction: column;

    &.user {
      align-items: flex-end;

      .fa-bubble {
        background: var(--el-color-primary);
        color: var(--el-color-white);
      }
    }

    &.assistant {
      align-items: flex-start;

      .fa-bubble {
        background: var(--el-fill-color-light);
        color: var(--el-text-color-primary);
      }
    }

    .fa-bubble {
      max-width: 90%;
      padding: 8px 12px;
      font-size: 13px;
      line-height: 1.6;
      border-radius: 8px;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .fa-loading {
      color: var(--el-text-color-secondary);
    }

    .fa-action {
      margin-top: 6px;
    }

    .fa-sources {
      margin-top: 6px;
      display: flex;
      flex-direction: column;
      gap: 4px;

      .fa-source {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
  }

  .fa-input {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }
}
</style>
