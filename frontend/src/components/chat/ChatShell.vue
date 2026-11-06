<!--
  ChatShell：聊天页的公共外壳（标题栏 / 内容区 / 输入区）。

  为什么要有它：问数页与「工作台对话」原本各写一套 flex 布局——
  一个输入区在底部但外壳是 el-card，一个自己算高度；改一处另一处不跟着变。
  统一后两边只关心"往里放什么"，高度、滚动、输入区吸底都由这里保证。

  用法：
    <ChatShell>
      <template #header>标题 / 操作</template>
      消息列表（或任意内容）
      <template #footer>输入框</template>
    </ChatShell>
-->
<template>
  <div class="chat-shell">
    <div v-if="$slots.header" class="chat-shell__header">
      <slot name="header" />
    </div>
    <div class="chat-shell__body" :class="{ 'is-scroll': scroll }">
      <slot />
    </div>
    <div v-if="$slots.footer" class="chat-shell__footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * scroll=false：内容自己管滚动（例如 ChatMessages 内部已有滚动容器），
 * 外壳只负责撑满高度，避免出现两层滚动条。
 */
withDefaults(defineProps<{ scroll?: boolean }>(), { scroll: true });
</script>

<style lang="scss">
.chat-shell {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  height: 100%;
}

.chat-shell__header {
  flex: 0 0 auto;
}

.chat-shell__body {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}

.chat-shell__body.is-scroll {
  overflow-y: auto;
}

.chat-shell__footer {
  flex: 0 0 auto;
  min-width: 0;
}
</style>
