<template>
  <div class="session-sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">{{ t("ai_chat.sessionSidebar_title") }}</span>
      <el-button size="small" :icon="Plus" circle @click="emit('create')" />
    </div>
    <el-input
      v-model="keyword"
      size="small"
      :placeholder="t('ai_chat.sessionSidebar_search')"
      :prefix-icon="Search"
      clearable
      class="sidebar-search"
    />
    <div class="session-list">
      <div
        v-for="s in filtered"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === activeId }"
        @click="emit('select', s.id)"
      >
        <template v-if="editingId === s.id">
          <el-input
            v-model="editTitle"
            size="small"
            class="edit-input"
            @click.stop
            @keyup.enter="confirmRename(s)"
            @keyup.esc="cancelRename"
          />
        </template>
        <template v-else>
          <span class="session-title">{{ s.title || t("ai_chat.sessionSidebar_unnamed") }}</span>
          <span class="session-meta">
            {{ t("ai_chat.sessionSidebar_messageCount", { count: s.message_count }) }}
          </span>
          <span class="session-actions" @click.stop>
            <el-icon class="action-icon" @click="startRename(s)"><Edit /></el-icon>
            <el-icon class="action-icon action-icon--danger" @click="handleRemove(s)">
              <Delete />
            </el-icon>
          </span>
        </template>
      </div>
      <el-empty
        v-if="!filtered.length"
        :description="t('ai_chat.sessionSidebar_empty')"
        :image-size="52"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import { Plus, Search, Edit, Delete } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import type { AiSessionItem } from "@/api/module_ai/session";

interface Props {
  sessions: AiSessionItem[];
  activeId: number | null;
}

interface Emits {
  (e: "select", id: number): void;
  (e: "create"): void;
  (e: "rename", id: number, title: string): void;
  (e: "remove", id: number): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const { t } = useI18n();

const keyword = ref("");
const editingId = ref<number | null>(null);
const editTitle = ref("");

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return props.sessions;
  return props.sessions.filter((s) => (s.title || "").toLowerCase().includes(kw));
});

const startRename = (s: AiSessionItem) => {
  editingId.value = s.id;
  editTitle.value = s.title || "";
};

const confirmRename = (s: AiSessionItem) => {
  const title = editTitle.value.trim();
  editingId.value = null;
  if (!title || title === s.title) return;
  emit("rename", s.id, title);
};

const cancelRename = () => {
  editingId.value = null;
};

const handleRemove = async (s: AiSessionItem) => {
  try {
    await ElMessageBox.confirm(
      t("ai_chat.sessionSidebar_deleteConfirm", {
        title: s.title || t("ai_chat.sessionSidebar_unnamed"),
        count: s.message_count,
      }),
      t("ai_chat.sessionSidebar_deleteSession"),
      {
        type: "warning",
        confirmButtonText: t("ai_chat.sessionSidebar_delete"),
        cancelButtonText: t("ai_chat.sessionSidebar_cancel"),
      }
    );
  } catch {
    return;
  }
  emit("remove", s.id);
};
</script>

<style lang="scss" scoped>
.session-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-right: 1px solid var(--el-border-color-lighter);

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;

    .sidebar-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }
  }

  .sidebar-search {
    margin-bottom: 8px;
  }

  .session-list {
    flex: 1;
    overflow-y: auto;

    .session-item {
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 8px 10px;
      margin-bottom: 4px;
      cursor: pointer;
      border-radius: 6px;
      transition: background 0.2s ease;

      &:hover {
        background: var(--el-fill-color);

        .session-actions {
          opacity: 1;
        }
      }

      &.active {
        background: var(--el-color-primary-light-9);
        border: 1px solid var(--el-color-primary-light-7);
      }

      .session-title {
        flex: 1;
        overflow: hidden;
        font-size: var(--el-font-size-small);
        text-overflow: ellipsis;
        white-space: nowrap;
        color: var(--el-text-color-primary);
      }

      .session-meta {
        flex-shrink: 0;
        font-size: var(--el-font-size-small);
        color: var(--el-text-color-secondary);
      }

      .session-actions {
        display: flex;
        flex-shrink: 0;
        gap: 6px;
        opacity: 0;
        transition: opacity 0.2s ease;

        .action-icon {
          font-size: 14px;
          color: var(--el-text-color-secondary);

          &:hover {
            color: var(--el-color-primary);
          }

          &--danger:hover {
            color: var(--el-color-danger);
          }
        }
      }

      .edit-input {
        flex: 1;
      }
    }
  }
}
</style>
