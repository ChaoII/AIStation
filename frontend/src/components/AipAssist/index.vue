<template>
  <div class="aip-assist">
    <!-- 浮层按钮 -->
    <el-button
      v-if="!visible"
      class="aip-assist__fab"
      type="primary"
      circle
      size="large"
      @click="visible = true"
      title="AIP Assist 全局助手"
    >
      <el-icon><MagicStick /></el-icon>
    </el-button>

    <transition name="el-fade-in">
      <div v-if="visible" class="aip-assist__panel">
        <div class="aip-assist__header">
          <div class="aip-assist__title">
            <el-icon><MagicStick /></el-icon>
            <span>AIP Assist</span>
            <el-tag size="small" type="info" effect="plain">全局助手</el-tag>
          </div>
          <el-button link :icon="Close" @click="close" />
        </div>
        <div ref="bodyRef" class="aip-assist__body">
          <div v-if="!messages.length" class="aip-assist__welcome">
            <div class="aip-assist__welcome-title">你好，我是 AIP 助手</div>
            <div class="aip-assist__welcome-sub">可跨页面解答系统问题，点击下方示例试试</div>
            <el-tag
              v-for="s in suggestions"
              :key="s"
              class="aip-assist__sug"
              size="small"
              effect="plain"
              @click="send(s)"
            >
              {{ s }}
            </el-tag>
          </div>
          <div v-for="(m, i) in messages" :key="i" class="aip-assist__msg" :class="m.role">
            <div v-if="m.role === 'user'" class="aip-assist__bubble user">{{ m.text }}</div>
            <div v-else class="aip-assist__bubble bot">
              <div v-if="m.loading" class="aip-assist__loading">正在思考…</div>
              <template v-else>
                <div class="aip-assist__reply">{{ m.text }}</div>
                <div v-if="m.sources?.length" class="aip-assist__sources">
                  <div class="aip-assist__sources-label">参考来源</div>
                  <div v-for="(s, si) in m.sources" :key="si" class="aip-assist__source">
                    <b>{{ s.title }}</b><span>{{ s.content }}</span>
                  </div>
                </div>
                <div v-if="m.toolCalls?.length" class="aip-assist__tools">
                  <el-tag
                    v-for="t in m.toolCalls"
                    :key="t.name"
                    size="small"
                    type="primary"
                    effect="plain"
                    class="aip-assist__tool-tag"
                  >
                    {{
                      t.result === null || t.result === undefined
                        ? `调用 ${t.name}`
                        : `✔ ${t.name}`
                    }}
                  </el-tag>
                </div>
                <div v-if="m.action" class="aip-assist__action">
                  <el-button size="small" type="primary" @click="runAction(m.action)">{{ m.action.label || "执行" }}</el-button>
                </div>
              </template>
            </div>
          </div>
        </div>
        <div class="aip-assist__input">
          <el-input
            v-model="input"
            placeholder="输入问题…"
            :disabled="loading"
            @keyup.enter="send(input)"
          />
          <el-button type="primary" :loading="loading" :disabled="!input.trim()" @click="send(input)">
            发送
          </el-button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from "vue";
import { Close, MagicStick } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { assistantChat } from "@/api/module_ai/assistant";
import router from "@/router";

const visible = ref(false);
const input = ref("");
const loading = ref(false);
const bodyRef = ref<HTMLElement | null>(null);
const messages = ref<any[]>([]);
const suggestions = ["本系统有多少表？", "AI 能力如何评估？", "有哪些敏感字段？"];

function close() {
  visible.value = false;
}

async function scrollBottom() {
  await nextTick();
  bodyRef.value?.scrollTo({ top: bodyRef.value.scrollHeight });
}

async function send(text: string) {
  const t = (text || "").trim();
  if (!t || loading.value) return;
  input.value = "";
  messages.value.push({ role: "user", text: t });
  const bot: any = { role: "assistant", text: "", loading: true };
  messages.value.push(bot);
  loading.value = true;
  scrollBottom();
  try {
    const r = await assistantChat(t);
    bot.loading = false;
    bot.text = r.data?.data?.reply || "(无回复)";
    bot.toolCalls = r.data?.data?.tool_calls || [];
    bot.action = r.data?.data?.action || null;
    bot.sources = r.data?.data?.sources || [];
  } catch (e: any) {
    bot.loading = false;
    bot.text = e?.msg || "请求失败，请重试";
  } finally {
    loading.value = false;
    scrollBottom();
  }
}

function runAction(action: any) {
  if (action.type === "navigate" && action.path) {
    router.push(action.path);
    close();
  } else if (action.type === "confirm") {
    ElMessage.info(action.reason || "请按提示在对应页面确认操作");
  } else if (action.api) {
    ElMessage.info("该动作为写操作，请在审批流中确认");
  }
}
</script>

<style lang="scss" scoped>
.aip-assist {
  position: fixed;
  right: 24px;
  bottom: 88px;
  z-index: 3000;
}
.aip-assist__fab {
  width: 52px;
  height: 52px;
  box-shadow: var(--el-box-shadow-light);
}
.aip-assist__panel {
  position: fixed;
  right: 24px;
  bottom: 88px;
  width: 360px;
  max-height: 540px;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  box-shadow: var(--el-box-shadow);
  overflow: hidden;
}
.aip-assist__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.aip-assist__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.aip-assist__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 120px;
}
.aip-assist__welcome {
  text-align: center;
  padding: 16px 8px;
}
.aip-assist__welcome-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}
.aip-assist__welcome-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.aip-assist__sug {
  margin: 0 3px 6px 0;
  cursor: pointer;
}
.aip-assist__msg {
  margin-bottom: 10px;
}
.aip-assist__bubble {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: var(--el-font-size-base);
  word-break: break-word;
}
.aip-assist__bubble.user {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  margin-left: auto;
  width: fit-content;
  max-width: 85%;
}
.aip-assist__bubble.bot {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  max-width: 100%;
}
.aip-assist__loading {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.aip-assist__sources {
  margin-top: 8px;
  font-size: 12px;
}
.aip-assist__sources-label {
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.aip-assist__source {
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
}
.aip-assist__source b {
  display: block;
  color: var(--el-text-color-primary);
}
.aip-assist__tools {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.aip-assist__action {
  margin-top: 8px;
}
.aip-assist__input {
  display: flex;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
