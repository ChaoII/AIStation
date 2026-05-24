<template>
  <div
    ref="containerRef"
    class="cm-wrapper"
    :class="{ 'cm-wrapper-border': border, 'cm-readonly': readonly }"
    :style="{ height }"
  />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, unref } from "vue";
import { EditorView } from "@codemirror/view";
import { EditorState, Compartment } from "@codemirror/state";
import { basicSetup } from "codemirror";
import { json } from "@codemirror/lang-json";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { html } from "@codemirror/lang-html";
import { javascript } from "@codemirror/lang-javascript";
import { oneDark } from "@codemirror/theme-one-dark";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    language?: string;
    readonly?: boolean;
    theme?: string;
    height?: string;
    border?: boolean;
  }>(),
  {
    modelValue: "",
    language: "json",
    readonly: false,
    theme: "default",
    height: "360px",
    border: false,
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const containerRef = ref<HTMLDivElement>();
let view: EditorView | null = null;

const languageComp = new Compartment();
const themeComp = new Compartment();
const readonlyComp = new Compartment();

function getLanguageExt(lang: string) {
  switch (lang) {
    case "python":
      return python();
    case "sql":
      return sql();
    case "html":
      return html();
    case "javascript":
    case "js":
    case "typescript":
    case "ts":
      return javascript();
    default:
    case "json":
      return json();
  }
}

function getThemeExt(theme: string) {
  if (theme === "one-dark" || theme === "dark" || theme === "dracula") {
    return [
      oneDark,
      EditorView.theme({
        "&": { backgroundColor: "#1e1e2e" },
        ".cm-gutters": { backgroundColor: "#181825" },
      }),
    ];
  }
  return [];
}

function createEditor() {
  const container = unref(containerRef);
  if (!container) return;

  const state = EditorState.create({
    doc: props.modelValue,
    extensions: [
      basicSetup,
      languageComp.of(getLanguageExt(props.language)),
      themeComp.of(getThemeExt(props.theme)),
      readonlyComp.of(EditorView.editable.of(!props.readonly)),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          emit("update:modelValue", update.state.doc.toString());
        }
      }),
      EditorView.theme({
        "&": { fontSize: "13px" },
        ".cm-scroller": {
          fontFamily: '"SF Mono", "SFMono-Regular", Menlo, Monaco, Consolas, monospace',
        },
        ".cm-content, .cm-lineNumbers": {
          fontFamily: '"SF Mono", "SFMono-Regular", Menlo, Monaco, Consolas, monospace',
        },
        "&.cm-focused": { outline: "none" },
        ".cm-activeLine": { backgroundColor: "transparent" },
        ".cm-activeLineGutter": { backgroundColor: "transparent" },
      }),
    ],
  });

  view = new EditorView({ state, parent: container });
}

function destroyEditor() {
  if (view) {
    view.destroy();
    view = null;
  }
}

function reconfigure(comp: Compartment, ext: any) {
  if (view) {
    view.dispatch({ effects: comp.reconfigure(ext) });
  }
}

watch(
  () => props.language,
  (lang) => {
    reconfigure(languageComp, getLanguageExt(lang));
  }
);

watch(
  () => props.theme,
  (theme) => {
    reconfigure(themeComp, getThemeExt(theme));
  }
);

watch(
  () => props.readonly,
  (ro) => {
    reconfigure(readonlyComp, EditorView.editable.of(!ro));
  }
);

watch(
  () => props.modelValue,
  (newVal) => {
    if (view && newVal !== view.state.doc.toString()) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: newVal || "" },
      });
    }
  }
);

onMounted(() => {
  createEditor();
});

onBeforeUnmount(() => {
  destroyEditor();
});
</script>

<style scoped>
.cm-wrapper {
  width: 100%;
  overflow: hidden;
}
.cm-wrapper-border {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}
.cm-wrapper :deep(.cm-editor) {
  height: 100%;
}
.cm-wrapper :deep(.cm-scroller) {
  overflow: auto;
}
</style>
