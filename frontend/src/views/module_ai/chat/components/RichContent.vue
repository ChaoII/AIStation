<template>
  <div ref="rootRef" class="rich-content" @click="handleClick" v-html="html"></div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import MarkdownIt from "markdown-it";
import markdownItHighlightjs from "markdown-it-highlightjs";
import hljs from "highlight.js";
import DOMPurify from "dompurify";
import "highlight.js/styles/atom-one-light.css";

interface Props {
  content: string;
}

const props = defineProps<Props>();

const { t } = useI18n();

const md: MarkdownIt = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`;
      } catch {
        return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
  },
}).use(markdownItHighlightjs);

const defaultRender =
  md.renderer.rules.link_open ||
  function (tokens: any[], idx: number, options: any, env: any, self: any) {
    return self.renderToken(tokens, idx, options, env, self);
  };

md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  tokens[idx].attrPush(["target", "_blank"]);
  tokens[idx].attrPush(["rel", "noopener noreferrer"]);
  return defaultRender(tokens, idx, options, env, self);
};

const html = computed(() => {
  if (!props.content) return "";
  // 归一换行 + 去掉首尾空白，避免渲染出空白 <p>/多余空行
  const normalized = props.content.replace(/\r\n/g, "\n").trim();
  const rawHtml = md.render(normalized);
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      "a",
      "abbr",
      "acronym",
      "b",
      "blockquote",
      "br",
      "code",
      "col",
      "colgroup",
      "dd",
      "del",
      "dl",
      "dt",
      "em",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "hr",
      "i",
      "img",
      "li",
      "ol",
      "p",
      "pre",
      "s",
      "span",
      "strike",
      "strong",
      "sub",
      "sup",
      "table",
      "tbody",
      "td",
      "tfoot",
      "th",
      "thead",
      "tr",
      "tt",
      "u",
      "ul",
      "video",
      "source",
      "div",
    ],
    ALLOWED_ATTR: [
      "href",
      "title",
      "target",
      "rel",
      "src",
      "alt",
      "width",
      "height",
      "class",
      "id",
      "controls",
      "poster",
      "type",
      "colspan",
      "rowspan",
      "span",
    ],
  });
});

const rootRef = ref<HTMLElement | null>(null);

/** 从 code 的 class 提取语言（markdown-it-highlightjs 会加 `language-xxx`）。 */
function langOf(code: HTMLElement): string {
  const m = (code.className || "").match(/language-([\w-]+)/i);
  return m ? m[1] : "text";
}

/** 为每个代码块注入语言标签与「复制」按钮（v-html 后处理，避免 v-html 内嵌事件）。 */
function decorateCode(): void {
  const root = rootRef.value;
  if (!root) return;
  root.querySelectorAll<HTMLElement>("pre").forEach((pre) => {
    if (pre.parentElement?.classList.contains("code-block")) return;
    const code = pre.querySelector("code");
    const lang = code ? langOf(code) : "text";

    const wrap = document.createElement("div");
    wrap.className = "code-block";

    const header = document.createElement("div");
    header.className = "code-header";
    const langTag = document.createElement("span");
    langTag.className = "code-lang";
    langTag.textContent = lang;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "code-copy";
    btn.textContent = t("ai_chat.richContent_copy");
    header.appendChild(langTag);
    header.appendChild(btn);

    pre.parentNode?.insertBefore(wrap, pre);
    wrap.appendChild(header);
    wrap.appendChild(pre);
  });
}

watch(
  () => props.content,
  async () => {
    await nextTick();
    decorateCode();
  },
  { immediate: true }
);

const handleClick = async (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  const btn = target.closest(".code-copy") as HTMLElement | null;
  if (!btn) return;
  const block = btn.closest(".code-block");
  const code = block?.querySelector("code");
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code.textContent || "");
    ElMessage.success(t("ai_chat.richContent_codeCopied"));
  } catch {
    const textArea = document.createElement("textarea");
    textArea.value = code.textContent || "";
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
    ElMessage.success(t("ai_chat.richContent_codeCopied"));
  }
};
</script>

<style lang="scss" scoped>
.rich-content {
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-primary);
  word-wrap: break-word;

  :deep(h1) {
    font-size: 1.4em;
  }

  :deep(h2) {
    font-size: 1.25em;
  }

  :deep(h3) {
    font-size: 1.1em;
  }

  :deep(h4),
  :deep(h5),
  :deep(h6) {
    font-size: 1em;
  }

  :deep(h1),
  :deep(h2),
  :deep(h3),
  :deep(h4),
  :deep(h5),
  :deep(h6) {
    margin: 0 0 10px;
    font-weight: 600;
    line-height: 1.4;
  }

  :deep(p) {
    margin: 0 0 10px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 24px;
    margin: 0 0 10px;
  }

  :deep(li) {
    margin: 2px 0;
    line-height: 1.7;
  }

  :deep(a) {
    color: var(--el-color-primary);
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }

  :deep(blockquote) {
    padding: 8px 16px;
    margin: 12px 0;
    background: var(--el-fill-color-light);
    border-left: 4px solid var(--el-color-primary);
  }

  :deep(table) {
    width: 100%;
    margin: 12px 0;
    border-collapse: collapse;

    th,
    td {
      padding: 8px 12px;
      border: 1px solid var(--el-border-color-light);
    }

    th {
      font-weight: 600;
      background: var(--el-fill-color-light);
    }
  }

  :deep(img) {
    max-width: 100%;
    border-radius: 6px;
  }

  :deep(.code-block) {
    margin: 12px 0;
    overflow: hidden;
    background: var(--el-fill-color-light);
    border-radius: 6px;

    .code-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      border-bottom: 1px solid var(--el-border-color-lighter);

      .code-lang {
        font-size: var(--el-font-size-small);
        color: var(--el-text-color-secondary);
      }

      .code-copy {
        font-size: var(--el-font-size-small);
        color: var(--el-text-color-secondary);
        cursor: pointer;
        background: transparent;
        border: none;

        &:hover {
          color: var(--el-color-primary);
        }
      }
    }

    pre {
      margin: 0;
      overflow-x: auto;

      code {
        font-family: "Courier New", Courier, monospace;
        font-size: var(--el-font-size-small);
      }
    }
  }

  :deep(code:not(pre code)) {
    padding: 2px 6px;
    font-family: "Courier New", Courier, monospace;
    font-size: var(--el-font-size-small);
    background: var(--el-fill-color-light);
    border-radius: 3px;
  }
}
</style>

<!-- 暗色下覆盖 highlight.js 亮色主题，避免代码块发白底 -->
<style lang="scss">
.rich-content {
  pre.hljs,
  code.hljs {
    color: var(--el-text-color-regular) !important;
    background: var(--el-fill-color-light) !important;
  }

  .hljs-comment,
  .hljs-quote {
    color: var(--el-text-color-secondary) !important;
  }

  .hljs-keyword,
  .hljs-selector-tag,
  .hljs-built_in {
    color: var(--el-color-primary) !important;
  }

  .hljs-string,
  .hljs-title,
  .hljs-attr {
    color: var(--el-color-success) !important;
  }

  .hljs-number,
  .hljs-literal {
    color: var(--el-color-warning) !important;
  }
}
</style>
