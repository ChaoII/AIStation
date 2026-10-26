<!--
  对话嵌入页（/#/embed）——独立公开路由，无平台登录。
  鉴权：URL 上的一次性短期 access_token（由宿主服务端用 appid:appkey 换票获得）。
  安全：页面不接触 appkey；401 时向宿主发 token_expired，由宿主换票后 setToken 热替换。
  交互契约：上行 7 类事件（信封 source=ai-embed/version=1），下行命令 setToken/sendMessage/resize/destroy。
-->
<template>
  <div class="embed-page" :style="themeStyle">
    <!-- 缺凭证 -->
    <div v-if="fatal === 'missing'" class="embed-state">
      <div class="embed-state__icon">
        <el-icon><Warning /></el-icon>
      </div>
      <div class="embed-state__title">{{ t("ai_workflow.embed_missingTitle") }}</div>
      <p class="embed-state__desc">
        {{ t("ai_workflow.embed_missingDesc") }}
      </p>
    </div>

    <!-- 初始化骨架 -->
    <div v-else-if="loading" class="embed-shell">
      <header class="embed-header">
        <el-skeleton animated>
          <template #template>
            <div class="embed-skeleton-row">
              <el-skeleton-item variant="circle" style="width: 8px; height: 8px" />
              <el-skeleton-item variant="text" style="width: 36%; height: 12px" />
            </div>
          </template>
        </el-skeleton>
        <span class="embed-header__brand">{{ t("ai_workflow.embed_brand") }}</span>
      </header>
      <div class="embed-messages embed-messages--loading">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item variant="text" style="width: 62%; height: 30px" />
            <el-skeleton-item variant="text" style="width: 44%; height: 30px; margin-left: auto" />
            <el-skeleton-item variant="text" style="width: 70%; height: 58px" />
          </template>
        </el-skeleton>
      </div>
      <footer class="embed-input embed-input--placeholder">
        <el-skeleton-item variant="text" style="width: 100%; height: 34px" />
      </footer>
    </div>

    <!-- 凭证过期 / 无权限 -->
    <div v-else-if="fatal === 'expired' || fatal === 'forbidden'" class="embed-state">
      <div class="embed-state__icon" :class="{ 'is-warn': fatal === 'expired' }">
        <el-icon>
          <Timer v-if="fatal === 'expired'" />
          <Lock v-else />
        </el-icon>
      </div>
      <div class="embed-state__title">
        {{
          fatal === "expired"
            ? t("ai_workflow.embed_expiredTitle")
            : t("ai_workflow.embed_forbiddenTitle")
        }}
      </div>
      <p class="embed-state__desc">
        {{
          fatal === "expired"
            ? t("ai_workflow.embed_expiredDesc")
            : t("ai_workflow.embed_forbiddenDesc")
        }}
      </p>
    </div>

    <!-- 正常对话 -->
    <div v-else class="embed-shell">
      <header class="embed-header">
        <div class="embed-header__main">
          <span class="embed-header__dot" :class="isStreaming ? 'is-busy' : 'is-ready'" />
          <span class="embed-header__name" :title="meta?.name">
            {{ meta?.name || t("ai_workflow.embed_conversation") }}
          </span>
        </div>
        <span class="embed-header__brand">{{ t("ai_workflow.embed_brand") }}</span>
      </header>

      <div ref="scrollRef" class="embed-messages" @scroll="onScroll">
        <div v-if="!messages.length && !isStreaming" class="embed-welcome">
          <div class="embed-welcome__badge">{{ initialChar }}</div>
          <p class="embed-welcome__text">{{ welcomeText }}</p>
          <p class="embed-welcome__hint">{{ t("ai_workflow.embed_hint") }}</p>
        </div>

        <template v-for="(m, i) in messages" :key="m.id || `m-${i}`">
          <div
            v-if="textOf(m)"
            class="embed-msg"
            :class="m.role === 'user' ? 'is-user' : 'is-assistant'"
          >
            <div class="embed-msg__avatar" :class="m.role === 'user' ? 'is-user' : 'is-ai'">
              {{ m.role === "user" ? t("ai_workflow.embed_you") : initialChar }}
            </div>
            <div class="embed-msg__content">
              <div class="embed-msg__sender">
                {{
                  m.role === "user"
                    ? t("ai_workflow.embed_you")
                    : meta?.name || t("ai_workflow.embed_aiAssistant")
                }}
              </div>
              <div class="embed-msg__body">
                <div v-if="m.role === 'user'" class="embed-msg__text">{{ textOf(m) }}</div>
                <template v-else>
                  <RichContent :content="textOf(m)" />
                  <span v-if="isTypingTail(i)" class="embed-caret" />
                </template>
              </div>
              <div v-if="m.role !== 'user' && sourcesOf(i).length" class="embed-sources">
                <button type="button" class="embed-sources__toggle" @click="toggleSources(i)">
                  <span>
                    {{ t("ai_workflow.embed_sourcesCount", { count: sourcesOf(i).length }) }}
                  </span>
                  <el-icon>
                    <ArrowDown v-if="!openSources[i]" />
                    <ArrowUp v-else />
                  </el-icon>
                </button>
                <ul v-if="openSources[i]" class="embed-sources__list">
                  <li v-for="(s, si) in sourcesOf(i)" :key="si" class="embed-sources__item">
                    <span class="embed-sources__title">{{ sourceTitle(s) }}</span>
                    <span v-if="s && s.score != null" class="embed-sources__score">
                      {{ Number(s.score).toFixed(2) }}
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </template>

        <div v-if="showTyping" class="embed-msg is-assistant">
          <div class="embed-msg__avatar is-ai">{{ initialChar }}</div>
          <div class="embed-msg__content">
            <div class="embed-msg__sender">
              {{ meta?.name || t("ai_workflow.embed_aiAssistant") }}
            </div>
            <div class="embed-typing">
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>

        <div v-if="notice" class="embed-notice">
          <span>{{ notice }}</span>
          <button v-if="noticeRetry" type="button" class="embed-notice__retry" @click="retryMeta">
            {{ t("ai_workflow.embed_retry") }}
          </button>
        </div>
      </div>

      <footer class="embed-input">
        <el-input
          v-model="draft"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 5 }"
          resize="none"
          :disabled="isStreaming"
          :placeholder="t('ai_workflow.embed_inputPlaceholder')"
          class="embed-input__field"
          @keydown.enter.exact.prevent="onSend"
        />
        <el-button
          v-if="isStreaming"
          class="embed-input__btn"
          circle
          type="primary"
          :aria-label="t('ai_workflow.embed_stopGenerate')"
          @click="stop"
        >
          <el-icon><VideoPause /></el-icon>
        </el-button>
        <el-button
          v-else
          class="embed-input__btn"
          circle
          type="primary"
          :aria-label="t('ai_workflow.embed_send')"
          :disabled="!draft.trim()"
          @click="onSend"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import {
  ArrowDown,
  ArrowUp,
  Lock,
  Promotion,
  Timer,
  VideoPause,
  Warning,
} from "@element-plus/icons-vue";
import RichContent from "@/views/module_ai/chat/components/RichContent.vue";
import { useEmbedChat } from "@/composables/ai/useEmbedChat";

defineOptions({ name: "AiEmbedChat" });

const { t } = useI18n();

type Fatal = "" | "missing" | "expired" | "forbidden";

interface MetaData {
  appid: string;
  kind: "agent" | "app" | "workflow";
  target_id: number;
  name: string;
  welcome: string;
  expire_at: string;
}

const route = useRoute();
const apiBase = import.meta.env.VITE_APP_BASE_API || "/api/v1";

const token = ref(String(route.query.token || ""));
const primary = computed(() => {
  const p = String(route.query.primary || "");
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(p) ? p : "";
});
const themeStyle = computed(() =>
  primary.value ? ({ "--embed-primary": primary.value } as Record<string, string>) : {}
);

const fatal = ref<Fatal>(token.value ? "" : "missing");
const loading = ref(!!token.value);
const meta = ref<MetaData | null>(null);
const notice = ref("");
const noticeRetry = ref(false);
const draft = ref("");
const openSources = reactive<Record<number, boolean>>({});
const sourcesByOrdinal = reactive<Record<number, any[]>>({});
const scrollRef = ref<HTMLElement | null>(null);
const nearBottom = ref(true);
let errorEmitted = false;

/* ---------- 本地存储（sid + 转写，按 ticket/目标隔离） ---------- */
function storageKeys(m: MetaData) {
  // 归属维度用 appid（换票后 token 变化但 app 不变 → 续期后仍可恢复转写；跨 app 隔离）
  const scope = `ai-embed:${m.appid || token.value.slice(0, 6)}:${m.kind}:${m.target_id}`;
  return { sid: `${scope}:sid`, messages: `${scope}:messages` };
}
function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 隐私模式等场景忽略 */
  }
}
function removeKey(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

const sid = ref("");
const initialMessages = ref<any[]>([]);

/* ---------- postMessage 上行 ---------- */
function emit(event: string, payload: Record<string, unknown> = {}) {
  if (window.parent === window) return; // 独立打开时不做上行
  window.parent.postMessage({ source: "ai-embed", version: 1, event, payload }, "*");
}

/* ---------- 消息工具 ---------- */
function textOf(m: any): string {
  return (m?.parts || [])
    .filter((p: any) => p?.type === "text")
    .map((p: any) => String(p.text || ""))
    .join("");
}
function assistantOrdinal(index: number): number {
  let n = -1;
  for (let i = 0; i <= index; i++) if (messages.value[i]?.role !== "user") n++;
  return n;
}
function sourcesOf(index: number): any[] {
  return sourcesByOrdinal[assistantOrdinal(index)] || [];
}
function toggleSources(index: number) {
  const k = assistantOrdinal(index);
  openSources[k] = !openSources[k];
}
function sourceTitle(s: any): string {
  return String(s?.title || s?.file_name || s?.source || t("ai_workflow.embed_knowledgePiece"));
}

const initialChar = computed(() => (meta.value?.name || "AI").trim().charAt(0) || "AI");
const welcomeText = computed(() => meta.value?.welcome || t("ai_workflow.embed_welcome"));

/* ---------- 失败处理 ---------- */
function handleHttpError(status: number) {
  if (status === 401) {
    fatal.value = "expired";
    emit("token_expired");
    return;
  }
  if (status === 403) {
    fatal.value = "forbidden";
    emit("error", { reason: "no_permission", message: t("ai_workflow.embed_noPermMsg") });
    return;
  }
  if (status === 429) {
    notice.value = t("ai_workflow.embed_rateLimitedNotice");
    noticeRetry.value = false;
    emit("error", { reason: "rate_limited", message: t("ai_workflow.embed_rateLimitedMsg") });
    return;
  }
  if (status === 404) {
    notice.value = t("ai_workflow.embed_notFoundNotice");
    noticeRetry.value = false;
    emit("error", { reason: "not_found", message: t("ai_workflow.embed_notFoundMsg") });
    return;
  }
  notice.value = t("ai_workflow.embed_networkNotice");
  noticeRetry.value = true;
  emit("error", { reason: "network", message: t("ai_workflow.embed_networkMsg") });
}

/* ---------- 对话 ---------- */
const { messages, status, error, isStreaming, sendMessage, stop } = useEmbedChat({
  getToken: () => token.value,
  buildBody: () => ({ sid: sid.value }),
  id: computed(() => sid.value || undefined),
  initialMessages: computed(() => initialMessages.value),
  onHttpError: handleHttpError,
  onTextDelta: (delta) => emit("reply_delta", { sid: sid.value, text: delta }),
  onAuxFrame: (type, data: any) => {
    if (type === "sources" && Array.isArray(data?.sources)) {
      const ordinal = Math.max(0, messages.value.filter((m) => m.role !== "user").length - 1);
      sourcesByOrdinal[ordinal] = data.sources;
    } else if (type === "data-embed") {
      // 服务端会话已重置（闲置超 TTL）：清本地转写与引用，后续对话由服务端重建上下文
      if (data?.data?.session_reset && meta.value) {
        removeKey(storageKeys(meta.value).messages);
        Object.keys(sourcesByOrdinal).forEach((k) => delete sourcesByOrdinal[Number(k)]);
      }
    }
  },
});

const showTyping = computed(() => status.value === "submitted");
function isTypingTail(index: number): boolean {
  return (
    status.value === "streaming" &&
    index === messages.value.length - 1 &&
    messages.value[index]?.role !== "user"
  );
}
const disabled = computed(() => !sid.value || loading.value);

/* 状态跃迁 → postMessage */
watch(status, (next, prev) => {
  if (prev === "ready" && next === "submitted") {
    errorEmitted = false;
    emit("reply_start", { sid: sid.value });
    scrollToBottom();
  }
  if (next === "ready" && prev !== "ready") {
    const last = [...messages.value].reverse().find((m) => m.role !== "user");
    const text = last ? textOf(last) : "";
    if (text) {
      emit("reply_done", { sid: sid.value, text });
      persistTranscript();
    }
  }
});

watch(error, (e) => {
  if (!e || errorEmitted) return;
  errorEmitted = true;
  if (!fatal.value) {
    notice.value = e;
    noticeRetry.value = true;
    emit("error", { sid: sid.value, reason: "network", message: e });
  }
});

/* ---------- 发送 / 停止 ---------- */
function onSend() {
  const text = draft.value.trim();
  if (!text || isStreaming.value || disabled.value) return;
  emit("user_message", { sid: sid.value, message: text });
  draft.value = "";
  errorEmitted = false;
  notice.value = "";
  sendMessage({ text });
  scrollToBottom();
}

/* ---------- 滚动 ---------- */
function scrollToBottom() {
  const el = scrollRef.value;
  if (!el) return;
  requestAnimationFrame(() => {
    el.scrollTop = el.scrollHeight;
    nearBottom.value = true;
  });
}
function onScroll() {
  const el = scrollRef.value;
  if (!el) return;
  nearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}
watch(
  () => messages.value.map((m) => textOf(m)).join("|"),
  () => {
    if (nearBottom.value) scrollToBottom();
  }
);

/* ---------- 转写持久化（刷新恢复） ---------- */
function persistTranscript() {
  if (!meta.value) return;
  const plain = messages.value
    .filter((m) => textOf(m))
    .map((m) => ({ role: m.role, parts: [{ type: "text", text: textOf(m) }] }));
  writeJson(storageKeys(meta.value).messages, plain);
}

/* ---------- meta 初始化 ---------- */
async function fetchMeta(): Promise<void> {
  loading.value = true;
  try {
    const res = await fetch(`${apiBase}/ai/embed/meta`, {
      headers: { Authorization: `Bearer ${token.value}` },
    });
    if (!res.ok) {
      handleHttpError(res.status);
      return;
    }
    const body = await res.json();
    const data = (body?.data || {}) as MetaData;
    const changed =
      !meta.value || meta.value.kind !== data.kind || meta.value.target_id !== data.target_id;
    meta.value = data;
    fatal.value = "";
    notice.value = "";
    if (changed) {
      const keys = storageKeys(data);
      sid.value = localStorage.getItem(keys.sid) || "";
      const restored = readJson<any[]>(keys.messages, []);
      initialMessages.value = restored.map((m, i) => ({
        id: `restored-${i}`,
        role: m.role,
        parts: m.parts,
      }));
      if (!sid.value) {
        sid.value =
          (globalThis.crypto?.randomUUID?.() as string | undefined) ||
          `sid-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        writeJson(keys.sid, sid.value);
      }
    }
    emit("ready", {
      kind: data.kind,
      target_id: data.target_id,
      name: data.name,
      expire_at: data.expire_at,
    });
    scrollToBottom();
  } catch (e: any) {
    if (!fatal.value) {
      notice.value = t("ai_workflow.embed_metaLoadFail");
      noticeRetry.value = true;
      emit("error", { reason: "network", message: String(e?.message || e) });
    }
  } finally {
    loading.value = false;
  }
}
function retryMeta() {
  notice.value = "";
  fetchMeta();
}

/* ---------- 下行命令（宿主 → 嵌入页） ---------- */
async function applyToken(next: string) {
  if (!next || next === token.value) return;
  token.value = next;
  fatal.value = "";
  loading.value = true;
  // 换票后重新读取 meta：目标不变则延续会话；目标变化则重置本地状态
  await fetchMeta();
}
function onParentMessage(ev: MessageEvent) {
  if (ev.source !== window.parent) return;
  const data: any = ev.data;
  if (!data || data.source !== "ai-host" || data.version !== 1) return;
  const payload = data.payload || {};
  switch (data.command) {
    case "setToken":
      void applyToken(String(payload.token || ""));
      break;
    case "sendMessage":
      if (payload.text) {
        draft.value = String(payload.text);
        onSend();
      }
      break;
    case "resize":
    case "destroy":
      // 尺寸由宿主控制 iframe；destroy 由宿主直接移除 iframe，这里无需额外处理
      break;
    default:
      break;
  }
}

onMounted(() => {
  window.addEventListener("message", onParentMessage);
  if (token.value) void fetchMeta();
});
onBeforeUnmount(() => {
  window.removeEventListener("message", onParentMessage);
});
</script>

<style scoped lang="scss">
.embed-page {
  --embed-primary: var(--el-color-primary);
  box-sizing: border-box;
  height: 100vh;
  padding: 10px;
  font-family: inherit;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color-page);
}

.embed-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  box-shadow: 0 10px 30px rgb(0 0 0 / 8%);
}

.embed-header {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.embed-header__main {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.embed-header__dot {
  flex: none;
  width: 8px;
  height: 8px;
  background: var(--el-color-success);
  border-radius: 50%;
  box-shadow: 0 0 0 3px rgb(103 194 58 / 16%);
  transition: background 0.2s;

  &.is-busy {
    background: var(--embed-primary);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--embed-primary) 18%, transparent);
    animation: embed-pulse 1.2s ease-in-out infinite;
  }
}

.embed-header__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  white-space: nowrap;
}

.embed-header__brand {
  flex: none;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  letter-spacing: 0.02em;
}

.embed-skeleton-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.embed-messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  padding: 18px 16px 12px;
  overflow-y: auto;
  scroll-behavior: smooth;

  &--loading {
    gap: 12px;
  }
}

.embed-welcome {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 180px;
  text-align: center;
}

.embed-welcome__badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  font-size: 18px;
  font-weight: 600;
  color: var(--embed-primary);
  background: color-mix(in srgb, var(--embed-primary) 12%, transparent);
  border-radius: 14px;
}

.embed-welcome__text {
  max-width: 30em;
  margin: 0;
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.embed-welcome__hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.embed-msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  animation: embed-fade-in 0.16s ease-out;
}

.embed-msg__avatar {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: var(--el-color-success);
  border-radius: 6px;

  &.is-user {
    background: var(--embed-primary);
  }
}

.embed-msg__content {
  flex: 1;
  min-width: 0;
}

.embed-msg__sender {
  margin-bottom: 6px;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.embed-msg__body {
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-primary);
  overflow-wrap: anywhere;

  :deep(p) {
    margin: 0 0 6px;
  }

  :deep(p:last-child) {
    margin-bottom: 0;
  }

  :deep(pre) {
    padding: 8px 10px;
    overflow-x: auto;
    font-size: 12px;
    background: var(--el-fill-color-light);
    border-radius: 6px;
  }
}

.embed-msg__text {
  display: inline-block;
  padding: 10px 14px;
  white-space: pre-wrap;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
}

.embed-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background: currentcolor;
  animation: embed-blink 1s steps(2) infinite;
}

.embed-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 6px 2px;

  i {
    width: 6px;
    height: 6px;
    background: var(--el-text-color-placeholder);
    border-radius: 50%;
    animation: embed-typing 1.2s ease-in-out infinite;

    &:nth-child(2) {
      animation-delay: 0.15s;
    }

    &:nth-child(3) {
      animation-delay: 0.3s;
    }
  }
}

.embed-sources {
  margin: 6px 0 0;
}

.embed-sources__toggle {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: none;
  border: 0;

  &:hover {
    color: var(--embed-primary);
  }

  .el-icon {
    font-size: 12px;
  }
}

.embed-sources__list {
  padding: 0;
  margin: 6px 0 0;
  list-style: none;
}

.embed-sources__item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.embed-sources__title {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.embed-sources__score {
  flex: none;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-placeholder);
}

.embed-notice {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-7);
  border-radius: 8px;
}

.embed-notice__retry {
  flex: none;
  font-size: 12px;
  color: var(--embed-primary);
  cursor: pointer;
  background: none;
  border: 0;
}

.embed-input {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: flex-end;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.embed-input__field {
  flex: 1;

  :deep(.el-textarea__inner) {
    padding: 8px 10px;
    font-size: var(--el-font-size-base);
    line-height: 1.5;
    border-radius: 10px;
    box-shadow: 0 0 0 1px var(--el-border-color-lighter) inset;

    &:focus {
      box-shadow: 0 0 0 1px var(--embed-primary) inset;
    }
  }
}

.embed-input__btn {
  --el-button-bg-color: var(--embed-primary);
  --el-button-border-color: var(--embed-primary);
  --el-button-hover-bg-color: color-mix(in srgb, var(--embed-primary) 88%, #000);
  --el-button-hover-border-color: color-mix(in srgb, var(--embed-primary) 88%, #000);

  flex: none;
  width: 34px;
  height: 34px;
}

.embed-input--placeholder {
  align-items: center;
}

/* ---------- 整页状态（缺凭证/过期/无权限） ---------- */
.embed-state {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  text-align: center;
}

.embed-state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  font-size: 24px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-radius: 16px;

  &.is-warn {
    color: var(--el-color-warning);
    background: var(--el-color-warning-light-9);
  }
}

.embed-state__title {
  font-size: 16px;
  font-weight: 600;
}

.embed-state__desc {
  max-width: 26em;
  margin: 0;
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

/* ---------- 动效 ---------- */
@keyframes embed-typing {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@keyframes embed-fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes embed-blink {
  50% {
    opacity: 0;
  }
}

@keyframes embed-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.45;
  }
}

@media (prefers-reduced-motion: reduce) {
  .embed-typing i,
  .embed-caret,
  .embed-header__dot.is-busy,
  .embed-msg {
    animation: none;
  }

  .embed-messages {
    scroll-behavior: auto;
  }
}
</style>
