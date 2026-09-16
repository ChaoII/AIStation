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
          @delete-session="handleSessionDeleted"
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
import { createAiSession, getAiSessionDetail, type AiSessionItem } from "@/api/module_ai/session";
import { getAiAppDetail } from "@/api/module_ai/app";
import { useAiChat } from "@/composables/ai/useAiChat";
import { textOf, reasoningOf, toolPartsOf } from "@/composables/ai/uiMessage";
import type { ChatMessage, UploadedFile } from "./types";

const route = useRoute();
const router = useRouter();

// 状态
const messages = ref<ChatMessage[]>([]);
const error = ref("");
// 运行时 ai_sessions 主键为整数；null 表示尚未落库的新会话
const currentSessionId = ref<number | null>(null);
const isSidebarCollapsed = ref(false);

// 运行中的 AI 应用（?app_id=）：非空时流式走 /ai/apps/{id}/run/stream
const appId = ref<number | null>(route.query.app_id ? Number(route.query.app_id) : null);
const appName = ref("");
// 请求令牌：discard out-of-order responses when app_id changes quickly
let appLoadToken = 0;

watch(
  () => route.query.app_id,
  async (v) => {
    const token = ++appLoadToken;
    appId.value = v ? Number(v) : null;
    appName.value = "";
    if (!appId.value) return;
    try {
      const res = await getAiAppDetail(appId.value);
      // 过期响应（app_id 已变更）直接丢弃
      if (token !== appLoadToken) return;
      const app = res.data?.data;
      if (!app) {
        // 应用不存在/无数据：回退通用助手，避免向不存在的应用发消息
        appId.value = null;
        appName.value = "";
        return;
      }
      appName.value = app.name || "";
    } catch {
      if (token !== appLoadToken) return;
      // 详情请求失败：回退通用助手，避免 POST 到不存在的应用
      appId.value = null;
      appName.value = "";
    }
  },
  { immediate: true }
);

// AI SDK 流式聊天（getter：随所选应用动态切换 path/body，替代旧 Agno WS）。
// body 在发送时读取响应式值：session_id 为 ai_sessions 整数主键（persist_session_exchange 需要），
// 选中应用时附 app_id 供新建会话记录归属。
const chat = useAiChat(() => ({
  path: appId.value ? `/ai/apps/${appId.value}/run/stream` : "/ai/assistant/stream",
  body: () => {
    const payload: Record<string, unknown> = {};
    if (currentSessionId.value != null) payload.session_id = currentSessionId.value;
    if (appId.value != null) payload.app_id = appId.value;
    return payload;
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
  const title = firstMessage.slice(0, 20) + (firstMessage.length > 20 ? "..." : "");
  try {
    // 运行时会话：写入 ai_sessions（整数主键），选中应用时记录 app_id
    const res = await createAiSession({ title, app_id: appId.value });
    const created = res.data?.data;
    if (created?.id != null) {
      currentSessionId.value = created.id;
      sidebarRef.value?.loadSessions();
      return true;
    }
    ElMessage.error("创建会话失败");
    return false;
  } catch (e: any) {
    // 请求层通常已弹提示；仅对未被覆盖的异常兜底，保证创建失败绝不静默
    const alreadyToasted = !!(e?.data?.msg || e?.msg || e instanceof Error);
    if (!alreadyToasted) ElMessage.error("创建会话失败");
    return false;
  }
};

// ============ 会话操作 ============
// 对齐应用归属：以目标会话的 app_id 为准同步 appId 与地址栏 query。
// 避免在 ?app_id= 下选中通用会话时仍走应用端点，并把 app_id 错盖到通用会话上。
// appName 由 route.query.app_id 的 watch 负责刷新（query 未变时无需重复请求）。
const syncAppContext = (targetAppId: number | null) => {
  appId.value = targetAppId;
  const current = route.query.app_id ? Number(route.query.app_id) : null;
  if (targetAppId === current) return;
  router.replace({
    path: "/ai/chat",
    query: targetAppId ? { app_id: String(targetAppId) } : {},
  });
};

const handleSelectSession = async (session: AiSessionItem) => {
  syncAppContext(session.app_id ?? null);
  currentSessionId.value = session.id;
  messages.value = [];
  chat.messages.value = [];

  try {
    const res = await getAiSessionDetail(session.id);
    const detail = res.data?.data;
    if (!detail) return;

    // 从落库 parts 还原为 AI SDK UIMessage，既用于展示也作为后续对话上下文
    chat.messages.value = (detail.messages || [])
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        id: String(m.id),
        role: m.role as "user" | "assistant",
        parts: (m.parts || [])
          .filter((p) => p.type === "text" && p.text)
          .map((p) => ({ type: "text" as const, text: String(p.text) })),
      }))
      .filter((m) => m.parts.length > 0);

    ElMessage.success(`已切换到会话：${detail.title || "未命名会话"}`);
  } catch {
    ElMessage.error("获取会话详情失败");
  }
};

const handleNewSession = () => {
  // 保留当前应用上下文：选中应用时新会话归属该 app，已清除应用时 appId 保持 null
  currentSessionId.value = null;
  messages.value = [];
  chat.messages.value = [];
  ElMessage.success("已开启新对话");
};

// 删除会话后，若删除的是当前激活会话，重置为“未落库”状态，
// 让下一次发送重新创建会话，避免往已删除的 id 上落库（record_exchange 找不到行）。
// 应用上下文由 ?app_id= 决定（切换会话时已对齐），删除当前会话不改变所在应用。
const handleSessionDeleted = (ids: number[]) => {
  if (currentSessionId.value == null || !ids.includes(currentSessionId.value)) return;
  currentSessionId.value = null;
  messages.value = [];
  chat.messages.value = [];
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
