<template>
  <div class="chat-input" :class="{ 'chat-input--disabled': disabled }">
    <div class="input-wrapper">
      <div v-if="uploadedFiles.length > 0" class="uploaded-files">
        <div v-for="file in uploadedFiles" :key="file.id" class="file-item">
          <img v-if="isImage(file)" :src="fileUrl(file)" class="file-thumb" alt="" />
          <el-icon v-else class="file-icon"><Document /></el-icon>
          <span class="file-name">{{ file.name }}</span>
          <el-icon class="file-remove" @click="removeFile(file.id)"><Close /></el-icon>
        </div>
      </div>

      <div ref="containerRef" class="input-container" :class="{ 'is-locked': disabled || sending }">
        <div class="editor-wrap">
          <div ref="editorEl" class="cm-host" :class="{ 'is-readonly': disabled || sending }"></div>
          <div v-if="atMenuVisible" class="at-menu" :style="atMenuStyle">
            <div class="at-menu__title">快捷指令</div>
            <div
              v-for="cmd in filteredAtCommands"
              :key="cmd.name"
              class="at-item"
              @click="chooseAt(cmd)"
            >
              <span class="at-item__name">#{{ cmd.name }}</span>
              <span class="at-item__desc">{{ cmd.desc }}</span>
            </div>
            <div v-if="filteredAtCommands.length === 0" class="at-menu__empty">无匹配指令</div>
          </div>
        </div>

        <div class="input-footer">
          <div class="quick-chips">
            <el-tag
              v-for="chip in quickChips"
              :key="chip"
              size="small"
              effect="plain"
              class="chip"
              @click="insertToken(`#${chip}`)"
            >
              #{{ chip }}
            </el-tag>
          </div>
          <div class="input-actions">
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :show-file-list="false"
              :on-change="handleFileChange"
              :accept="acceptTypes"
              :multiple="true"
            >
              <el-button :icon="Paperclip" class="upload-btn" circle />
            </el-upload>
            <el-button
              v-if="sending"
              class="stop-button"
              type="danger"
              circle
              @click="emit('stop')"
            >
              <el-icon><VideoPause /></el-icon>
            </el-button>
            <el-button
              v-else
              :disabled="
                (!inputMessage.trim() && uploadedFiles.length === 0) || disabled || sending
              "
              class="send-button"
              type="primary"
              circle
              @click="handleSend"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
      <div class="input-hint">按 Enter 发送消息，Shift + Enter 换行，@ 唤起快捷指令</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import type { UploadFile } from "element-plus";
import { ElMessage } from "element-plus";
import { Promotion, Paperclip, Document, Close, VideoPause } from "@element-plus/icons-vue";
import {
  EditorView,
  keymap,
  placeholder,
  ViewPlugin,
  Decoration,
  type DecorationSet,
} from "@codemirror/view";
import { EditorState, Prec, RangeSetBuilder } from "@codemirror/state";
import { basicSetup } from "codemirror";
import { insertNewlineAndIndent } from "@codemirror/commands";
import type { UploadedFile } from "@/views/module_ai/chat/types";

interface Props {
  disabled?: boolean;
  sending?: boolean;
}

interface Emits {
  (e: "send", message: string, files?: UploadedFile[]): void;
  (e: "stop"): void;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  sending: false,
});

const emit = defineEmits<Emits>();

const inputMessage = ref("");
const uploadedFiles = ref<UploadedFile[]>([]);
const editorEl = ref<HTMLElement>();
const containerRef = ref<HTMLElement>();

const atMenuVisible = ref(false);
const atQuery = ref("");
let atAnchor: number | null = null;

const acceptTypes = computed(
  () => ".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.gif,.mp3,.wav,.mp4,.avi,.mov"
);

const atMenuStyle = computed(() => ({
  left: "12px",
  bottom: `${(editorEl.value?.clientHeight || 120) + 44}px`,
}));

const quickChips = ["联网搜索", "生成报告", "创建数据集", "创建标注任务"];

const atCommands = [
  { name: "联网搜索", desc: "联网检索最新信息" },
  { name: "生成报告", desc: "基于检索结果生成报告" },
  { name: "创建数据集", desc: "调用数据集创建工具" },
  { name: "创建标注任务", desc: "创建标注任务" },
];

/** 根据 `@` 后已输入文本过滤快捷指令。 */
const filteredAtCommands = computed(() => {
  const q = atQuery.value.trim();
  if (!q) return atCommands;
  return atCommands.filter((c) => c.name.includes(q) || c.desc.includes(q));
});

/** 高亮 `#指令名` token。 */
const mentionHighlight = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = buildMentions(view);
    }
    update(u: any) {
      if (u.docChanged) this.decorations = buildMentions(u.view);
    }
  },
  { decorations: (v: any) => v.decorations }
);

function buildMentions(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const re = /#[A-Za-z\u4e00-\u9fa5_][\w\u4e00-\u9fa5_-]*/g;
  const text = view.state.doc.toString();
  const mark = Decoration.mark({ class: "mention" });
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    builder.add(m.index, m.index + m[0].length, mark);
  }
  return builder.finish();
}

let view: EditorView | null = null;

onMounted(() => {
  if (!editorEl.value) return;
  view = new EditorView({
    parent: editorEl.value,
    state: EditorState.create({
      doc: "",
      extensions: [
        basicSetup,
        EditorView.lineWrapping,
        placeholder("输入消息…（Enter 发送 / Shift+Enter 换行，@ 唤起快捷指令）"),
        mentionHighlight,
        EditorView.updateListener.of((u) => {
          if (u.docChanged) {
            inputMessage.value = u.state.doc.toString();
          }
          detectAtMenu(u.state);
        }),
        Prec.highest(
          keymap.of([
            {
              key: "Enter",
              preventDefault: true,
              run: () => {
                handleSend();
                return true;
              },
            },
            {
              key: "Shift-Enter",
              preventDefault: true,
              run: (cm) => {
                insertNewlineAndIndent(cm);
                return true;
              },
            },
            { key: "Escape", run: () => (atMenuVisible.value = false) },
          ])
        ),
      ],
    }),
  });
});

onBeforeUnmount(() => {
  view?.destroy();
  view = null;
  // 释放所有已创建的预览 ObjectURL，避免内存泄漏
  for (const f of uploadedFiles.value) {
    if (f.url) URL.revokeObjectURL(f.url);
  }
});

function detectAtMenu(state: EditorState) {
  const head = state.selection.main.head;
  // 从光标向前找当前`@`（仅当`@`与光标之间的文本是连续字词时视作候选前缀）
  const before = state.doc.sliceString(0, head);
  const atPos = findAtPos(before);
  if (atPos !== -1 && !props.sending) {
    atAnchor = atPos + 1;
    atQuery.value = state.doc.sliceString(atPos + 1, head);
    atMenuVisible.value = true;
  } else {
    atMenuVisible.value = false;
    atAnchor = null;
    atQuery.value = "";
  }
}

/** 在光标前的文本中定位最后一个未被 `#` 占位的 `@`，返回其位置；无则 -1。 */
function findAtPos(text: string): number {
  const re = /(?:^|\s|^#|#)@([\w\u4e00-\u9fa5]*)$/;
  const m = re.exec(text);
  return m ? m.index + m[0].lastIndexOf("@") : -1;
}

function chooseAt(cmd: { name: string }) {
  if (!view || atAnchor == null) return;
  // 把光标前的 `@查询` 整体替换为 `#名称`
  const head = view.state.selection.main.head;
  view.dispatch({
    changes: { from: atAnchor - 1, to: head, insert: `#${cmd.name}` },
    selection: { anchor: atAnchor - 1 + cmd.name.length + 1 },
  });
  inputMessage.value = view.state.doc.toString();
  atMenuVisible.value = false;
  atAnchor = null;
  atQuery.value = "";
  view.focus();
}

function insertToken(token: string) {
  if (!view) return;
  const head = view.state.selection.main.head;
  view.dispatch({
    changes: { from: head, to: head, insert: `${token} ` },
    selection: { anchor: head + token.length + 1 },
  });
  inputMessage.value = view.state.doc.toString();
  view.focus();
}

const handleFileChange = (uploadFile: UploadFile) => {
  const file = uploadFile.raw;
  if (!file) return;
  const maxSize = 10 * 1024 * 1024;
  if (file.size > maxSize) {
    ElMessage.warning("文件大小不能超过10MB");
    return;
  }
  const uploadedFile: UploadedFile = {
    id: Date.now().toString() + Math.random().toString(36).slice(2),
    name: file.name,
    size: file.size,
    type: file.type,
    url: URL.createObjectURL(file),
    file,
  };
  uploadedFiles.value.push(uploadedFile);
};

const removeFile = (id: string) => {
  const index = uploadedFiles.value.findIndex((f) => f.id === id);
  if (index > -1) {
    const f = uploadedFiles.value[index];
    if (f.url) URL.revokeObjectURL(f.url);
    uploadedFiles.value.splice(index, 1);
  }
};

const isImage = (file: UploadedFile) => file.type?.startsWith("image/");
const fileUrl = (file: UploadedFile) => file.url || "";

const clearEditor = () => {
  if (!view) return;
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: "" } });
  inputMessage.value = "";
};

const handleSend = () => {
  const message = inputMessage.value.trim();
  if ((!message && uploadedFiles.value.length === 0) || props.disabled || props.sending) {
    return;
  }
  emit("send", message, uploadedFiles.value.length > 0 ? [...uploadedFiles.value] : undefined);
  clearEditor();
  uploadedFiles.value = [];
};

defineExpose({
  focus: () => {
    view?.focus();
  },
});
</script>

<style lang="scss" scoped>
.chat-input {
  .input-wrapper {
    max-width: 800px;
    margin: 0 auto;
    padding: 12px 16px;

    .uploaded-files {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;

      .file-item {
        display: flex;
        gap: 6px;
        align-items: center;
        padding: 6px 10px;
        font-size: var(--el-font-size-small);
        background: var(--el-fill-color-light);
        border: 1px solid var(--el-border-color-light);
        border-radius: 8px;

        .file-thumb {
          width: 28px;
          height: 28px;
          object-fit: cover;
          border-radius: 4px;
        }

        .file-icon {
          font-size: var(--el-font-size-medium);
          color: var(--el-color-primary);
        }

        .file-name {
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          font-size: var(--el-font-size-small);
          white-space: nowrap;
        }

        .file-remove {
          cursor: pointer;
          color: var(--el-text-color-secondary);

          &:hover {
            color: var(--el-color-danger);
          }
        }
      }
    }

    .input-container {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px 20px;
      background: var(--el-bg-color-overlay);
      border: 1px solid var(--el-border-color-light);
      border-radius: 16px;
      box-shadow: var(--el-box-shadow-light);
      transition:
        border-color 0.2s ease,
        box-shadow 0.2s ease,
        transform 0.2s ease;

      &:hover {
        border-color: var(--el-color-primary);
        box-shadow: var(--el-box-shadow);
        transform: translateY(-2px);
      }

      &:focus-within {
        border-color: var(--el-color-primary);
        box-shadow: 0 0 0 1px var(--el-color-primary);
      }

      &.is-locked:hover,
      &.is-locked:focus-within {
        border-color: var(--el-border-color-light);
        box-shadow: var(--el-box-shadow-light);
        transform: none;
      }

      .editor-wrap {
        position: relative;
        min-width: 0;

        .cm-host {
          max-height: 180px;
          overflow: hidden;
          font-size: var(--el-font-size-base);
          line-height: 1.6;

          &.is-readonly {
            opacity: 0.6;
            pointer-events: none;
          }

          :deep(.cm-editor) {
            background: transparent;

            &.cm-focused {
              outline: none;
            }
          }

          :deep(.cm-scroller) {
            font-family: inherit;
            overflow: auto;
          }

          :deep(.mention) {
            color: var(--el-color-primary);
            font-weight: 600;
            background: var(--el-color-primary-light-9);
            border-radius: 3px;
          }
        }

        .at-menu {
          position: absolute;
          z-index: 30;
          width: 220px;
          overflow: hidden;
          background: var(--el-bg-color-overlay);
          border: 1px solid var(--el-border-color-light);
          border-radius: 8px;
          box-shadow: var(--el-box-shadow);

          .at-menu__title {
            padding: 6px 12px;
            font-size: var(--el-font-size-small);
            color: var(--el-text-color-secondary);
            background: var(--el-fill-color-light);
          }

          .at-menu__empty {
            padding: 10px 12px;
            font-size: var(--el-font-size-small);
            color: var(--el-text-color-secondary);
          }

          .at-item {
            display: flex;
            gap: 8px;
            align-items: center;
            padding: 8px 12px;
            cursor: pointer;

            &:hover {
              background: var(--el-fill-color-light);
            }

            .at-item__name {
              flex-shrink: 0;
              font-size: var(--el-font-size-small);
              font-weight: 600;
              color: var(--el-color-primary);
            }

            .at-item__desc {
              font-size: var(--el-font-size-small);
              color: var(--el-text-color-secondary);
            }
          }
        }
      }

      .input-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;

        .quick-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;

          .chip {
            cursor: pointer;
          }
        }

        .input-actions {
          display: flex;
          flex-shrink: 0;
          gap: 8px;
          align-items: center;

          .upload-btn {
            font-size: var(--el-font-size-large);
            color: var(--el-text-color-secondary);

            &:hover {
              color: var(--el-color-primary);
            }
          }

          .send-button,
          .stop-button {
            flex-shrink: 0;
            border-radius: 50%;
            box-shadow: var(--el-box-shadow-light);
          }
        }
      }
    }

    .input-hint {
      margin-top: 10px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
      text-align: center;
      letter-spacing: 0.3px;
    }
  }

  &.chat-input--disabled .input-wrapper .input-container {
    opacity: 0.72;
    filter: grayscale(0.06);
  }
}
</style>
