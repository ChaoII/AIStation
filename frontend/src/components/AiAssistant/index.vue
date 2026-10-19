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
      width="900px"
      :close-on-click-modal="false"
      draggable
      class="ai-assistant-dialog"
    >
      <template #header>
        <div class="dialog-header">
          <el-button
            text
            size="small"
            :icon="Menu"
            class="session-toggle"
            :class="{ active: sessionPanelOpen }"
            @click="sessionPanelOpen = !sessionPanelOpen"
          />
          <div class="i-svg:ai header-icon" />
          <span class="title">AI 智能助手</span>
        </div>
      </template>

      <div class="dialog-body">
        <SessionSidebar
          v-if="sessionPanelOpen"
          class="session-panel"
          :sessions="sessions"
          :active-id="currentSessionId"
          @select="handleSelectSession"
          @create="handleCreateSession"
          @rename="handleRenameSession"
          @remove="handleRemoveSession"
        />
        <div class="chat-area">
          <div class="assistant-chat">
            <ChatMessages
              :messages="displayMessages"
              :error="errorText"
              :is-streaming="isSending"
              @prompt-click="handleSend"
              @error-close="errorText = ''"
            />
          </div>
          <div class="assistant-input">
            <ChatInput :sending="isSending" @send="handleSend" @stop="handleStop" />
          </div>
        </div>
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
import { useAiChat, type AiChatFilePayload } from "@/composables/ai/useAiChat";
import { isToolPart } from "@/composables/ai/uiMessage";
import { Menu } from "@element-plus/icons-vue";
import {
  getAiSessionList,
  getAiSessionDetail,
  createAiSession,
  renameAiSession,
  deleteAiSessions,
  type AiSessionItem,
} from "@/api/module_ai/session";
import { AnnotationAPI } from "@/api/module_annotation";
// 本体动作执行（Agent 动作提议的确认落点）。修前 AiAssistant 不认识
// api === "ontologyAction"，用户点「确认」后什么也不会发生。
import { executeOntAction } from "@/api/module_ai/ontology";
import ChatMessages from "@/views/module_ai/chat/components/ChatMessages.vue";
import ChatInput from "@/views/module_ai/chat/components/ChatInput.vue";
import SessionSidebar from "@/views/module_ai/chat/components/SessionSidebar.vue";
import type { UploadedFile } from "@/views/module_ai/chat/types";

const router = useRouter();
const settingsStore = useSettingsStore();

// 状态
const dialogVisible = ref(false);
const errorText = ref("");

// Agno 原生事件流助手（默认 /ai/assistant/stream）；会话统一走 /sessions
const currentSessionId = ref<number | null>(null);
const sessions = ref<AiSessionItem[]>([]);
const sessionMessages = ref<any[]>([]);
const sessionPanelOpen = ref(true);

const chat = useAiChat(() => ({
  id: currentSessionId,
  initialMessages: sessionMessages,
  body: () => (currentSessionId.value != null ? { session_id: currentSessionId.value } : {}),
}));

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

// 直接渲染 useChat 的 SDK UIMessage（按 parts 渲染，含文本/思维/工具/来源）
const displayMessages = chat.messages;

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
    } else if (action.api === "ontologyAction") {
      // 本体动作（后端 agent_tools.propose_ontology_action 的确认载荷）。
      // 修前这里没有分支 ⇒ 用户点「确认」后什么也不会发生（后端能力吃灰）。
      // 动作必须知道**改哪一行**，而 Agent 提议时并不知道 ⇒ 让人工填目标行主键。
      const payload = action.payload || {};
      const obj = await ElMessageBox.prompt(
        `动作「${payload.code}」将写回本体对象表，请填目标行的主键（如 id）。`,
        "确认执行本体动作",
        {
          inputPattern: /\S/,
          inputErrorMessage: "目标行主键不能为空",
          type: "warning",
        }
      );
      const r = await executeOntAction({
        code: payload.code,
        object_key: String(obj.value).trim(),
        params: payload.args || {},
      });
      const d = r.data?.data || {};
      if (d.needs_approval) {
        ElMessage.warning(d.msg || "已生成待审批单，需管理员批准后执行");
      } else if (d.ok === false) {
        ElMessage.error(d.msg || "本体动作执行失败");
      } else {
        ElMessage.success(d.msg || "本体动作已执行");
      }
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
};

// 从工具输出里提取 __action__ / __report_id__（v2 由 tool part 承载，不再有 data-finish）
const extractMeta = (output: unknown): { action?: unknown; reportId?: unknown } => {
  let obj: any = output;
  if (typeof output === "string") {
    try {
      obj = JSON.parse(output);
    } catch {
      return {};
    }
  }
  if (obj && typeof obj === "object") {
    return { action: obj["__action__"], reportId: obj["__report_id__"] };
  }
  return {};
};

// 读取本轮助手消息的工具结果，执行其携带的动作（导航/确认/报告提示）
const handleAssistantAction = async () => {
  const list = chat.messages.value;
  const last: any = list[list.length - 1];
  if (!last) return;
  let action: any;
  let reportId: any;
  for (const p of last.parts || []) {
    if (isToolPart(p) && p.output != null) {
      const meta = extractMeta(p.output);
      if (meta.action) action = meta.action;
      if (meta.reportId != null) reportId = meta.reportId;
    }
  }
  if (reportId != null) {
    ElMessage.success(`已生成报告 #${reportId}，可在「AI 管理 → AI 报告」查看`);
  }
  if (!action) return;
  if (action.type === "navigate" && action.path) {
    router.push(action.path);
    handleClose();
  } else if (action.type === "confirm") {
    await confirmAssistantAction(action);
  }
};

// 文件 → data URL
const readAsDataUrl = (file: File) =>
  new Promise<string>((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => resolve("");
    r.readAsDataURL(file);
  });

const toFilePayload = async (files?: UploadedFile[]): Promise<AiChatFilePayload[]> => {
  const out: AiChatFilePayload[] = [];
  for (const f of files || []) {
    if (!f.file) continue;
    const dataUrl = await readAsDataUrl(f.file);
    if (!dataUrl) continue;
    out.push({ name: f.name, type: f.type, dataUrl });
  }
  return out;
};

// 发送消息（会话统一走 /sessions：首条消息时创建会话）
const handleSend = async (message: string, files?: UploadedFile[]) => {
  const text = (message || "").trim();
  if ((!text && (!files || files.length === 0)) || isSending.value) return;
  errorText.value = "";

  if (currentSessionId.value == null) {
    try {
      const res = await createAiSession({ title: (text || "附件消息").slice(0, 20) });
      const created = res.data?.data;
      if (created?.id != null) {
        currentSessionId.value = created.id;
        await loadSessions();
      }
    } catch {
      // 创建会话失败不阻断对话（后端以无会话继续）
    }
  }

  const payload = await toFilePayload(files);
  await chat.sendMessage({ text, files: payload.length ? payload : undefined });
  await handleAssistantAction();
};

const handleStop = () => {
  chat.stop();
};

// 把后端会话消息（parts 为 {type,text}）转成 SDK UIMessage
const toUIMessages = (msgs: any[]) =>
  (msgs || []).map((m: any) => ({
    id: `sess-${m.id}`,
    role: m.role === "user" ? "user" : "assistant",
    parts: (m.parts || [])
      .filter((p: any) => p.type === "text" && p.text)
      .map((p: any) => ({ type: "text", text: String(p.text) })),
  }));

const loadSessions = async () => {
  try {
    const res = await getAiSessionList();
    sessions.value = res.data?.data || [];
  } catch {
    sessions.value = [];
  }
};

const handleSelectSession = async (id: number) => {
  if (id === currentSessionId.value) return;
  try {
    const res = await getAiSessionDetail(id);
    const detail = res.data?.data;
    sessionMessages.value = toUIMessages(detail?.messages || []);
    currentSessionId.value = id;
    errorText.value = "";
  } catch {
    ElMessage.error("加载会话失败");
  }
};

const handleCreateSession = async () => {
  try {
    const res = await createAiSession({ title: "新对话" });
    const created = res.data?.data;
    if (created?.id != null) {
      sessionMessages.value = [];
      currentSessionId.value = created.id;
      await loadSessions();
    }
  } catch {
    ElMessage.error("创建会话失败");
  }
};

const handleRenameSession = async (id: number, title: string) => {
  try {
    await renameAiSession(id, title);
    await loadSessions();
  } catch {
    ElMessage.error("重命名失败");
  }
};

const handleRemoveSession = async (id: number) => {
  try {
    await deleteAiSessions([id]);
    if (id === currentSessionId.value) {
      currentSessionId.value = null;
      sessionMessages.value = [];
    }
    await loadSessions();
  } catch {
    ElMessage.error("删除失败");
  }
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
  loadSessions();
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
    gap: 10px;
    align-items: center;

    .session-toggle {
      color: var(--el-text-color-secondary);

      &.active {
        color: var(--el-color-primary);
      }
    }

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

  .dialog-body {
    display: flex;
    gap: 12px;
    height: 460px;

    .session-panel {
      flex-shrink: 0;
      width: 220px;
      height: 100%;
    }

    .chat-area {
      display: flex;
      flex: 1;
      min-width: 0;
      flex-direction: column;

      /* 与「AI 聊天」页一致的聊天区（共享 ChatMessages/ChatInput 组件） */
      .assistant-chat {
        flex: 1;
        min-height: 0;
        overflow: hidden;
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 8px;
      }

      .assistant-input {
        margin-top: 8px;
      }
    }
  }
}
</style>
