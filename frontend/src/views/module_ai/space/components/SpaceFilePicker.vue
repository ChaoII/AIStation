<!-- 个人空间文件选择器：弹窗内「左侧文件夹树 + 右侧文件表」，供助手对话引用空间文件 -->
<template>
  <el-dialog
    :model-value="visible"
    title="从个人空间选择文件"
    width="900px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="space-picker">
      <div class="space-picker-side">
        <div class="space-picker-side-head">
          <span>文件夹</span>
          <el-button link type="primary" :icon="FolderOpened" @click="pickFolder(null)">
            全部
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
          placeholder="搜索文件名"
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
          empty-text="该文件夹暂无文件"
          @selection-change="(rows: any[]) => (selected = rows)"
        >
          <el-table-column type="selection" width="40" :selectable="() => !!props.multiple" />
          <el-table-column label="名称" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="space-picker-name">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ typeLabel(row.file_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="90" align="right">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
        </el-table>
        <div class="space-picker-footer">
          <span class="space-picker-count">已选 {{ selected.length }} 个</span>
          <el-button type="primary" :disabled="!selected.length" @click="confirmPick">
            确定引用
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
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

const treeData = ref<SpaceFolder[]>([]);
const currentFolderId = ref<number | null>(null);
const keyword = ref("");
const files = ref<SpaceFileItem[]>([]);
const selected = ref<SpaceFileItem[]>([]);
const loading = ref(false);

const typeLabels: Record<string, string> = {
  image: "图片",
  pdf: "PDF",
  docx: "文档",
  txt: "文本",
  md: "MD",
  csv: "CSV",
  json: "JSON",
  video: "视频",
  audio: "音频",
  other: "其他",
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
  return typeLabels[ft] || ft || "其他";
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
