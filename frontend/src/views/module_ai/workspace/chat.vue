<!-- 工作台聊天：左时间归集会话列表 + 右 AI 渲染引擎（useAiChat + chat 组件） -->
<template>
  <div class="app-container ai-workspace-chat">
    <!-- 左：会话列表 -->
    <aside class="chat-side">
      <div class="chat-side-head">
        <span class="chat-side-title">{{ assetLabel }}</span>
        <el-button size="small" type="primary" :icon="Plus" @click="newSession">新会话</el-button>
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
            <div class="chat-sess-main">
              <div class="chat-sess-title">{{ s.title || "未命名会话" }}</div>
              <div class="chat-sess-meta">
                {{ s.message_count ?? 0 }} 条 · {{ fmtTime(s.updated_time) }}
              </div>
            </div>
            <el-icon class="chat-sess-del" @click.stop="delSession(s.id)"><Delete /></el-icon>
          </div>
        </template>
        <div v-if="!sessionGroups.length" class="chat-side-empty">暂无会话，点「新会话」开始</div>
      </el-scrollbar>
      <div class="chat-side-foot">
        <el-button size="small" :disabled="!todaySessions.length" @click="delToday">
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
import { Delete, Plus } from "@element-plus/icons-vue";
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
const labelMap: Record<string, string> = {
  agent: "智能体",
  app: "应用",
  workflow: "工作流",
  cron: "定时任务",
};
const assetLabel = computed(() => labelMap[kind] || "对话");

// ---- 会话 ----
const sessions = ref<AiSessionItem[]>([]);
const currentSessionId = ref<number | null>(null);
const initialMessages = ref<any[]>([]);

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
  for (const s of sessions.value) {
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
  gap: 12px;
  padding: 12px;
  box-sizing: border-box;
}

.chat-side {
  flex: 0 0 240px;
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  overflow: hidden;
}

.chat-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.chat-side-title {
  font-weight: 600;
}

.chat-side-scroll {
  flex: 1 1 auto;
  min-height: 0;
}

.chat-group-label {
  padding: 8px 12px 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-sess {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 8px;
  &:hover {
    background: var(--el-fill-color-light);
  }
  &.chat-sess--active {
    background: var(--el-color-primary-light-9);
  }
}

.chat-sess-main {
  min-width: 0;
  flex: 1;
}

.chat-sess-title {
  font-size: var(--el-font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-sess-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-sess-del {
  opacity: 0;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  &:hover {
    color: var(--el-color-danger);
  }
}
.chat-sess:hover .chat-sess-del {
  opacity: 1;
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
