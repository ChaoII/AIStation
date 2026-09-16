<template>
  <div class="chat-input" :class="{ 'chat-input--disabled': disabled }">
    <div class="input-wrapper">
      <div v-if="uploadedFiles.length > 0" class="uploaded-files">
        <div v-for="file in uploadedFiles" :key="file.id" class="file-item">
          <el-icon class="file-icon"><Document /></el-icon>
          <span class="file-name">{{ file.name }}</span>
          <el-icon class="file-remove" @click="removeFile(file.id)"><Close /></el-icon>
        </div>
      </div>
      <div class="input-container">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :placeholder="placeholder"
          :disabled="disabled || sending"
          :autosize="{ minRows: 1, maxRows: 6 }"
          resize="none"
          class="message-input"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.shift.enter.exact="handleShiftEnter"
        />
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
            :disabled="(!inputMessage.trim() && uploadedFiles.length === 0) || disabled || sending"
            :loading="sending"
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { Promotion, Paperclip, Document, Close } from "@element-plus/icons-vue";
import type { UploadFile } from "element-plus";
import type { UploadedFile } from "@/views/module_ai/chat/types";

interface Props {
  disabled?: boolean;
  sending?: boolean;
}

interface Emits {
  (e: "send", message: string, files?: UploadedFile[]): void;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  sending: false,
});

const emit = defineEmits<Emits>();

const inputMessage = ref("");
const uploadedFiles = ref<UploadedFile[]>([]);

const acceptTypes = computed(() => {
  return ".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png,.gif,.mp3,.wav,.mp4,.avi,.mov";
});

const placeholder = "输入消息…（Enter 发送 / Shift+Enter 换行）";

const handleFileChange = (uploadFile: UploadFile) => {
  const file = uploadFile.raw;
  if (!file) return;

  const maxSize = 10 * 1024 * 1024;
  if (file.size > maxSize) {
    alert("文件大小不能超过10MB");
    return;
  }

  const uploadedFile: UploadedFile = {
    id: Date.now().toString() + Math.random().toString(36).substr(2),
    name: file.name,
    size: file.size,
    type: file.type,
    file,
  };

  uploadedFiles.value.push(uploadedFile);
};

const removeFile = (id: string) => {
  const index = uploadedFiles.value.findIndex((f) => f.id === id);
  if (index > -1) {
    uploadedFiles.value.splice(index, 1);
  }
};

const handleSend = () => {
  const message = inputMessage.value.trim();
  if ((!message && uploadedFiles.value.length === 0) || props.disabled || props.sending) {
    return;
  }
  emit("send", message, uploadedFiles.value.length > 0 ? [...uploadedFiles.value] : undefined);
  inputMessage.value = "";
  uploadedFiles.value = [];
};

const handleShiftEnter = () => {
  inputMessage.value += "\n";
};

defineExpose({
  focus: () => {
    const input = document.querySelector(".message-input textarea") as HTMLTextAreaElement;
    input?.focus();
  },
});
</script>

<style lang="scss" scoped>
.chat-input {
  .input-wrapper {
    /* 铺满聊天区，仅保留左右内边距，不再居中限宽 */
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
        padding: 8px 14px;
        font-size: 13px;
        background: var(--el-fill-color-light);
        border: 1px solid var(--el-border-color-light);
        border-radius: 8px;
        transition: all 0.2s ease;

        &:hover {
          background: var(--el-color-primary-light-9);
          border-color: var(--el-color-primary-light-7);
        }

        .file-icon {
          font-size: 16px;
          color: var(--el-color-primary);
        }

        .file-name {
          max-width: 180px;
          overflow: hidden;
          text-overflow: ellipsis;
          font-size: 13px;
          white-space: nowrap;
        }

        .file-remove {
          font-size: 14px;
          color: var(--el-text-color-secondary);
          cursor: pointer;
          transition: color 0.2s ease;

          &:hover {
            color: var(--el-color-danger);
          }
        }
      }
    }

    /* 紧凑一行：左侧 textarea 自适应，右侧附件/发送按钮内联 */
    .input-container {
      display: flex;
      gap: 8px;
      align-items: flex-end;
      padding: 8px 12px;
      background: var(--el-bg-color-overlay);
      border: 1px solid var(--el-border-color-light);
      border-radius: 8px;
      box-shadow: var(--el-box-shadow-light);
      transition:
        border-color 0.2s ease,
        box-shadow 0.2s ease;

      &:hover {
        border-color: var(--el-color-primary);
        box-shadow: var(--el-box-shadow);
      }

      &:focus-within {
        border-color: var(--el-color-primary);
        box-shadow: 0 0 0 1px var(--el-color-primary);
      }

      .message-input {
        flex: 1;
        min-width: 0;

        :deep(.el-textarea__inner) {
          padding: 0;
          line-height: 1.6;
          color: var(--el-text-color-primary);
          resize: none;
          background: transparent;
          border: none;
          box-shadow: none;
        }

        :deep(.el-textarea) {
          padding: 0;
        }
      }

      .input-actions {
        display: flex;
        flex-shrink: 0;
        gap: 8px;
        align-items: center;

        .upload-btn {
          font-size: 18px;
          color: var(--el-text-color-secondary);
          transition: all 0.2s ease;

          &:hover {
            color: var(--el-color-primary);
            transform: scale(1.05);
          }
        }

        .send-button {
          flex-shrink: 0;
          border-radius: 50%;
          box-shadow: var(--el-box-shadow-light);
          transition: all 0.2s ease;

          &:hover {
            box-shadow: var(--el-box-shadow);
            transform: translateY(-1px);
          }

          &:active {
            transform: translateY(0);
          }
        }
      }
    }
  }

  &.chat-input--disabled .input-wrapper .input-container {
    opacity: 0.72;
    filter: grayscale(0.06);

    &:hover {
      border-color: var(--el-border-color-light);
      box-shadow: var(--el-box-shadow-light);
    }

    &:focus-within {
      border-color: var(--el-border-color-light);
      box-shadow: var(--el-box-shadow-light);
    }
  }
}
</style>
