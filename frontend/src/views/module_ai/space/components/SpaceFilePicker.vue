<!-- 个人空间文件选择器：弹窗内「左侧文件夹树 + 右侧文件表」，供助手对话引用空间文件 -->
<template>
  <el-dialog
    :model-value="visible"
    :title="t('ai_chat.spaceFilePicker_title')"
    width="900px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="space-picker">
      <div class="space-picker-side">
        <div class="space-picker-side-head">
          <span>{{ t("ai_chat.spaceFilePicker_folders") }}</span>
          <el-button link type="primary" :icon="FolderOpened" @click="pickFolder(null)">
            {{ t("ai_chat.spaceFilePicker_all") }}
          </el-button>
        </div>
        <el-tree
          :data="treeData"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="currentFolderId ?? undefined"
          highlight-current
          :expand-on-click-node="false"
          @node-click="(d: any) => pickFolder(d.id)"
        />
      </div>
      <div class="space-picker-main">
        <el-input
          v-model="keyword"
          :placeholder="t('ai_chat.spaceFilePicker_search')"
          clearable
          :prefix-icon="Search"
          style="width: 100%"
          @input="loadFiles(1)"
        />
        <el-table
          v-loading="loading"
          border
          stripe
          :data="files"
          height="320"
          :empty-text="t('ai_chat.spaceFilePicker_noFiles')"
          @selection-change="(rows: any[]) => (selected = rows)"
        >
          <el-table-column type="selection" width="40" :selectable="() => !!props.multiple" />
          <el-table-column :label="t('ai_chat.space_name')" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="space-picker-name">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_chat.space_type')" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ typeLabel(row.file_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_chat.space_size')" width="90" align="right">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
        </el-table>
        <div class="space-picker-footer">
          <span class="space-picker-count">
            {{ t("ai_chat.spaceFilePicker_selected", { count: selected.length }) }}
          </span>
          <el-button type="primary" :disabled="!selected.length" @click="confirmPick">
            {{ t("ai_chat.spaceFilePicker_confirm") }}
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { FolderOpened, Search } from "@element-plus/icons-vue";

import {
  getSpaceFileList,
  getSpaceFolderTree,
  type SpaceFileItem,
  type SpaceFolder,
} from "@/api/module_ai/space";

const props = defineProps<{
  visible: boolean;
  multiple?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:visible", v: boolean): void;
  (e: "confirm", files: { file_id: number; name: string; file_type: string }[]): void;
}>();

const { t } = useI18n();

const treeData = ref<SpaceFolder[]>([]);
const currentFolderId = ref<number | null>(null);
const keyword = ref("");
const files = ref<SpaceFileItem[]>([]);
const selected = ref<SpaceFileItem[]>([]);
const loading = ref(false);

const typeLabels: Record<string, string> = {
  image: t("ai_chat.space_typeImage"),
  pdf: "PDF",
  docx: t("ai_chat.space_typeDoc"),
  txt: t("ai_chat.space_typeText"),
  md: "MD",
  csv: "CSV",
  json: "JSON",
  video: t("ai_chat.space_typeVideo"),
  audio: t("ai_chat.space_typeAudio"),
  other: t("ai_chat.space_typeOther"),
};

function formatSize(bytes: number): string {
  if (bytes == null || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function typeLabel(ft: string): string {
  return typeLabels[ft] || ft || t("ai_chat.space_typeOther");
}

async function loadTree() {
  const r = await getSpaceFolderTree();
  treeData.value = r.data?.data || [];
}

async function loadFiles(page = 1) {
  loading.value = true;
  try {
    const r = await getSpaceFileList({
      folder_id: currentFolderId.value,
      keyword: keyword.value || undefined,
      page_no: page,
      page_size: 50,
    });
    files.value = r.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

function pickFolder(id: number | null) {
  currentFolderId.value = id;
  selected.value = [];
  loadFiles(1);
}

function confirmPick() {
  emit(
    "confirm",
    selected.value.map((s) => ({ file_id: s.id, name: s.name, file_type: s.file_type }))
  );
  emit("update:visible", false);
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      selected.value = [];
      loadTree();
      loadFiles(1);
    }
  }
);
</script>

<style lang="scss" scoped>
.space-picker {
  display: flex;
  gap: var(--el-margin-base, 12px);
  min-height: 360px;
}

.space-picker-side {
  flex-shrink: 0;
  width: 200px;
  padding-right: 8px;
  overflow: auto;
  border-right: 1px solid var(--el-border-color-lighter);
}

.space-picker-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.space-picker-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.space-picker-name {
  color: var(--el-text-color-primary);
}

.space-picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.space-picker-count {
  color: var(--el-text-color-secondary);
}
</style>
