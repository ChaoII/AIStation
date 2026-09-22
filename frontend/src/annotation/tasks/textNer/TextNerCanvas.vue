<template>
  <div ref="root" class="text-ner-canvas">
    <div ref="editorRef" class="text-ner-canvas__editor" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { basicSetup } from "codemirror";
import { EditorState, StateField, StateEffect } from "@codemirror/state";
import { EditorView, Decoration, type DecorationSet } from "@codemirror/view";
import type { EntitySpan } from "../../../api/module_annotation/document";

/** 选区区间（UTF-16 code unit 偏移）。 */
export interface TextSelectRange {
  from: number;
  to: number;
}

const props = withDefaults(
  defineProps<{
    /** 只读文本内容。 */
    content: string;
    /** 当前实体区间（用于 Mark 高亮）。 */
    entities?: EntitySpan[];
    /** 当前选中实体 id（高亮描边）。 */
    selectedId?: string;
    /** 需高亮描边的实体 id 集合（如关系两端实体）。 */
    highlightIds?: string[];
    /** 实体颜色函数：入参 `(span, classes)`，返回 CSS 颜色。缺省用配色表。 */
    entityColor?: (span: EntitySpan, classes: any[]) => string;
    /** 任务类别（供颜色函数使用，可为空）。 */
    classes?: any[];
  }>(),
  {
    entities: () => [],
    selectedId: "",
    highlightIds: () => [],
    classes: () => [],
    entityColor: undefined,
  }
);

const emit = defineEmits<{
  /** 用户完成一次选区（mouseup），供外部提示实体类型。 */
  (e: "select", range: TextSelectRange): void;
  /** 选区实时变化（含当前主选区）。 */
  (e: "selection", range: TextSelectRange): void;
  /** 点击落在已有实体上，供外部打开编辑对话框。 */
  (e: "span-click", span: EntitySpan): void;
}>();

const root = ref<HTMLElement | null>(null);
const editorRef = ref<HTMLElement | null>(null);
let view: EditorView | null = null;

/** 装饰集合更新 effect + 承载 StateField（`provide` 给 `EditorView.decorations`）。 */
const setDecorations = StateEffect.define<DecorationSet>();
const decorationField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    value = value.map(tr.changes);
    for (const e of tr.effects) {
      if (e.is(setDecorations)) value = e.value;
    }
    return value;
  },
  provide: (f) => EditorView.decorations.from(f),
});

/** 实体 mark 默认配色表（按 label_id 取色，避免与 Element 主色冲突）。 */
const PALETTE = ["#cce8ff", "#ffe6a8", "#d8f5d0", "#ffd6d6", "#e6e0ff", "#d0f0f0"];

function entityColorOf(span: EntitySpan, classes: any[]): string {
  if (props.entityColor) return props.entityColor(span, classes);
  return PALETTE[Math.abs(span.label_id) % PALETTE.length];
}

/** 根据当前实体列表构建 Mark 装饰集合。 */
function buildDecorations(): DecorationSet {
  const sorted = [...(props.entities ?? [])].sort((a, b) => a.start - b.start || a.end - b.end);
  const ranges: { from: number; to: number; value: ReturnType<typeof Decoration.mark> }[] = [];
  for (const span of sorted) {
    const color = entityColorOf(span, props.classes ?? []);
    const bg = isBaseColor(color) ? color : `color-mix(in srgb, ${color} 24%, transparent)`;
    const isSelected = span.id === props.selectedId || props.highlightIds?.includes(span.id);
    ranges.push({
      from: span.start,
      to: span.end,
      value: Decoration.mark({
        class: isSelected ? "text-ner-entity text-ner-entity--selected" : "text-ner-entity",
        attributes: {
          "data-entity-id": span.id,
          style: `--ner-color:${color}; background-color:${bg}; ${
            isSelected ? "box-shadow:0 0 0 1px " + color : ""
          }`,
        },
      }),
    });
  }
  return Decoration.set(ranges, true);
}

function isBaseColor(color: string): boolean {
  return /^(#[0-9a-f]{3,8}|rgb|hsl|var\(|transparent)/i.test(color);
}

function applyDecorations() {
  view?.dispatch({ effects: setDecorations.of(buildDecorations()) });
}

function currentRange(): TextSelectRange {
  const sel = view?.state.selection.main;
  return sel ? { from: sel.from, to: sel.to } : { from: 0, to: 0 };
}

function handleEditorClick(ev: MouseEvent) {
  if (!view) return;
  const href = (ev.target as HTMLElement)?.closest?.("[data-entity-id]") as HTMLElement | null;
  if (href) {
    const id = href.getAttribute("data-entity-id");
    const span = (props.entities ?? []).find((s) => s.id === id);
    if (span) emit("span-click", span);
    return;
  }
}

function handleEditorMouseUp(ev: MouseEvent) {
  if (!view) return;
  const onEntity = (ev.target as HTMLElement)?.closest?.("[data-entity-id]");
  const range = currentRange();
  // 点击实体交由 span-click 处理；仅在拖动产生非空选区时触发 select
  if (!onEntity && range.to > range.from) emit("select", range);
}

onMounted(() => {
  if (!editorRef.value) return;
  const state = EditorState.create({
    doc: props.content,
    extensions: [
      basicSetup,
      // 只读：禁止任何修改（readOnly 由命令层拦截），但保留 contenteditable 以支持鼠标拖选。
      // 切勿同时设置 EditorView.editable.of(false)——那会关闭 DOM 可编辑，鼠标拖选失效。
      EditorState.readOnly.of(true),
      decorationField,
      EditorView.updateListener.of((update) => {
        if (update.selectionSet || update.docChanged) emit("selection", currentRange());
      }),
      EditorView.theme({
        "&": { fontSize: "var(--el-font-size-base)", height: "100%" },
        ".cm-scroller": { fontFamily: "var(--el-font-family, inherit)" },
      }),
    ],
  });
  view = new EditorView({ state, parent: editorRef.value });
  applyDecorations();
  view.dom.addEventListener("click", handleEditorClick);
  view.dom.addEventListener("mouseup", handleEditorMouseUp);
});

onUnmounted(() => {
  if (view) {
    view.dom.removeEventListener("click", handleEditorClick);
    view.dom.removeEventListener("mouseup", handleEditorMouseUp);
    view.destroy();
    view = null;
  }
});

watch(
  () => [props.entities, props.selectedId, props.highlightIds] as const,
  () => applyDecorations(),
  { deep: true }
);

// 内容异步加载：控件挂载时 content 可能为空，全文到位后替换文档并重建装饰。
watch(
  () => props.content,
  (val) => {
    if (!view) return;
    if (val === view.state.doc.toString()) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: val } });
    applyDecorations();
  }
);
</script>

<style>
.text-ner-canvas {
  height: 100%;
  overflow: auto;
}

.text-ner-canvas__editor {
  height: 100%;
  min-height: 100%;
}

.text-ner-canvas .cm-editor {
  height: 100%;
}

/* 实体高亮 Mark：底色由内联 --ner-color 提供，此处仅做统一基础样式与下划线 */
.text-ner-canvas .cm-line span.text-ner-entity {
  border-bottom: 1.5px solid var(--ner-color);
  cursor: pointer;
  transition: background-color 0.1s ease;
}

.text-ner-canvas .cm-line span.text-ner-entity:hover {
  filter: brightness(0.94);
}
</style>
