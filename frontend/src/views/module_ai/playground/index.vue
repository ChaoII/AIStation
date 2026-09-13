<template>
  <div class="app-container">
    <el-row :gutter="16">
      <el-col :xs="24" :md="16">
        <el-card shadow="never">
          <template #header>
            <div class="pg-head">
              <div class="pg-head-left">
                <el-select
                  v-model="selectedAppId"
                  class="pg-app-select"
                  placeholder="通用助手"
                  clearable
                  @change="handleAppChange"
                >
                  <el-option label="通用助手" :value="0" />
                  <el-option v-for="a in apps" :key="a.id" :label="a.name" :value="a.id" />
                </el-select>
                <el-button size="small" @click="openSessions">历史会话</el-button>
              </div>
              <div class="pg-head-actions">
                <el-tag v-if="isBusy" type="warning" size="small">生成中…</el-tag>
                <el-tag v-else type="success" size="small">就绪</el-tag>
                <el-button v-if="isBusy" size="small" @click="stop">停止</el-button>
              </div>
            </div>
          </template>

          <el-scrollbar ref="scrollRef" height="calc(100vh - 260px)">
            <el-alert
              v-if="error"
              class="pg-error"
              type="error"
              :title="error.message"
              show-icon
              :closable="false"
            />
            <div v-if="!messages.length" class="pg-empty">
              试试：“我们有几个数据集？共多少张图？” / “生成一份训练与告警总结报告” /
              “打开模型仓库页”
            </div>

            <div
              v-for="(m, mi) in messages"
              :key="m.id || mi"
              class="pg-msg"
              :class="m.role === 'user' ? 'pg-msg--user' : 'pg-msg--assistant'"
            >
              <template v-if="m.role === 'user'">
                <div class="pg-bubble">{{ textOf(m) }}</div>
              </template>
              <template v-else>
                <template v-for="(p, pi) in m.parts" :key="pi">
                  <el-collapse v-if="p.type === 'reasoning' && p.text" class="pg-block">
                    <el-collapse-item title="思考过程" :name="String(pi)">
                      <div class="pg-pre">{{ p.text }}</div>
                    </el-collapse-item>
                  </el-collapse>

                  <div
                    v-else-if="p.type === 'text' && p.text"
                    class="pg-text"
                    v-html="renderMarkdown(p.text)"
                  ></div>

                  <el-collapse v-else-if="p.type === 'dynamic-tool'" class="pg-block">
                    <el-collapse-item :name="String(pi)">
                      <template #title>
                        <el-tag size="small">{{ p.toolName }}</el-tag>
                        <el-tag
                          class="pg-tool-state"
                          size="small"
                          :type="stateType(p.state)"
                          effect="plain"
                        >
                          {{ stateLabel(p.state) }}
                        </el-tag>
                      </template>
                      <div class="pg-pre">
                        参数：{{ stringify(p.input) }}
                        <template v-if="p.errorText">错误：{{ p.errorText }}</template>
                        <template v-else>结果：{{ stringify(p.output) }}</template>
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </template>
              </template>
            </div>
          </el-scrollbar>

          <div class="pg-compose">
            <el-input
              v-model="input"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="向系统提问或下达指令…（Enter 发送，Shift+Enter 换行）"
              @keydown.enter.exact.prevent="send"
            />
            <el-button type="primary" :loading="isBusy" :disabled="!input.trim()" @click="send">
              发送
            </el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never">
          <template #header>
            <div class="pg-head">
              <span>工具调用</span>
              <el-tag size="small" type="info" effect="plain">{{ allTools.length }}</el-tag>
            </div>
          </template>
          <el-timeline v-if="allTools.length">
            <el-timeline-item
              v-for="(t, i) in allTools"
              :key="i"
              :type="stateType(t.state)"
              placement="top"
            >
              <div class="pg-tool">
                <el-tag size="small">{{ t.toolName }}</el-tag>
                <el-tag size="small" :type="stateType(t.state)" effect="plain">
                  {{ stateLabel(t.state) }}
                </el-tag>
              </div>
              <div class="pg-tool-detail">{{ stringify(t.input) }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无工具调用" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>

    <el-drawer v-model="drawerVisible" title="会话历史" size="360px" direction="rtl">
      <div class="pg-drawer-head">
        <el-button type="primary" size="small" @click="newSession">新建会话</el-button>
        <el-button size="small" @click="loadSessions">刷新</el-button>
      </div>
      <el-scrollbar height="calc(100vh - 170px)">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="pg-session"
          :class="{ 'pg-session--active': s.id === sessionId }"
          @click="selectSession(s)"
        >
          <div class="pg-session-main">
            <div class="pg-session-title">{{ s.title || "未命名会话" }}</div>
            <div class="pg-session-meta">{{ s.message_count }} 条 · {{ s.created_time }}</div>
          </div>
          <el-button link type="danger" size="small" @click.stop="removeSession(s)">删除</el-button>
        </div>
        <el-empty v-if="!sessions.length" description="暂无会话" :image-size="60" />
      </el-scrollbar>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from "vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAiChat } from "@/composables/ai/useAiChat";
import { textOf, type AiUIPart } from "@/composables/ai/uiMessage";
import { getAiAppList } from "@/api/module_ai/app";
import {
  createAiSession,
  deleteAiSessions,
  getAiSessionDetail,
  getAiSessionList,
} from "@/api/module_ai/session";

const md = new MarkdownIt({ breaks: true, linkify: true });

const apps = ref<any[]>([]);
const selectedAppId = ref<number | null>(null);
const sessionId = ref<number | null>(null);
const drawerVisible = ref(false);
const sessions = ref<any[]>([]);

// getter 形式：切换应用时 path 变化 → useAiChat 内部 computed 重建 transport
const chat = useAiChat(() => ({
  path: selectedAppId.value ? `/ai/apps/${selectedAppId.value}/run/stream` : "/ai/assistant/stream",
  body: () => ({ session_id: sessionId.value ?? undefined, variables: {} }),
}));
const { messages, status, error, sendMessage, stop } = chat;

const input = ref("");
const scrollRef = ref<{ setScrollTop: (top: number) => void }>();

const isBusy = computed(() => status.value === "submitted" || status.value === "streaming");

/** 汇总所有消息中的工具调用 part。 */
const allTools = computed<AiUIPart[]>(() =>
  messages.value.flatMap((m) => (m.parts || []).filter((p: any) => p.type === "dynamic-tool"))
);

function renderMarkdown(text: string): string {
  return DOMPurify.sanitize(md.render(text || ""));
}

function stringify(value: any): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function stateLabel(state?: string): string {
  switch (state) {
    case "input-streaming":
      return "生成参数";
    case "input-available":
      return "调用中";
    case "output-available":
      return "已完成";
    case "output-error":
      return "出错";
    default:
      return state || "—";
  }
}

function stateType(state?: string): "success" | "warning" | "danger" | "info" {
  switch (state) {
    case "output-available":
      return "success";
    case "output-error":
      return "danger";
    case "input-streaming":
    case "input-available":
      return "warning";
    default:
      return "info";
  }
}

async function send() {
  const text = input.value.trim();
  if (!text || isBusy.value) return;
  input.value = "";
  await sendMessage({ text });
}

async function loadApps() {
  try {
    const res = await getAiAppList();
    apps.value = res.data?.data || [];
  } catch {
    /* 静默：应用列表非核心 */
  }
}

function handleAppChange() {
  sessionId.value = null;
  chat.messages.value = [];
}

async function loadSessions() {
  try {
    const res = await getAiSessionList();
    sessions.value = res.data?.data || [];
  } catch {
    /* 静默 */
  }
}

function openSessions() {
  drawerVisible.value = true;
  loadSessions();
}

async function newSession() {
  try {
    const res = await createAiSession({
      title: "新会话",
      app_id: selectedAppId.value || null,
    });
    sessionId.value = res.data?.data?.id ?? null;
    chat.messages.value = [];
    drawerVisible.value = false;
    await loadSessions();
  } catch {
    ElMessage.error("新建会话失败");
  }
}

async function selectSession(s: any) {
  try {
    const res = await getAiSessionDetail(s.id);
    const msgs = res.data?.data?.messages || [];
    sessionId.value = s.id;
    // 先切回会话所属应用：selectedAppId 是 chat init 依赖，会重建 transport；
    // 等重建（消息被清空）落地后再回填历史消息，避免续聊串用其他应用的模型/工具。
    selectedAppId.value = s.app_id ?? 0;
    await nextTick();
    chat.messages.value = msgs.map((m: any) => ({
      id: `s-${m.id}`,
      role: m.role,
      parts: m.parts || [],
    }));
    drawerVisible.value = false;
  } catch {
    ElMessage.error("加载会话失败");
  }
}

async function removeSession(s: any) {
  try {
    await ElMessageBox.confirm("确认删除该会话?", "警告", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteAiSessions([s.id]);
    if (sessionId.value === s.id) {
      sessionId.value = null;
      chat.messages.value = [];
    }
    await loadSessions();
  } catch {
    ElMessage.error("删除失败");
  }
}

watch(
  () => messages.value.length,
  async () => {
    await nextTick();
    scrollRef.value?.setScrollTop(999999);
  }
);

onMounted(loadApps);
</script>

<style scoped lang="scss">
.pg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pg-head-left {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pg-app-select {
  width: 200px;
}

.pg-head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pg-error {
  margin-bottom: 12px;
}

.pg-empty {
  padding: 40px 12px;
  color: var(--el-text-color-placeholder);
  text-align: center;
}

.pg-msg {
  margin-bottom: 16px;

  &--user {
    display: flex;
    justify-content: flex-end;
  }
}

.pg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
}

.pg-text {
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: break-word;

  :deep(p) {
    margin: 8px 0;
  }

  :deep(table) {
    width: 100%;
    margin: 8px 0;
    border-collapse: collapse;
  }

  :deep(th),
  :deep(td) {
    padding: 6px 8px;
    border: 1px solid var(--el-border-color-lighter);
  }

  :deep(pre) {
    padding: 12px;
    overflow-x: auto;
    background: var(--el-fill-color-light);
    border-radius: 6px;
  }
}

.pg-block {
  margin: 8px 0;
}

.pg-tool-state {
  margin-left: 8px;
}

.pg-pre {
  max-height: 320px;
  overflow: auto;
  font-family: "Courier New", Courier, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

.pg-compose {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.pg-tool {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pg-tool-detail {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}

.pg-drawer-head {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.pg-session {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &--active {
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary);
  }
}

.pg-session-main {
  min-width: 0;
}

.pg-session-title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  white-space: nowrap;
}

.pg-session-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
