<!--
  ChatMessage：聊天消息的统一外壳（头像 / 发送者 / 正文 / 过程 / 操作）。

  user 渲染成右对齐气泡（头像在气泡右侧），assistant 渲染成
  「头像 + 名字 + 过程 + 正文 + 操作」块。思考/工具用命名插槽注入。
-->
<template>
  <div class="chat-msg" :class="[`is-${role}`, { 'is-streaming': streaming }]">
    <div class="chat-msg__row">
      <div v-if="avatar" class="chat-msg__avatar" :class="`is-${role}`">
        <el-icon>
          <User v-if="role === 'user'" />
          <ChatDotRound v-else />
        </el-icon>
      </div>

      <div class="chat-msg__main">
        <template v-if="role === 'user'">
          <div class="chat-msg__bubble">
            <slot />
          </div>
        </template>

        <template v-else>
          <div class="chat-msg__head">
            <span class="chat-msg__name">{{ name }}</span>
            <slot name="meta" />
            <span v-if="streaming" class="chat-msg__live">{{ liveLabel }}</span>
          </div>
          <slot name="reasoning" />
          <slot name="tools" />
          <div class="chat-msg__body"><slot /></div>
          <slot name="footer" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChatDotRound, User } from "@element-plus/icons-vue";

withDefaults(
  defineProps<{
    role: "user" | "assistant";
    /** 助手名称（用户侧不显示） */
    name?: string;
    /** 是否显示头像（32px 圆角方块：用户=主色，助手=成功色） */
    avatar?: boolean;
    /** 流式中：头部显示"生成中" */
    streaming?: boolean;
    liveLabel?: string;
  }>(),
  { name: "AI", avatar: true, streaming: false, liveLabel: "生成中…" }
);
</script>

<style lang="scss">
.chat-msg {
  padding: 8px 0 14px;
}

.chat-msg + .chat-msg {
  border-top: 1px dashed var(--el-border-color-lighter);
}

.chat-msg__row {
  display: flex;
  gap: 12px;
  min-width: 0;
}

/* 用户：头像在右，气泡靠右 */
.chat-msg.is-user .chat-msg__row {
  flex-direction: row-reverse;
}

.chat-msg__avatar {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 15px;
  color: #fff;
  border-radius: 6px;
}

.chat-msg__avatar.is-user {
  background: var(--el-color-primary);
}

.chat-msg__avatar.is-assistant {
  background: var(--el-color-success);
}

.chat-msg__main {
  min-width: 0;
  flex: 1 1 auto;
}

.chat-msg.is-user .chat-msg__main {
  display: flex;
  justify-content: flex-end;
}

.chat-msg__bubble {
  max-width: 72%;
  padding: 9px 14px;
  font-weight: 500;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  overflow-wrap: anywhere;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: var(--el-border-radius-base);
  border-bottom-right-radius: 2px;
}

.chat-msg__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.chat-msg__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.chat-msg__live {
  font-size: 12px;
  color: var(--el-color-primary);
}

.chat-msg__body {
  min-width: 0;
}
</style>
