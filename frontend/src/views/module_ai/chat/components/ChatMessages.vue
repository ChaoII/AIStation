<template>
  <div ref="messagesContainer" class="chat-messages">
    <WelcomeScreen v-if="messages.length === 0" @prompt-click="handlePromptClick" />
    <div v-else class="messages-list">
      <MessageItem
        v-for="(message, i) in messages"
        :key="message.id"
        :message="message"
        :streaming="isStreaming && i === messages.length - 1"
        @resend="(text: string) => emit('resend', text)"
      />
    </div>
    <div v-if="error" class="error-banner">
      <el-alert :title="error" type="error" :closable="true" show-icon @close="handleErrorClose" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from "vue";
import type { UIMessage } from "ai";
import WelcomeScreen from "./WelcomeScreen.vue";
import MessageItem from "./MessageItem.vue";

interface Props {
  messages: UIMessage[];
  error: string;
  /** 是否有消息正在流式生成（用于控制光标/「思考中」显示）。 */
  isStreaming?: boolean;
}

interface Emits {
  (e: "prompt-click", prompt: string): void;
  (e: "error-close"): void;
  (e: "resend", text: string): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const messagesContainer = ref<HTMLElement>();

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
};

watch(
  () => props.messages,
  () => {
    scrollToBottom();
  },
  { deep: true }
);

const handlePromptClick = (prompt: string) => {
  emit("prompt-click", prompt);
};

const handleErrorClose = () => {
  emit("error-close");
};

defineExpose({
  scrollToBottom,
});
</script>

<style lang="scss" scoped>
.chat-messages {
  height: 100%;
  overflow-y: auto;
  /* 与 index chat-main 同底，避免 disabled 灰 + page 色打架 */
  background: transparent;

  .messages-list {
    max-width: 800px;
    padding: 24px;
    margin: 0 auto;
  }

  .error-banner {
    position: fixed;
    bottom: 140px;
    left: 50%;
    z-index: 1000;
    padding: 0 24px;
    transform: translateX(-50%);
  }
}
</style>
