<!-- 工作台聊天：左时间归集会话列表 + 右 AI 渲染引擎（useAiChat + chat 组件） -->
<template>
  <div class="app-container ai-workspace-chat">
    <!-- 左：会话列表 -->
    <aside class="chat-side">
      <button class="chat-new-session" @click="newSession">
        <el-icon><Plus /></el-icon>
        <span>新建会话</span>
      </button>
      <div class="chat-search">
        <el-input
          v-model="sessionSearch"
          placeholder="搜索会话..."
          :prefix-icon="Search"
          size="small"
          clearable
        />
      </div>
      <el-scrollbar class="chat-side-scroll">
        <template v-for="group in sessionGroups" :key="group.label">
          <div class="chat-group-label">{{ group.label }}</div>
          <div
            v-for="s in group.items"
            :key="s.id"
            class="chat-sess"
            :class="{ 'chat-sess--active': s.id === currentSessionId }"
            @click="openSession(s)"
          >
            <div class="chat-sess-title">{{ s.title || "未命名会话" }}</div>
            <div class="chat-sess-meta">
              <span>{{ s.message_count ?? 0 }} 条</span>
              <span>· {{ fmtTime(s.updated_time) }}</span>
            </div>
            <el-icon class="chat-sess-del" @click.stop="delSession(s.id)"><Delete /></el-icon>
          </div>
        </template>
        <div v-if="!sessionGroups.length" class="chat-side-empty">暂无会话，点「新建会话」开始</div>
      </el-scrollbar>
      <div class="chat-side-foot">
        <el-button size="small" plain :disabled="!todaySessions.length" @click="delToday">
          删除当天会话
        </el-button>
      </div>
    </aside>

    <!-- 右：对话区 -->
    <main class="chat-main">
      <ChatMessages
        ref="msgRef"
        :messages="chat.messages.value"
        :error="chat.error.value || ''"
        :is-streaming="chat.isStreaming.value"
        @prompt-click="onPrompt"
      />
      <ChatInput
        :disabled="chat.isStreaming.value"
        :sending="chat.isStreaming.value"
        @send="onSend"
        @stop="chat.stop()"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { Delete, Plus, Search } from "@element-plus/icons-vue";
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

import {
  createAiSession,
  deleteAiSessions,
  getAiSessionDetail,
  getAiSessionList,
  type AiSessionItem,
} from "@/api/module_ai/session";
import ChatInput from "@/views/module_ai/chat/components/ChatInput.vue";
import ChatMessages from "@/views/module_ai/chat/components/ChatMessages.vue";
import { useAiChat } from "@/composables/ai/useAiChat";

defineOptions({ name: "AiWorkspaceChat" });

const route = useRoute();
const kind = String(route.params.kind || "agent");
const assetId = Number(route.params.id);

const pathMap: Record<string, string> = {
  agent: `/ai/agents/${assetId}/run/stream`,
  app: `/ai/apps/${assetId}/run/stream`,
  workflow: `/ai/workflows/${assetId}/run/stream`,
};
// ---- 会话 ----
const sessions = ref<AiSessionItem[]>([]);
const currentSessionId = ref<number | null>(null);
const initialMessages = ref<any[]>([]);
const sessionSearch = ref("");

const chat = useAiChat({
  path: pathMap[kind] || pathMap.agent,
  body: () => ({ session_id: currentSessionId.value }),
  id: currentSessionId,
  initialMessages,
});

async function loadSessions() {
  const res: any = await getAiSessionList({ app_id: assetId });
  sessions.value = res.data?.data || [];
}

function fmtTime(t?: string | null) {
  if (!t) return "";
  const d = new Date(t);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function isToday(t?: string | null) {
  if (!t) return false;
  const d = new Date(t);
  const now = new Date();
  return d.toDateString() === now.toDateString();
}

const sessionGroups = computed(() => {
  const q = sessionSearch.value.toLowerCase();
  const list = q
    ? sessions.value.filter((s) => (s.title || "").toLowerCase().includes(q))
    : sessions.value;
  const groups: { label: string; items: AiSessionItem[] }[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "近 7 天", items: [] },
    { label: "更早", items: [] },
  ];
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const weekAgo = new Date();
  weekAgo.setDate(today.getDate() - 7);
  for (const s of list) {
    const d = new Date(s.updated_time || s.created_time || 0);
    if (d.toDateString() === today.toDateString()) groups[0].items.push(s);
    else if (d.toDateString() === yesterday.toDateString()) groups[1].items.push(s);
    else if (d > weekAgo) groups[2].items.push(s);
    else groups[3].items.push(s);
  }
  return groups.filter((g) => g.items.length);
});

const todaySessions = computed(() => sessions.value.filter((s) => isToday(s.updated_time)));

async function openSession(s: AiSessionItem) {
  currentSessionId.value = s.id;
  const res: any = await getAiSessionDetail(s.id);
  const msgs = (res.data?.data?.messages || []) as any[];
  initialMessages.value = msgs
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: String(m.id),
      role: m.role,
      parts: (m.parts || []).map((p: any) => ({ type: p.type, text: p.text })),
    }));
}

async function newSession() {
  const res: any = await createAiSession({ app_id: assetId });
  const s = res.data?.data as AiSessionItem;
  sessions.value.unshift(s);
  currentSessionId.value = s.id;
  initialMessages.value = [];
}

async function delSession(id: number) {
  await deleteAiSessions([id]);
  sessions.value = sessions.value.filter((s) => s.id !== id);
  if (currentSessionId.value === id) {
    currentSessionId.value = null;
    initialMessages.value = [];
  }
}

async function delToday() {
  const ids = todaySessions.value.map((s) => s.id);
  if (!ids.length) return;
  await deleteAiSessions(ids);
  sessions.value = sessions.value.filter((s) => !ids.includes(s.id));
  if (currentSessionId.value && ids.includes(currentSessionId.value)) {
    currentSessionId.value = null;
    initialMessages.value = [];
  }
}

function onPrompt(p: string) {
  chat.sendMessage({ text: p });
}

function onSend(text: string) {
  chat.sendMessage({ text });
}

loadSessions();
</script>

<style lang="scss" scoped>
.ai-workspace-chat {
  height: 100%;
  display: flex;
  flex-direction: row;
  gap: 12px;
  padding: 12px;
  box-sizing: border-box;
}

.chat-side {
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}

.chat-new-session {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 12px;
  padding: 10px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  &:hover {
    border-color: var(--el-color-primary);
    color: var(--el-color-primary);
    box-shadow: 0 2px 8px rgb(0 0 0 / 6%);
  }
}

.chat-search {
  padding: 0 12px 8px;
}

.chat-side-scroll {
  flex: 1 1 auto;
  min-height: 0;
}

.chat-group-label {
  padding: 8px 14px 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-sess {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px;
  cursor: pointer;
  border-radius: 8px;
  position: relative;
  transition: background 0.15s;
  &:hover {
    background: var(--el-fill-color-light);
  }
  &.chat-sess--active {
    background: var(--el-color-primary-light-9);
  }

  .chat-sess-del {
    position: absolute;
    top: 50%;
    right: 10px;
    transform: translateY(-50%);
    opacity: 0;
    color: var(--el-text-color-secondary);
    cursor: pointer;
    &:hover {
      color: var(--el-color-danger);
    }
  }
  &:hover .chat-sess-del {
    opacity: 1;
  }
  &.chat-sess--active .chat-sess-del {
    opacity: 1;
  }
}

.chat-sess-title {
  font-size: var(--el-font-size-base);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 20px;
}

.chat-sess-meta {
  display: flex;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-side-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-side-foot {
  padding: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: center;
}

.chat-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}
</style>
