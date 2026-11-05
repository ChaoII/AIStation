<!--
  CodeBlock：只读代码块（语法高亮 + 一键复制）。

  为什么不用 <pre>：问数的 SQL 是长单行（100+ 字符），纯文本既没有高亮也没有
  换行提示，看着像一大段糊在一起的文字。这里用项目已有的 highlight.js，
  只注册 sql，避免把整包语言带进首屏。
-->
<template>
  <div class="code-block">
    <div class="code-block__head">
      <span class="code-block__lang">{{ language.toUpperCase() }}</span>
      <span class="code-block__lines">{{ lineCount }} 行</span>
      <el-button
        class="code-block__copy"
        link
        size="small"
        :icon="copied ? 'Select' : 'CopyDocument'"
        @click="copy"
      >
        {{ copied ? "已复制" : "复制" }}
      </el-button>
    </div>
    <pre class="code-block__body"><code v-html="highlighted" /></pre>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import hljs from "highlight.js/lib/core";
import sqlLang from "highlight.js/lib/languages/sql";

hljs.registerLanguage("sql", sqlLang);
hljs.registerLanguage("postgresql", sqlLang);

const props = withDefaults(defineProps<{ code: string; language?: string }>(), { language: "sql" });

const copied = ref(false);

const lineCount = computed(() => (props.code || "").split("\n").length);

const highlighted = computed(() => {
  const code = props.code || "";
  if (!code) return "";
  try {
    return hljs.highlight(code, { language: props.language }).value;
  } catch {
    return escapeHtml(code);
  }
});

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function copy() {
  try {
    await navigator.clipboard.writeText(props.code || "");
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    ElMessage.warning("复制失败，请手动选择");
  }
}
</script>

<style lang="scss">
.code-block {
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-lighter);
}

.code-block__head {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 8px 4px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.code-block__lang {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.code-block__lines {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.code-block__copy {
  margin-left: auto;
}

.code-block__body {
  max-height: 220px;
  margin: 0;
  padding: 10px 12px;
  overflow: auto;
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* highlight.js sql 配色（用主题变量，跟随明暗） */
.code-block__body .hljs-keyword,
.code-block__body .hljs-built_in {
  color: var(--el-color-primary);
}

.code-block__body .hljs-string {
  color: var(--el-color-success);
}

.code-block__body .hljs-number {
  color: var(--el-color-warning);
}

.code-block__body .hljs-comment {
  color: var(--el-text-color-placeholder);
}
</style>
