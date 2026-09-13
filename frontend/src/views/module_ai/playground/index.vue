<template>
  <div class="app-container ai-console">
    <div class="ai-head">
      <div>
        <div class="ai-eyebrow">AI · Playground</div>
        <h1>运行台</h1>
        <div class="ai-sub">流式试运行：问数、统计、报告、导航，工具调用过程实时可见</div>
      </div>
      <div class="ai-signal">
        <span class="dot" :class="running ? '' : 'on'" />
        {{ running ? "生成中…" : "就绪" }}
      </div>
    </div>

    <div class="ai-run">
      <div class="ai-panel ai-stream">
        <div class="ai-stream-list" ref="listRef">
          <div v-if="!messages.length" class="ai-empty">
            试试：“我们有几个数据集？共多少张图？” / “生成一份训练与告警总结报告” / “打开模型仓库页”
          </div>
          <div v-for="(m, i) in messages" :key="i" class="ai-msg" :class="m.role">
            <div class="av">{{ m.role === "user" ? "U" : "AI" }}</div>
            <div class="bd" v-html="render(m.text)"></div>
          </div>
        </div>
        <div class="ai-compose">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="向系统提问或下达指令…（Enter 发送，Shift+Enter 换行）"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" :loading="running" :disabled="!input.trim()" @click="send">
            发送
          </el-button>
        </div>
      </div>

      <div class="ai-panel">
        <div class="ai-panel-hd"><span>工具时间线</span></div>
        <div class="ai-timeline">
          <div v-if="!steps.length" class="ai-empty">暂无工具调用</div>
          <div v-for="(s, i) in steps" :key="i" class="ai-step">
            <div class="nm">{{ s.name }}</div>
            <div class="rs">{{ s.summary }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from "vue";
import MarkdownIt from "markdown-it";
import { assistantStream } from "@/api/module_ai/assistant";

const md = new MarkdownIt({ breaks: true, linkify: true });

const input = ref("");
const running = ref(false);
const messages = ref<Array<{ role: "user" | "assistant"; text: string }>>([]);
const steps = ref<Array<{ name: string; summary: string }>>([]);
const listRef = ref<HTMLElement | null>(null);

function render(text: string): string {
  return md.render(text || "");
}

async function scrollBottom() {
  await nextTick();
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text || running.value) return;
  input.value = "";
  messages.value.push({ role: "user", text });
  messages.value.push({ role: "assistant", text: "" });
  const assistant = messages.value[messages.value.length - 1];
  running.value = true;
  steps.value = [];
  await scrollBottom();

  try {
    await assistantStream(text, (event, data) => {
      if (event === "delta") {
        assistant.text += data.text || "";
      } else if (event === "tool") {
        steps.value.push({ name: data.name, summary: summarize(data.result) });
      } else if (event === "done") {
        if (data.reply) assistant.text = data.reply;
      } else if (event === "error") {
        assistant.text += `\n\n> 出错：${data.message}`;
      }
      scrollBottom();
    });
  } catch (e: any) {
    assistant.text += `\n\n> 请求失败：${e?.message || e}`;
  } finally {
    running.value = false;
    scrollBottom();
  }
}

function summarize(result: any): string {
  if (result == null) return "—";
  if (typeof result === "string") return result.slice(0, 160);
  if (Array.isArray(result)) return `返回 ${result.length} 条`;
  if (result.error) return `错误：${result.error}`;
  const keys = Object.keys(result);
  return keys.slice(0, 6).join(", ");
}
</script>
