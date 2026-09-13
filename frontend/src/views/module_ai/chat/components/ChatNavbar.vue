<template>
  <div class="chat-navbar">
    <div class="navbar-left">
      <button class="collapse-btn" @click="toggleSidebar">
        <div v-if="!props.isSidebarCollapsed" class="i-svg:layout_leftbar_close_line w-6 h-6" />
        <div v-else class="i-svg:layout_leftbar_open_line w-6 h-6" />
      </button>
      <el-tag v-if="props.appName" class="app-tag" effect="light" closable @close="handleCloseApp">
        应用：{{ props.appName }}
      </el-tag>
    </div>
    <div class="navbar-right">
      <el-button v-if="hasMessages" text :icon="Delete" @click="handleClearChat">
        清空对话
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Delete } from "@element-plus/icons-vue";

interface Props {
  messageCount: number;
  isSidebarCollapsed?: boolean;
  appName?: string;
}

interface Emits {
  (e: "clear-chat"): void;
  (e: "close-app"): void;
  (e: "toggle-sidebar"): void;
}

const props = withDefaults(defineProps<Props>(), {
  isSidebarCollapsed: false,
  appName: "",
});
const emit = defineEmits<Emits>();

const hasMessages = computed(() => props.messageCount > 0);

const handleClearChat = () => {
  emit("clear-chat");
};

const handleCloseApp = () => {
  emit("close-app");
};

const toggleSidebar = () => {
  emit("toggle-sidebar");
};
</script>

<style lang="scss" scoped>
.chat-navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px;

  .navbar-left {
    display: flex;
    gap: 12px;
    align-items: center;

    .collapse-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      padding: 0;
      color: var(--el-text-color-regular);
      cursor: pointer;
      background: transparent;
      border: none;
      border-radius: 4px;
      transition:
        background-color 0.2s,
        color 0.2s;

      &:hover {
        color: var(--el-color-primary);
        background: var(--el-color-primary-light-9);
      }

      &:focus-visible {
        outline: 2px solid var(--el-color-primary);
        outline-offset: 2px;
      }

      /* UnoCSS 图标 SVG 多随 currentColor */
      & > div {
        color: inherit;
      }

      .collapse-icon {
        width: 20px;
        height: 20px;
        color: inherit;
      }
    }

    .app-tag {
      max-width: 320px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .navbar-right {
    display: flex;
    flex-wrap: nowrap;
    gap: 12px;
    align-items: center;

    /* EP 相邻按钮自带 margin-left，叠在 flex gap 上会导致间距忽大忽小 */
    :deep(.el-button) {
      margin: 0;
    }
  }
}
</style>
