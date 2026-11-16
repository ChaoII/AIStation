<!-- 悬浮助手（agent-surface 版）：与旧 AiAssistant 并列存在，由 useSurfaceFlag 决定用哪个 -->
<template>
  <div>
    <div class="sa-fab" :class="{ 'is-open': open }" @click="open = !open">
      <el-icon v-if="!open"><ChatDotRound /></el-icon>
      <el-icon v-else><Close /></el-icon>
    </div>

    <el-drawer v-model="open" :size="560" :with-header="false" append-to-body class="sa-drawer">
      <div class="sa-body">
        <AgentSurface
          :transport="transport"
          :session-id="sessionId"
          :title="'AI 助手'"
          :subtitle="'Agno · 可回退到旧界面'"
          :theme="'light'"
          :palette="'paper'"
          :locale="'zh-CN'"
          :show-reasoning="true"
          :show-tool-calls="true"
          :presets="presets"
          @feedback="onFeedback"
          @error="onError"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { ChatDotRound, Close } from "@element-plus/icons-vue";
import { AgentSurface } from "agent-surface";
import "agent-surface/style.css";

import { AgnoSurfaceTransport } from "@/composables/ai/surface/agnoSurfaceTransport";

defineOptions({ name: "SurfaceAssistant" });

const open = ref(false);
const sessionId = ref<string>("");

/** agno 原生事件流（与旧 AiAssistant 同一端点，body 带上会话 id） */
const transport = new AgnoSurfaceTransport({
  path: "/ai/assistant/stream",
  buildBody: () => (sessionId.value ? { session_id: sessionId.value } : {}),
});

const presets = [
  { label: "今天有哪些告警", prompt: "今天有哪些告警？" },
  { label: "系统里有多少用户", prompt: "系统里一共有多少个用户？" },
];

function onFeedback(p: { messageId: string; value: "up" | "down" | "" }) {
  try {
    localStorage.setItem(`ws_msg_like_${p.messageId}`, p.value === "up" ? "1" : "0");
  } catch {
    /* 忽略 */
  }
  if (p.value) ElMessage.success("已记录反馈");
}

function onError(msg: string) {
  ElMessage.error(msg || "对话出错");
}
</script>

<style lang="scss">
.sa-fab {
  position: fixed;
  right: 28px;
  bottom: 96px;
  z-index: 2000;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-color-primary);
  color: #fff;
  cursor: pointer;
  box-shadow: var(--el-box-shadow-light);
  font-size: 20px;
}
.sa-fab.is-open {
  background: var(--el-text-color-secondary);
}
.sa-drawer .el-drawer__body {
  padding: 0;
}
.sa-body {
  height: 100%;
  min-height: 0;
}
</style>
