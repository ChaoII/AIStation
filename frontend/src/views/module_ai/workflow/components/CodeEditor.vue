<!-- 代码/JSON 编辑器：封装 CodeMirror 6，按语言高亮，双向绑定 modelValue -->
<template>
  <div ref="host" class="code-editor"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from "vue";
import { EditorView, basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { python } from "@codemirror/lang-python";
import { json } from "@codemirror/lang-json";
import { javascript } from "@codemirror/lang-javascript";
import { sql } from "@codemirror/lang-sql";

const props = defineProps<{
  modelValue?: string;
  language?: "python" | "json" | "javascript" | "sql";
}>();
const emit = defineEmits(["update:modelValue"]);

const host = ref<HTMLElement>();
let view: EditorView | null = null;

function lang() {
  if (props.language === "python") return python();
  if (props.language === "json") return json();
  if (props.language === "sql") return sql();
  return javascript();
}

onMounted(() => {
  view = new EditorView({
    parent: host.value!,
    state: EditorState.create({
      doc: props.modelValue || "",
      extensions: [
        basicSetup,
        lang(),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit("update:modelValue", u.state.doc.toString());
        }),
      ],
    }),
  });
});

watch(
  () => props.modelValue,
  (v) => {
    if (view && view.state.doc.toString() !== (v || "")) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: v || "" },
      });
    }
  }
);

onBeforeUnmount(() => view?.destroy());
</script>

<style scoped lang="scss">
.code-editor {
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  overflow: hidden;

  :deep(.cm-editor) {
    font-size: 13px;
    min-height: 140px;
  }

  :deep(.cm-scroller) {
    font-family: var(--el-font-family);
  }
}
</style>
