<!--
  ChatMessage：聊天消息的统一外壳（头像 / 发送者 / 正文 / 过程 / 操作）。

  为什么要它：问数页和工作台对话各写一套消息 DOM，思考块和工具时间线一个用
  公共组件、一个自己画。现在两边都用 ChatMessage，内容通过插槽注入：

    <ChatMessage role="user">问题</ChatMessage>

    <ChatMessage role="assistant" name="AI">
      <template #reasoning><ReasoningBlock ... /></template>
      <template #tools><ToolCallTimeline :parts="..." /></template>
      正文（表格 / Markdown / SQL）
      <template #footer>反馈按钮</template>
    </ChatMessage>

  user 渲染成右对齐气泡；assistant 渲染成"名字 + 过程 + 正文 + 操作"块。
-->
<template>
  <div class="chat-msg" :class="[`is-${role}`, { 'is-streaming': streaming }]">
    <div v-if="role === 'user'" class="chat-msg__user">
      <div class="chat-msg__bubble">
        <slot />
      </div>
    </div>

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
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    role: "user" | "assistant";
    /** 助手名称（用户侧不显示） */
    name?: string;
    /** 流式中：头部显示"生成中" */
    streaming?: boolean;
    liveLabel?: string;
  }>(),
  { name: "AI", streaming: false, liveLabel: "生成中…" }
);
</script>

<style lang="scss">
.chat-msg {
  padding: 8px 0 14px;
}

.chat-msg + .chat-msg {
  border-top: 1px dashed var(--el-border-color-lighter);
}

/* 用户：右对齐气泡 */
.chat-msg__user {
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

/* 助手：名称 + 分段内容 */
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
