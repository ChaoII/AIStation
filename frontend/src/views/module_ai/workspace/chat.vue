<!-- 工作台聊天：左时间归集会话列表 + 右 AI 渲染引擎（useAiChat + chat 组件） -->
<template>
  <div class="app-container ai-workspace-chat">
    <!-- 左：会话列表 -->
    <aside class="chat-side">
      <div class="chat-side-head">
        <span class="chat-side-name">{{ assistantName }}</span>
        <el-button size="small" type="primary" :icon="Plus" @click="newSession">
          {{ t("ai_chat.workspaceChat_newSession") }}
        </el-button>
      </div>
      <div class="chat-search">
        <el-input
          v-model="sessionSearch"
          :placeholder="t('ai_chat.workspaceChat_searchSession')"
          :prefix-icon="Search"
          size="small"
          clearable
        />
      </div>
      <el-scrollbar class="chat-side-scroll">
        <template v-for="group in sessionGroups" :key="group.label">
          <div class="chat-group-head">
            <span class="chat-group-label">{{ group.label }}</span>
            <el-tooltip
              v-if="group.key === 'today' && todaySessions.length"
              :content="t('ai_chat.workspaceChat_deleteToday')"
              placement="top"
            >
              <el-icon class="chat-group-del" @click.stop="delToday">
                <Delete />
              </el-icon>
            </el-tooltip>
          </div>
          <div
            v-for="s in group.items"
            :key="s.id"
            class="chat-sess"
            :class="{ 'chat-sess--active': s.id === currentSessionId }"
            @click="openSession(s)"
          >
            <div class="chat-sess-title">
              {{ s.title || t("ai_chat.workspaceChat_unnamed") }}
            </div>
            <div class="chat-sess-meta">
              <span>
                {{ t("ai_chat.workspaceChat_messageCount", { count: s.message_count ?? 0 }) }}
              </span>
              <span>· {{ fmtTime(s.updated_time) }}</span>
            </div>
            <el-icon class="chat-sess-del" @click.stop="delSession(s.id)"><Delete /></el-icon>
          </div>
        </template>
        <div v-if="!sessionGroups.length" class="chat-side-empty">
          {{ t("ai_chat.workspaceChat_empty") }}
        </div>
      </el-scrollbar>
      <div class="chat-side-foot">
        <el-button
          size="small"
          plain
          type="danger"
          :disabled="!sessions.length"
          @click="delAllSessions"
        >
          {{ t("ai_chat.workspaceChat_deleteAll") }}
        </el-button>
      </div>
    </aside>

    <!-- 右：对话区 -->
    <main class="chat-main">
      <div class="chat-main-head">
        <span class="chat-main-title">{{ currentSessionTitle }}</span>
        <div class="chat-main-actions">
          <el-tooltip :content="t('ai_chat.workspaceChat_exportTip')" placement="top">
            <el-button
              size="small"
              text
              :icon="Download"
              :disabled="!chat.messages.value.length"
              @click="exportSession"
            >
              {{ t("ai_chat.workspaceChat_export") }}
            </el-button>
          </el-tooltip>
        </div>
      </div>
      <ChatShell :scroll="false">
        <ChatOutline
          :items="outlineItems"
          container=".chat-messages"
          :title="t('ai_chat.chatOutline_title')"
        />
        <ChatMessages
          ref="msgRef"
          :messages="chat.messages.value"
          :error="chat.error.value || ''"
          :is-streaming="chat.isStreaming.value"
          :assistant-name="assistantName"
          @prompt-click="onPrompt"
          @resend="onSend"
        />
        <template #footer>
          <ChatInput
            :disabled="chat.isStreaming.value"
            :sending="chat.isStreaming.value"
            :models="models"
            :model-id="chatModelId"
            :thinking="chatThinking"
            @send="onSend"
            @stop="chat.stop()"
            @update:model-id="(v: number) => (chatModelId = v)"
            @update:thinking="(v: 'quick' | 'deep') => (chatThinking = v)"
          />
        </template>
      </ChatShell>
    </main>
  </div>
</template>

<script setup lang="ts">
import { Delete, Download, Plus, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";

import {
  createAiSession,
  deleteAiSessions,
  getAiSessionDetail,
  getAiSessionList,
  type AiSessionItem,
} from "@/api/module_ai/session";
import ChatInput from "@/views/module_ai/chat/components/ChatInput.vue";
import ChatMessages from "@/views/module_ai/chat/components/ChatMessages.vue";
import ChatShell from "@/components/chat/ChatShell.vue";
import ChatOutline from "@/components/chat/ChatOutline.vue";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiAgentDetail } from "@/api/module_ai/agent";
import { getAiWorkflowDetail } from "@/api/module_ai/workflow";
import { getAiAppList } from "@/api/module_ai/app";
import { useAiChat } from "@/composables/ai/useAiChat";
import { textOf } from "@/composables/ai/uiMessage";

defineOptions({ name: "AiWorkspaceChat" });

const { t } = useI18n();

const route = useRoute();
const router = useRouter();
const kind = String(route.params.kind || "agent");
const assetId = Number(route.params.id);

const pathMap: Record<string, string> = {
  agent: `/ai/agents/${assetId}/run/stream`,
  app: `/ai/apps/${assetId}/run/stream`,
  workflow: `/ai/workflows/${assetId}/run/stream`,
};
// 历史链接守卫：定时任务已迁出工作台（cron 不再有对话语义）。此前 cron 会回落到
// agent 的 run 接口（拿 cron id 当 agent id），直达旧 URL 会打错接口——这里直接送回工作台。
onMounted(() => {
  loadAssetName();
  if (!pathMap[kind]) {
    ElMessage.info(t("ai_chat.workspaceChat_noLongerSupported"));
    router.replace("/ai/workspace");
  }
});
const assetLabel = computed(
  () =>
    ({
      agent: t("ai_chat.workspaceChat_agent"),
      app: t("ai_chat.workspaceChat_app"),
      workflow: t("ai_chat.workspaceChat_workflow"),
    })[kind] || t("ai_chat.workspaceChat_chat")
);

// 从哪个智能体进来就用它的名字（以前助手固定叫「FA助手」，换个智能体也还是它）
const assetName = ref("");
const assistantName = computed(() => assetName.value || assetLabel.value);

async function loadAssetName() {
  try {
    if (kind === "agent") {
      const r: any = await getAiAgentDetail(assetId);
      // 注意：智能体表叫 agent_name，应用/工作流才是 name（写错过一次，界面上就退回"智能体"）
      assetName.value = r.data?.data?.agent_name || r.data?.data?.name || "";
    } else if (kind === "workflow") {
      const r: any = await getAiWorkflowDetail(assetId);
      assetName.value = r.data?.data?.name || "";
    } else if (kind === "app") {
      const r: any = await getAiAppList();
      const hit = (r.data?.data || []).find((x: any) => Number(x.id) === assetId);
      assetName.value = hit?.name || "";
    }
  } catch {
    /* 取不到名称就退回「智能体/应用/工作流」通用名 */
  }
}
// ---- 会话 ----
const sessions = ref<AiSessionItem[]>([]);
const currentSessionId = ref<number | null>(null);
const initialMessages = ref<any[]>([]);
const sessionSearch = ref("");

// 模型 / 思考强度
const models = ref<any[]>([]);
const chatModelId = ref<number | null>(null);
const chatThinking = ref<"quick" | "deep">("quick");
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
  // workflow 端点是 UI Message Stream（编排帧协议）；agent/app 端点是 Agno 原生事件
  protocol: kind === "workflow" ? "ui" : "agno",
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
  const groups: { key: string; label: string; items: AiSessionItem[] }[] = [
    { key: "today", label: t("ai_chat.workspaceChat_today"), items: [] },
    { key: "yesterday", label: t("ai_chat.workspaceChat_yesterday"), items: [] },
    { key: "week", label: t("ai_chat.workspaceChat_week"), items: [] },
    { key: "earlier", label: t("ai_chat.workspaceChat_earlier"), items: [] },
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

/** 长会话导航：按顺序列出用户提过的每个问题 */
const outlineItems = computed(() =>
  (chat.messages.value || [])
    .map((m: any, i: number) => ({ m, i }))
    .filter((x) => x.m.role === "user")
    .map((x) => ({
      id: `msg-${x.i}`,
      text: String(textOf(x.m) || "").slice(0, 80),
    }))
);

async function openSession(s: AiSessionItem) {
  currentSessionId.value = s.id;
  const res: any = await getAiSessionDetail(s.id);
  const msgs = (res.data?.data?.messages || []) as any[];
  initialMessages.value = msgs
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      id: String(m.id),
      role: m.role,
      // ⚠️ 必须原样保留 part：只留 {type,text} 会把工具调用的 state/input/output
      // 全丢掉 —— 界面上就是「永远进行中、点不开详情」（真实踩过）。
      parts: (m.parts || []).map((p: any) => ({ ...p })),
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
  await ElMessageBox.confirm(
    t("ai_chat.workspaceChat_deleteTodayConfirm", { count: ids.length }),
    t("ai_chat.workspaceChat_deleteToday"),
    {
      confirmButtonText: t("ai_chat.workspaceChat_delete"),
      cancelButtonText: t("ai_chat.workspaceChat_cancel"),
      type: "warning",
    }
  );
  await deleteAiSessions(ids);
  sessions.value = sessions.value.filter((s) => !ids.includes(s.id));
  if (currentSessionId.value && ids.includes(currentSessionId.value)) {
    currentSessionId.value = null;
    initialMessages.value = [];
  }
}

async function delAllSessions() {
  if (!sessions.value.length) return;
  await ElMessageBox.confirm(
    t("ai_chat.workspaceChat_deleteAllConfirm", { count: sessions.value.length }),
    t("ai_chat.workspaceChat_deleteAll"),
    {
      confirmButtonText: t("ai_chat.workspaceChat_delete"),
      cancelButtonText: t("ai_chat.workspaceChat_cancel"),
      type: "warning",
    }
  );
  await deleteAiSessions(sessions.value.map((s) => s.id));
  sessions.value = [];
  currentSessionId.value = null;
  initialMessages.value = [];
}

const currentSessionTitle = computed(() => {
  const s = sessions.value.find((x) => x.id === currentSessionId.value);
  return s?.title || t("ai_chat.workspaceChat_newSession");
});

/** 导出当前会话为 Markdown 文件（用于数据训练/标注）。 */
function exportSession() {
  const msgs = chat.messages.value;
  const lines: string[] = [`# ${currentSessionTitle.value}\n`];
  for (const m of msgs) {
    const role =
      m.role === "user" ? t("ai_chat.workspaceChat_user") : t("ai_chat.workspaceChat_ai");
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
  a.download = `${currentSessionTitle.value || t("ai_chat.workspaceChat_session")}.md`;
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
  flex: 0 0 240px;
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

/* 搜索框与下面分组之间留出呼吸感（原来几乎贴在一起，像被一条横线切开） */
.chat-search {
  padding: 10px 12px 14px;
}

.chat-side-scroll {
  flex: 1 1 auto;
  min-height: 0;
}

.chat-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 6px;
}

.chat-group-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-group-del {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;

  &:hover {
    color: var(--el-color-danger);
  }
}

.chat-group-head:hover .chat-group-del {
  opacity: 1;
}

.chat-sess {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 14px;
  margin: 0 6px 2px;
  cursor: pointer;
  border-radius: 6px;
  position: relative;
  transition: background 0.15s;
  &:hover {
    background: var(--el-fill-color-light);
  }
  &.chat-sess--active {
    background: var(--el-color-primary-light-9);
    box-shadow: inset 3px 0 0 var(--el-color-primary);
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
</style>
