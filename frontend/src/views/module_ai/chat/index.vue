<template>
  <div class="app-container">
    <el-container class="main-chat">
      <el-aside class="sidebar-container" :class="{ collapsed: isSidebarCollapsed }">
        <Sidebar
          ref="sidebarRef"
          :current-session-id="currentSessionId"
          :is-collapsed="isSidebarCollapsed"
          @select-session="handleSelectSession"
          @new-session="handleNewSession"
        />
      </el-aside>
      <el-container class="chat-container">
        <el-header class="chat-header">
          <ChatNavbar
            :message-count="displayMessages.length"
            :app-name="appName"
            :is-sidebar-collapsed="isSidebarCollapsed"
            @clear-chat="handleClearChat"
            @close-app="handleCloseApp"
            @toggle-sidebar="toggleSidebar"
          />
        </el-header>
        <el-main class="chat-main">
          <ChatMessages
            ref="chatMessagesRef"
            :messages="displayMessages"
            :error="error"
            @prompt-click="handleSendMessage"
            @error-close="error = ''"
          />
        </el-main>
        <el-footer class="chat-footer">
          <ChatInput :sending="isSending" @send="handleSendMessage" />
        </el-footer>
      </el-container>
    </el-container>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Chat",
  inheritAttrs: false,
});

import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ChatNavbar from "./components/ChatNavbar.vue";
import ChatMessages from "./components/ChatMessages.vue";
import ChatInput from "./components/ChatInput.vue";
import Sidebar from "./components/Sidebar.vue";
import AiChatAPI, { ChatSession } from "@/api/module_ai/chat";
import { getAiAppDetail } from "@/api/module_ai/app";
import { useAiChat } from "@/composables/ai/useAiChat";
import { textOf, reasoningOf, toolPartsOf } from "@/composables/ai/uiMessage";
import type { ChatMessage, UploadedFile } from "./types";

const route = useRoute();
const router = useRouter();

// 状态
const messages = ref<ChatMessage[]>([]);
const error = ref("");
const currentSessionId = ref<string | null>(null);
const isSidebarCollapsed = ref(false);

// 运行中的 AI 应用（?app_id=）：非空时流式走 /ai/apps/{id}/run/stream
const appId = ref<number | null>(route.query.app_id ? Number(route.query.app_id) : null);
const appName = ref("");

watch(
  () => route.query.app_id,
  async (v) => {
    appId.value = v ? Number(v) : null;
    appName.value = "";
    if (!appId.value) return;
    try {
      const res = await getAiAppDetail(appId.value);
      appName.value = res.data?.data?.name || "";
    } catch {
      appName.value = "";
    }
  },
  { immediate: true }
);

// 助手/应用流的 session_id 为整数（ai_sessions 主键）；当前会话栏沿用旧 Agno 会话（UUID 字符串），
// 直接透传会触发后端 422，故仅在可解析为整数时才携带（在 body 回调内读取，避免成为 transport 依赖）。
const streamSessionId = (): number | undefined => {
  const raw = currentSessionId.value;
  if (raw === null || raw === "") return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
};

// AI SDK 流式聊天（getter：随所选应用动态切换 path/body，替代旧 Agno WS）
const chat = useAiChat(() => ({
  path: appId.value ? `/ai/apps/${appId.value}/run/stream` : "/ai/assistant/stream",
  body: () => {
    const sessionId = streamSessionId();
    return sessionId === undefined ? {} : { session_id: sessionId };
  },
}));
const isSending = computed(
  () => chat.status.value === "submitted" || chat.status.value === "streaming"
);

// Refs
const chatMessagesRef = ref<{ scrollToBottom: () => void }>();
const sidebarRef = ref<{ loadSessions: () => void }>();

// 把 AI SDK 的 UIMessage 映射为页面 ChatMessage（正文/思考/工具提示）
const liveMessages = computed<ChatMessage[]>(() =>
  chat.messages.value.map((m: any) => {
    const text = textOf(m);
    const think = reasoningOf(m);
    const toolNames = toolPartsOf(m)
      .map((p) => p.toolName)
      .filter(Boolean);
    const toolHint = toolNames.map((n) => `\n\n> 🔧 调用工具：${n}`).join("");
    return {
      id: m.id,
      type: m.role === "user" ? "user" : "assistant",
      content: `${text}${toolHint}`,
      think: think || undefined,
      timestamp: Date.now(),
      loading: isSending.value && m.role === "assistant" && !text,
      collapsed: text.length > 200,
    };
  })
);

// 历史会话消息（只读）+ 当前流式消息
const displayMessages = computed<ChatMessage[]>(() => [...messages.value, ...liveMessages.value]);

// ============ 消息处理 ============
const addMessage = (type: "user" | "assistant", content: string, files?: UploadedFile[]) => {
  messages.value.push({
    id: generateId(),
    type,
    content,
    timestamp: Date.now(),
    collapsed: content.length > 200,
    files,
  });
};

const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
};

// ============ 发送消息 ============
const handleSendMessage = async (message: string, files?: UploadedFile[]) => {
  // 重置上一轮错误状态，避免历史失败提示残留
  error.value = "";

  const hasFiles = !!files && files.length > 0;
  const text = (message || "").trim();

  // 后端仅消费文本，附件暂不支持：显式提示，避免静默丢弃
  if (hasFiles) {
    ElMessage.warning("当前暂不支持发送附件，仅处理文本内容");
    // 仅附件、无文本时不发送空消息
    if (!text) return;
  }

  if ((!message && !hasFiles) || isSending.value) return;

  // 创建新会话（如果没有）
  if (!currentSessionId.value) {
    const success = await createNewSession(message);
    if (!success) return;
  }

  try {
    // 走 AI SDK UI Message Stream（真流式：思考/回复/工具），不依赖 Agno WS
    await chat.sendMessage({ text: message });
  } catch (e: any) {
    error.value = e?.message || String(e);
  }
};

const createNewSession = async (firstMessage: string): Promise<boolean> => {
  try {
    const title = firstMessage.slice(0, 20) + (firstMessage.length > 20 ? "..." : "");
    const res = await AiChatAPI.createSession({ title });

    if (res.data?.code === 0 || res.data?.success) {
      currentSessionId.value = res.data.data?.id ?? null;
      sidebarRef.value?.loadSessions();
      return true;
    }
    throw new Error("创建会话失败");
  } catch {
    return false;
  }
};

// ============ 会话操作 ============
const handleSelectSession = async (session: ChatSession) => {
  currentSessionId.value = session.id;
  messages.value = [];
  chat.messages.value = [];

  try {
    const response = await AiChatAPI.getSessionDetail(session.id);
    if (response.data?.code !== 0) {
      return;
    }

    const sessionData = response.data.data || {};
    const runs = sessionData.runs || [];

    runs.forEach((run: any) => {
      const runMessages = run.messages || [];
      runMessages.forEach((msg: any) => {
        if (msg.role === "user" || msg.role === "assistant") {
          addMessage(msg.role, msg.content);
        }
      });
    });

    ElMessage.success(`已切换到会话：${session.title}`);
  } catch {
    ElMessage.error("获取会话详情失败");
  }
};

const handleNewSession = () => {
  currentSessionId.value = null;
  messages.value = [];
  chat.messages.value = [];
  ElMessage.success("已开启新对话");
};

const handleClearChat = async () => {
  try {
    await ElMessageBox.confirm("确定要清空当前对话吗？此操作不可恢复。", "确认清空", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    messages.value = [];
    chat.messages.value = [];
    ElMessage.success("对话已清空");
  } catch {
    ElMessage.info("已取消清空对话");
  }
};

const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
};

// 关闭应用标签：回到通用助手（appId 由 route 监听同步清空），不清空会话
const handleCloseApp = () => {
  router.replace({ path: "/ai/chat" });
};
</script>

<style lang="scss" scoped>
.main-chat {
  /* L2 内容面：与 AppMain 的 L0 画布（留白/间隙）区分开，避免与 gap 同色 */
  --chat-area-bg: var(--el-bg-color-overlay);

  height: 100%;
  overflow: hidden;
  background: var(--chat-area-bg);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-light);

  /* 与右侧同一表面色；与内容区的分界交给 Sidebar 的竖线即可 */
  .sidebar-container {
    width: 200px;
    background: transparent;
    transition: width 0.3s ease;

    &.collapsed {
      width: 64px;
    }
  }

  .chat-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--chat-area-bg);
  }

  .chat-header {
    height: auto;
    padding: 0;
    background: var(--chat-area-bg);
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .chat-main {
    flex: 1;
    overflow: hidden;
    background: var(--chat-area-bg);
  }

  .chat-footer {
    height: auto;
    min-height: 80px;
    padding: 0;
    background: var(--chat-area-bg);
    border-top: 1px solid var(--el-border-color-lighter);
  }
}
</style>
