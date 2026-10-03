<!-- AI 运行台：选择组件/知识库 → 输入问题 → 流式运行预览 -->
<template>
  <div class="app-container ai-playground-page">
    <el-row :gutter="12">
      <el-col :md="8">
        <el-card shadow="never" class="pg-left">
          <template #header>运行对象</template>
          <el-form label-position="top" size="small">
            <el-form-item label="组件类型">
              <el-select v-model="runType" style="width: 100%">
                <el-option label="组件（应用/智能体/工作流/知识库）" value="app" />
                <el-option label="知识库问答" value="kb" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="runType === 'app'" label="选择组件">
              <el-select v-model="appId" filterable placeholder="选择组件" style="width: 100%">
                <el-option
                  v-for="a in apps"
                  :key="a.id"
                  :label="`${a.name}（${typeLabel(a.app_type)}）`"
                  :value="a.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-else label="选择知识库">
              <el-select v-model="kbId" filterable placeholder="选择知识库" style="width: 100%">
                <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="问题">
              <el-input
                v-model="query"
                type="textarea"
                :rows="4"
                placeholder="输入测试问题，Ctrl+Enter 发送"
                @keydown.ctrl.enter="run"
              />
            </el-form-item>
            <el-button type="primary" :loading="running" :disabled="!canRun" @click="run">
              运行
            </el-button>
            <el-button :disabled="!running" @click="stop">停止</el-button>
          </el-form>
        </el-card>
      </el-col>
      <el-col :md="16">
        <el-card shadow="never" class="pg-right">
          <template #header>输出</template>
          <div ref="outputRef" v-loading="running" class="pg-output">
            <template v-if="answer">
              <div class="pg-answer" v-html="render(answer)"></div>
            </template>
            <el-empty v-else description="选择运行对象并输入问题开始" :image-size="60" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import MarkdownIt from "markdown-it";
import { getAiAppList } from "@/api/module_ai/app";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { Auth } from "@/utils/auth";

defineOptions({ name: "AiPlayground" });

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
function render(text: string) {
  return md.render(text || "");
}
function typeLabel(t: string) {
  return { chat: "聊天", agent: "智能体", workflow: "工作流", kb: "知识库" }[t] || t;
}

const apps = ref<any[]>([]);
const kbs = ref<any[]>([]);
const runType = ref("app");
const appId = ref<number | null>(null);
const kbId = ref<number | null>(null);
const query = ref("");
const answer = ref("");
const running = ref(false);
const outputRef = ref<HTMLElement>();
let controller: AbortController | null = null;

const canRun = computed(() => {
  if (!query.value.trim()) return false;
  return runType.value === "app" ? !!appId.value : !!kbId.value;
});

async function loadOptions() {
  try {
    const [a, k] = await Promise.all([getAiAppList(), getAiKnowledgeList()]);
    apps.value = a.data?.data || [];
    kbs.value = k.data?.data || [];
  } catch {
    /* 忽略 */
  }
}

async function run() {
  if (!canRun.value) return;
  running.value = true;
  answer.value = "";
  controller = new AbortController();
  let url = "";
  let body: any = {};
  if (runType.value === "app") {
    url = `/api/v1/ai/apps/${appId.value}/run/stream`;
    body = { messages: [{ role: "user", content: query.value }] };
  } else {
    url = `/api/v1/ai/knowledge/bases/${kbId.value}/ask`;
    body = { query: query.value, top_k: 6 };
  }
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken()}`,
      },
      signal: controller.signal,
      body: JSON.stringify(body),
    });
    if (!resp.ok || !resp.body) throw new Error("请求失败");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    // 知识库 ask 为一次性 JSON（非 SSE），按 JSON 处理
    const ct = resp.headers.get("content-type") || "";
    if (!ct.includes("text/event-stream")) {
      const text = await resp.text();
      try {
        const j = JSON.parse(text);
        answer.value = j?.data?.answer || "";
      } catch {
        answer.value = text;
      }
      scrollBottom();
      return;
    }
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        const s = line.trim();
        if (!s.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(s.slice(6));
          if (evt.type === "text-delta") answer.value += evt.delta || "";
          else if (evt.type === "text") answer.value += evt.text || "";
          else if (evt.type === "error")
            answer.value += `\n[错误] ${evt.error || evt.message || ""}`;
          else if (evt.type === "finish" && evt.payload?.reply) answer.value += evt.payload.reply;
        } catch {
          /* 忽略非 JSON */
        }
      }
    }
    scrollBottom();
  } catch (e: any) {
    if ((e as any)?.name !== "AbortError") {
      answer.value = `运行失败：${e?.message || e}`;
    }
  } finally {
    running.value = false;
    controller = null;
  }
}

function stop() {
  controller?.abort();
  running.value = false;
}

async function scrollBottom() {
  await nextTick();
  if (outputRef.value) outputRef.value.scrollTop = outputRef.value.scrollHeight;
}

onMounted(loadOptions);
</script>

<style scoped>
.ai-playground-page {
  padding: 12px;
}
.pg-left,
.pg-right {
  margin-bottom: 12px;
}
.pg-output {
  min-height: 60vh;
  max-height: 72vh;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.pg-answer {
  line-height: 1.8;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  word-break: break-word;
}
.pg-answer :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 6px;
  overflow: auto;
}
.pg-answer :deep(code) {
  font-family: var(--el-font-family-mono, monospace);
}
.pg-answer :deep(h1),
.pg-answer :deep(h2),
.pg-answer :deep(h3) {
  margin: 0.5em 0;
}
</style>
