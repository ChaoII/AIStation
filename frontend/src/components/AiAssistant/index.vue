<template>
  <!-- 悬浮按钮 -->
  <div class="ai-assistant">
    <!-- AI 助手图标按钮 -->
    <el-button
      v-if="!dialogVisible && !fabCollapsed"
      class="ai-fab-button"
      type="primary"
      circle
      size="large"
      :style="fabStyle"
      @contextmenu.prevent="fabCollapsed = true"
      @click="handleOpen"
    >
      <div class="i-svg:ai ai-icon" />
    </el-button>

    <!-- 收缩态：贴边小标签，避免遮挡表单控件 -->
    <div
      v-if="!dialogVisible && fabCollapsed"
      class="ai-fab-tab"
      :style="fabStyle"
      @click="fabCollapsed = false"
    >
      AI
    </div>

    <!-- AI 对话框：与「AI 聊天」页共用同一套消息/输入组件与 Agno 事件流 -->
    <el-dialog
      v-model="dialogVisible"
      width="600px"
      :close-on-click-modal="false"
      draggable
      class="ai-assistant-dialog"
    >
      <template #header>
        <div class="dialog-header">
          <div class="i-svg:ai header-icon" />
          <span class="title">AI 智能助手</span>
        </div>
      </template>

      <div class="assistant-chat">
        <ChatMessages
          :messages="displayMessages"
          :error="errorText"
          @prompt-click="handleSend"
          @error-close="errorText = ''"
        />
      </div>
      <div class="assistant-input">
        <ChatInput :sending="isSending" @send="handleSend" @stop="handleStop" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useStorage } from "@vueuse/core";
import { useSettingsStore } from "@/store";
import { useAiChat } from "@/composables/ai/useAiChat";
import {
  textOf,
  reasoningOf,
  toolPartsOf,
  sourcesOf,
  dataPartsOf,
} from "@/composables/ai/uiMessage";
import { createAiSession } from "@/api/module_ai/session";
import { AnnotationAPI } from "@/api/module_annotation";
import ChatMessages from "@/views/module_ai/chat/components/ChatMessages.vue";
import ChatInput from "@/views/module_ai/chat/components/ChatInput.vue";
import type { ChatMessage } from "@/views/module_ai/chat/types";

const router = useRouter();
const settingsStore = useSettingsStore();

// 状态
const dialogVisible = ref(false);
const errorText = ref("");

// Agno 原生事件流助手（默认 /ai/assistant/stream）；会话统一走 /sessions
const chat = useAiChat(() => ({
  body: () => (currentSessionId.value != null ? { session_id: currentSessionId.value } : {}),
}));

const currentSessionId = ref<number | null>(null);

const isSending = computed(
  () => chat.status.value === "submitted" || chat.status.value === "streaming"
);

const fabCollapsed = useStorage<boolean>("vea:ui:ai_assistant_fab_collapsed", false);

const fabRight = ref(30);
const fabBottom = ref(80);
const fabStyle = computed(() => ({
  right: `${fabRight.value}px`,
  bottom: `${fabBottom.value}px`,
}));

const isElementVisible = (el: Element) => {
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") {
    return false;
  }
  return (el as HTMLElement).getClientRects().length > 0;
};

const getActiveRightDrawerWidth = (): number => {
  const drawers = Array.from(document.querySelectorAll(".el-drawer"));
  for (let i = drawers.length - 1; i >= 0; i--) {
    const drawer = drawers[i] as HTMLElement;
    if (!isElementVisible(drawer)) {
      continue;
    }
    const rect = drawer.getBoundingClientRect();
    if (rect.width > 0 && rect.right >= window.innerWidth - 8) {
      return rect.width;
    }
  }
  return 0;
};

const updateFabPosition = () => {
  const safeMargin = 24;
  const drawerWidth = getActiveRightDrawerWidth() || 0;
  const baseRight = drawerWidth + 30;

  const nextRight = baseRight;
  let nextBottom = 80;

  const fabSize = fabCollapsed.value ? 42 : 60;
  const computeFabRect = (rightPx: number, bottomPx: number) => {
    const right = window.innerWidth - rightPx;
    const left = right - fabSize;
    const bottom = window.innerHeight - bottomPx;
    const top = bottom - fabSize;
    return { left, right, top, bottom };
  };

  const intersects = (
    a: { left: number; right: number; top: number; bottom: number },
    b: DOMRect
  ) => {
    return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
  };

  const poppers = Array.from(document.querySelectorAll(".el-popper"));
  for (const popper of poppers) {
    if (!isElementVisible(popper)) {
      continue;
    }
    const rect = (popper as HTMLElement).getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      continue;
    }

    const candidateFabRect = computeFabRect(nextRight, nextBottom);
    if (intersects(candidateFabRect, rect)) {
      const requiredBottom = Math.ceil(window.innerHeight - rect.top + safeMargin);
      nextBottom = Math.max(nextBottom, requiredBottom);
    }
  }

  const maxBottom = window.innerHeight - fabSize - safeMargin;
  nextBottom = Math.min(nextBottom, Math.max(0, maxBottom));

  fabRight.value = nextRight + (drawerWidth > 0 ? safeMargin : 0);
  fabBottom.value = nextBottom;
};

watch(
  fabCollapsed,
  () => {
    updateFabPosition();
  },
  { flush: "post" }
);

watch(
  () => settingsStore.settingsVisible,
  () => {
    nextTick(() => {
      scheduleUpdateFabPositionBurst();
    });
  },
  { flush: "post" }
);

let domObserver: MutationObserver | null = null;
let rafId: number | null = null;

const scheduleUpdateFabPosition = () => {
  if (rafId != null) {
    return;
  }
  rafId = window.requestAnimationFrame(() => {
    rafId = null;
    updateFabPosition();
  });
};

const scheduleUpdateFabPositionBurst = (frames = 18) => {
  let count = 0;
  const tick = () => {
    scheduleUpdateFabPosition();
    count += 1;
    if (count < frames) {
      window.requestAnimationFrame(tick);
    }
  };
  tick();
};

// 把 Agno 事件流消息映射为页面 ChatMessage（正文/思考/工具/来源）
const liveMessages = computed<ChatMessage[]>(() =>
  chat.messages.value.map((m: any) => {
    const text = textOf(m);
    const think = reasoningOf(m);
    const toolNames = toolPartsOf(m)
      .map((p) => p.toolName)
      .filter(Boolean);
    const toolHint = toolNames.map((n) => `\n\n> 🔧 调用工具：${n}`).join("");
    const sources = sourcesOf(m);
    return {
      id: m.id,
      type: m.role === "user" ? "user" : "assistant",
      content: `${text}${toolHint}`,
      think: think || undefined,
      sources: sources.length ? sources : undefined,
      timestamp: Date.now(),
      loading: isSending.value && m.role === "assistant" && !text,
      collapsed: text.length > 200,
    };
  })
);

const displayMessages = computed<ChatMessage[]>(() => liveMessages.value);

// 待确认操作：用户确认后调用既有业务 API
const confirmAssistantAction = async (action: any) => {
  try {
    await ElMessageBox.confirm(`确认${action.label || "执行该操作"}？`, "AI 操作确认", {
      type: "warning",
    });
  } catch {
    return;
  }
  try {
    if (action.api === "createDataset") {
      await AnnotationAPI.createDataset(action.payload);
      ElMessage.success("数据集已创建");
    } else if (action.api === "createAnnotationTask") {
      await AnnotationAPI.createTask(action.payload);
      ElMessage.success("标注任务已创建");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
};

// 读取本轮助手消息的完成帧，执行其携带的动作（导航/确认/报告提示）
const handleAssistantAction = async () => {
  const list = chat.messages.value;
  const last: any = list[list.length - 1];
  if (!last) return;
  const fin: any = dataPartsOf(last, "data-finish")[0] || {};
  const action = fin.action;
  if (fin.report_id) {
    ElMessage.success(`已生成报告 #${fin.report_id}，可在「AI 管理 → AI 报告」查看`);
  }
  if (!action) return;
  if (action.type === "navigate" && action.path) {
    router.push(action.path);
    handleClose();
  } else if (action.type === "confirm") {
    await confirmAssistantAction(action);
  }
};

// 发送消息（会话统一走 /sessions：首条消息时创建会话）
const handleSend = async (message: string) => {
  const text = (message || "").trim();
  if (!text || isSending.value) return;
  errorText.value = "";

  if (currentSessionId.value == null) {
    try {
      const res = await createAiSession({ title: text.slice(0, 20) });
      const created = res.data?.data;
      if (created?.id != null) currentSessionId.value = created.id;
    } catch {
      // 创建会话失败不阻断对话（后端以无会话继续）
    }
  }

  await chat.sendMessage({ text });
  await handleAssistantAction();
};

const handleStop = () => {
  chat.stop();
};

// 打开对话框
const handleOpen = () => {
  dialogVisible.value = true;
};

// 关闭对话框
const handleClose = () => {
  dialogVisible.value = false;
};

// 组件卸载时清理定时器
onMounted(() => {
  updateFabPosition();
  window.addEventListener("resize", updateFabPosition);

  domObserver = new MutationObserver(() => {
    scheduleUpdateFabPosition();
  });
  domObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "style"],
  });
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateFabPosition);
  if (domObserver) {
    domObserver.disconnect();
    domObserver = null;
  }
  if (rafId != null) {
    window.cancelAnimationFrame(rafId);
    rafId = null;
  }
});
</script>

<style scoped lang="scss">
.ai-assistant {
  .ai-fab-button {
    position: fixed;
    z-index: 9999;
    width: 60px;
    height: 60px;
    box-shadow: var(--el-box-shadow);
    transition: all 0.3s ease;

    &:hover {
      box-shadow: var(--el-box-shadow-dark);
      transform: scale(1.1);
    }

    .ai-icon {
      width: 32px;
      height: 32px;
    }
  }

  .ai-fab-tab {
    position: fixed;
    z-index: 9999;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 42px;
    height: 42px;
    font-size: 14px;
    font-weight: 600;
    color: var(--el-color-white);
    cursor: pointer;
    user-select: none;
    background: var(--el-color-primary);
    border-radius: 999px;
    box-shadow: var(--el-box-shadow);
  }
}

.ai-assistant-dialog {
  .dialog-header {
    display: flex;
    gap: 12px;
    align-items: center;

    .header-icon {
      width: 28px;
      height: 28px;
    }

    .title {
      font-size: 18px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }
  }

  /* 与「AI 聊天」页一致的聊天区（共享 ChatMessages/ChatInput 组件） */
  .assistant-chat {
    height: 420px;
    overflow: hidden;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
  }

  .assistant-input {
    margin-top: 8px;
  }
}
</style>
