<template>
  <div class="app-container">
    <el-row :gutter="16">
      <el-col :xs="24" :md="16">
        <el-card shadow="never">
          <template #header>
            <div class="pg-head">
              <span>对话</span>
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from "vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import { useAiChat } from "@/composables/ai/useAiChat";
import { textOf, type AiUIPart } from "@/composables/ai/uiMessage";

const md = new MarkdownIt({ breaks: true, linkify: true });

const { messages, status, error, sendMessage, stop } = useAiChat();

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

watch(
  () => messages.value.length,
  async () => {
    await nextTick();
    scrollRef.value?.setScrollTop(999999);
  }
);
</script>

<style scoped lang="scss">
.pg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
</style>
