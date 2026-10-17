<!-- 工作台聊天：左时间归集会话列表 + 右 AI 渲染引擎（useAiChat + chat 组件） -->
<template>
  <div class="app-container ai-workspace-chat">
    <!-- 左：会话列表 -->
    <aside class="chat-side">
      <div class="chat-side-head">
        <span class="chat-side-name">{{ assetLabel }}</span>
        <el-button size="small" type="primary" :icon="Plus" @click="newSession">新建会话</el-button>
      </div>
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
          <div class="chat-group-head">
            <span class="chat-group-label">{{ group.label }}</span>
            <el-button
              v-if="group.label === '今天' && todaySessions.length"
              link
              size="small"
              class="chat-group-del"
              @click="delToday"
            >
              删除今天
            </el-button>
          </div>
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
        <el-button
          size="small"
          plain
          type="danger"
          :disabled="!sessions.length"
          @click="delAllSessions"
        >
          删除全部
        </el-button>
      </div>
    </aside>

    <!-- 右：对话区 -->
    <main class="chat-main">
      <div class="chat-main-head">
        <span class="chat-main-title">{{ currentSessionTitle }}</span>
        <div class="chat-main-actions">
          <el-tooltip content="导出会话为 Markdown" placement="top">
            <el-button
              size="small"
              text
              :icon="Download"
              :disabled="!chat.messages.value.length"
              @click="exportSession"
            >
              导出
            </el-button>
          </el-tooltip>
        </div>
      </div>
      <ChatMessages
        ref="msgRef"
        :messages="chat.messages.value"
        :error="chat.error.value || ''"
        :is-streaming="chat.isStreaming.value"
        @prompt-click="onPrompt"
        @resend="onSend"
      />
      <div class="chat-toolbar">
        <el-dropdown trigger="click" @command="(m: any) => (chatModelId = m.id)">
          <span class="ct-trigger">
            <span class="ct-avatar">{{ (chatModelLabel[0] || "M").toUpperCase() }}</span>
            <span class="ct-name">{{ chatModelLabel }}</span>
            <el-icon class="ct-chevron"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="m in models"
                :key="m.id"
                :command="m"
                :class="{ 'is-active': m.id === chatModelId }"
              >
                {{ m.name }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <div class="ct-thinking">
          <el-tooltip :content="chatThinking === 'deep' ? '深度思考' : '快速'">
            <span
              class="ct-mode"
              :class="{ 'ct-mode--deep': chatThinking === 'deep' }"
              @click="chatThinking = chatThinking === 'deep' ? 'quick' : 'deep'"
            >
              {{ chatThinking === "deep" ? "🧠" : "⚡" }}
            </span>
          </el-tooltip>
        </div>
      </div>
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
import { Delete, Download, Plus, Search, ArrowDown } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
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
import { getAiModelList } from "@/api/module_ai/model";
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
const assetLabel = computed(
  () => ({ agent: "智能体", app: "应用", workflow: "工作流", cron: "定时任务" })[kind] || "对话"
);
// ---- 会话 ----
const sessions = ref<AiSessionItem[]>([]);
const currentSessionId = ref<number | null>(null);
const initialMessages = ref<any[]>([]);
const sessionSearch = ref("");

// 模型 / 思考强度
const models = ref<any[]>([]);
const chatModelId = ref<number | null>(null);
const chatThinking = ref<"quick" | "deep">("quick");
const chatModelLabel = computed(() => {
  const m = models.value.find((x) => x.id === chatModelId.value);
  return m?.name || "选择模型";
});
async function loadModels() {
  try {
    const res: any = await getAiModelList();
    models.value = res.data?.data || [];
  } catch {
    models.value = [];
  }
}

const chat = useAiChat({
  path: pathMap[kind] || pathMap.agent,
  body: () => ({
    session_id: currentSessionId.value,
    model_id: chatModelId.value,
    thinking: chatThinking.value,
  }),
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
  await ElMessageBox.confirm(`将删除今天的 ${ids.length} 个会话，是否继续？`, "删除今天", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await deleteAiSessions(ids);
  sessions.value = sessions.value.filter((s) => !ids.includes(s.id));
  if (currentSessionId.value && ids.includes(currentSessionId.value)) {
    currentSessionId.value = null;
    initialMessages.value = [];
  }
}

async function delAllSessions() {
  if (!sessions.value.length) return;
  await ElMessageBox.confirm(`将删除全部 ${sessions.value.length} 个会话，是否继续？`, "删除全部", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await deleteAiSessions(sessions.value.map((s) => s.id));
  sessions.value = [];
  currentSessionId.value = null;
  initialMessages.value = [];
}

const currentSessionTitle = computed(() => {
  const s = sessions.value.find((x) => x.id === currentSessionId.value);
  return s?.title || "新会话";
});

/** 导出当前会话为 Markdown 文件（用于数据训练/标注）。 */
function exportSession() {
  const msgs = chat.messages.value;
  const lines: string[] = [`# ${currentSessionTitle.value}\n`];
  for (const m of msgs) {
    const role = m.role === "user" ? "用户" : "AI";
    const text = (m.parts || [])
      .filter((p: any) => p.type === "text")
      .map((p: any) => p.text || "")
      .join("");
    lines.push(`## ${role}\n\n${text || ""}\n`);
  }
  const content = lines.join("\n");
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentSessionTitle.value || "会话"}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function onPrompt(p: string) {
  chat.sendMessage({ text: p });
}

function onSend(text: string) {
  chat.sendMessage({ text });
}

loadSessions();
loadModels();
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
  border-radius: 6px;
  overflow: hidden;
}

.chat-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.chat-side-name {
  font-weight: 600;
  font-size: var(--el-font-size-base);
}

.chat-search {
  padding: 0 12px 8px;
}

.chat-side-scroll {
  flex: 1 1 auto;
  min-height: 0;
}

.chat-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px 4px;
}

.chat-group-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-group-del {
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
  border-radius: 6px;
  overflow: hidden;
}

.chat-main-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.chat-main-title {
  font-weight: 600;
  font-size: var(--el-font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-main-actions {
  flex-shrink: 0;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px 0;
}

.ct-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    color: var(--el-color-primary);
    border-color: var(--el-color-primary-light-5);
    background: var(--el-color-primary-light-9);
  }
}

.ct-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 9px;
  font-weight: 600;
}

.ct-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ct-chevron {
  font-size: 12px;
}

.ct-thinking {
  display: inline-flex;
}

.ct-mode {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--el-color-primary-light-5);
  }

  &.ct-mode--deep {
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-5);
  }
}
</style>
