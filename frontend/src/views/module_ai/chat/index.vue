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
            :connection-status="connectionStatus"
            :is-connected="isConnected"
            :message-count="messages.length"
            :is-sidebar-collapsed="isSidebarCollapsed"
            @clear-chat="handleClearChat"
            @toggle-connection="toggleConnection"
            @toggle-sidebar="toggleSidebar"
          />
        </el-header>
        <el-main class="chat-main">
          <ChatMessages
            ref="chatMessagesRef"
            :messages="messages"
            :error="error"
            @prompt-click="handleSendMessage"
            @error-close="error = ''"
          />
        </el-main>
        <el-footer class="chat-footer">
          <ChatInput
            :disabled="!isConnected"
            :sending="sending"
            :is-connected="isConnected"
            @send="handleSendMessage"
          />
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

import { ref, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ChatNavbar from "./components/ChatNavbar.vue";
import ChatMessages from "./components/ChatMessages.vue";
import ChatInput from "./components/ChatInput.vue";
import Sidebar from "./components/Sidebar.vue";
import AiChatAPI, { ChatSession } from "@/api/module_ai/chat";
import { assistantStream } from "@/api/module_ai/assistant";
import { Auth } from "@/utils/auth";
import type { ChatMessage, UploadedFile } from "./types";

// 状态
const messages = ref<ChatMessage[]>([]);
const sending = ref(false);
const isConnected = ref(false);
const connectionStatus = ref<"connected" | "connecting" | "disconnected">("disconnected");
const error = ref("");
const currentSessionId = ref<string | null>(null);
const isSidebarCollapsed = ref(false);

// Refs
const chatMessagesRef = ref<{ scrollToBottom: () => void }>();
const sidebarRef = ref<{ loadSessions: () => void }>();

// WebSocket
let ws: WebSocket | null = null;
const WS_URL = import.meta.env.VITE_APP_WS_ENDPOINT;

// ============ WebSocket 操作 ============
const connectWebSocket = () => {
  if (ws?.readyState === WebSocket.OPEN) return;

  connectionStatus.value = "connecting";
  error.value = "";

  try {
    const url = new URL("/api/v1/ai/chat/ws", WS_URL);
    const token = Auth.getAccessToken();
    if (token) url.searchParams.append("token", token);

    ws = new WebSocket(url.toString());

    ws.onopen = () => {
      isConnected.value = true;
      connectionStatus.value = "connected";
      ElMessage.success("连接成功");
    };

    ws.onmessage = (event) => handleWebSocketMessage(event.data);

    ws.onclose = () => {
      isConnected.value = false;
      connectionStatus.value = "disconnected";
      finishLoadingMessages();
    };

    ws.onerror = () => {
      isConnected.value = false;
      connectionStatus.value = "disconnected";
      ElMessage.error("连接失败，请检查服务器状态");
      finishLoadingMessages();
    };
  } catch {
    connectionStatus.value = "disconnected";
    error.value = "无法创建连接";
  }
};

const disconnectWebSocket = () => {
  if (ws) {
    ws.close(1000, "用户主动断开");
    ws = null;
  }
  isConnected.value = false;
  connectionStatus.value = "disconnected";
  finishLoadingMessages();
};

const toggleConnection = () => {
  if (isConnected.value) {
    disconnectWebSocket();
    ElMessage.info("已断开连接");
  } else {
    connectWebSocket();
  }
};

// ============ 消息处理 ============
const handleWebSocketMessage = (data: string) => {
  const lastMessage = messages.value[messages.value.length - 1];
  const content = data || "";

  // Agno 中间步骤事件（以 \u0000STEP 前缀的 JSON 行回传）：渲染为工具/思考提示
  if (content.startsWith("\u0000STEP ")) {
    try {
      const evt = JSON.parse(content.slice(6));
      const eventName = String(evt.event || "");
      let line = "";
      if (evt.tool) line = `\n\n> 🔧 调用工具：${evt.tool}`;
      else if (eventName.toLowerCase().includes("reason")) line = "\n\n> 🧠 思考中…";
      if (line) {
        if (lastMessage?.type === "assistant" && lastMessage.loading) lastMessage.content += line;
        else addMessage("assistant", line.trim());
      }
    } catch {
      /* 忽略非法事件 */
    }
    chatMessagesRef.value?.scrollToBottom();
    return;
  }

  if (lastMessage?.type === "assistant" && lastMessage.loading) {
    lastMessage.content += content;
  } else {
    addMessage("assistant", content);
  }

  chatMessagesRef.value?.scrollToBottom();
};

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

const finishLoadingMessages = () => {
  messages.value.forEach((msg) => {
    if (msg.type === "assistant" && msg.loading) {
      msg.loading = false;
      msg.collapsed = msg.content.length > 200;
    }
  });
};

const generateId = () => {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
};

// ============ 发送消息 ============
const handleSendMessage = async (message: string, files?: UploadedFile[]) => {
  if ((!message && !files) || sending.value) return;

  // 结束上一个加载中的消息
  finishLoadingMessages();

  // 创建新会话（如果没有）
  if (!currentSessionId.value) {
    const success = await createNewSession(message);
    if (!success) return;
  }

  // 添加用户消息
  addMessage("user", message, files);

  // 添加加载中的助手消息
  messages.value.push({
    id: generateId(),
    type: "assistant",
    content: "",
    timestamp: Date.now(),
    loading: true,
  });
  const last = messages.value[messages.value.length - 1];

  sending.value = true;
  chatMessagesRef.value?.scrollToBottom();

  try {
    // 走运行时 SSE（真流式：思考/回复/工具），不依赖 Agno WS
    await assistantStream(message, (event, data) => {
      if (event === "delta") {
        last.content += data.text || "";
      } else if (event === "tool") {
        last.content += `\n\n> 🔧 调用工具：${data.name}`;
      } else if (event === "reasoning") {
        last.content += "";
      } else if (event === "done") {
        if (data.report_id) last.content += `\n\n> 已生成报告 #${data.report_id}`;
      } else if (event === "error") {
        last.content += `\n\n> 出错：${data.message}`;
      }
      chatMessagesRef.value?.scrollToBottom();
    });
  } catch (e: any) {
    last.content += `\n\n> 请求失败：${e?.message || e}`;
  } finally {
    last.loading = false;
    sending.value = false;
    chatMessagesRef.value?.scrollToBottom();
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
    ElMessage.success("对话已清空");
  } catch {
    ElMessage.info("已取消清空对话");
  }
};

const toggleSidebar = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
};

// ============ 生命周期 ============
onMounted(connectWebSocket);
onUnmounted(disconnectWebSocket);
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
