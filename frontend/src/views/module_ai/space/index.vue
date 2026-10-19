<!-- AI 个人工作空间：左侧文件夹树 + 右侧文件列表（上传/预览/下载/移动/删除） -->
<template>
  <div class="app-container ai-space-page">
    <div class="space-layout">
      <!-- 左：文件夹树 -->
      <el-card shadow="never" class="space-side">
        <template #header>
          <div class="space-side-head">
            <span>文件夹</span>
            <el-button
              v-hasPerm="'module_ai:space:manage'"
              link
              type="primary"
              :icon="Plus"
              @click="openFolderCreate(null)"
            />
          </div>
        </template>
        <el-tree
          :data="treeData"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="currentFolderId ?? undefined"
          highlight-current
          :expand-on-click-node="false"
          @node-click="onFolderClick"
        >
          <template #default="{ data }">
            <span class="space-tree-node">
              <el-icon class="space-tree-icon"><Folder /></el-icon>
              <span class="space-tree-label">{{ data.name }}</span>
              <el-dropdown trigger="click" @command="(c: string) => onFolderCmd(data, c)">
                <el-icon class="space-tree-more" @click.stop><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="addchild">新建子文件夹</el-dropdown-item>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item
                      command="delete"
                      style="color: var(--el-color-danger)"
                      divided
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </template>
        </el-tree>
      </el-card>

      <!-- 右：文件区 -->
      <el-card shadow="never" class="space-main">
        <div class="space-toolbar">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>
              <el-button link type="primary" @click="onFolderClick(null)">全部文件</el-button>
            </el-breadcrumb-item>
            <el-breadcrumb-item v-for="f in breadcrumb" :key="f.id">
              <el-button link type="primary" @click="onFolderClick(f.id)">{{ f.name }}</el-button>
            </el-breadcrumb-item>
          </el-breadcrumb>
          <div class="space-toolbar-right">
            <el-input
              v-model="keyword"
              placeholder="搜索文件名"
              clearable
              :prefix-icon="Search"
              style="width: 200px"
              @keyup.enter="loadFiles(1)"
              @clear="loadFiles(1)"
            />
            <el-select
              v-model="typeFilter"
              placeholder="类型"
              clearable
              style="width: 120px"
              @change="loadFiles(1)"
            >
              <el-option
                v-for="t in typeOptions"
                :key="t.value"
                :label="t.label"
                :value="t.value"
              />
            </el-select>
            <el-upload
              v-hasPerm="'module_ai:space:upload'"
              :show-file-list="false"
              :multiple="true"
              :http-request="doUpload"
            >
              <el-button type="primary" :icon="Upload">上传文件</el-button>
            </el-upload>
          </div>
        </div>

        <div class="space-quota">
          <span class="space-quota-label">空间用量</span>
          <el-progress
            :percentage="quotaPercent"
            :stroke-width="10"
            :status="quotaPercent >= 100 ? 'exception' : undefined"
            class="space-quota-bar"
          />
          <span class="space-quota-text">{{ quotaText }}</span>
        </div>

        <el-table
          v-loading="loading"
          :data="files"
          empty-text="当前目录暂无文件"
          @selection-change="(rows: SpaceFileItem[]) => (selectedIds = rows.map((r) => r.id))"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column label="名称" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="space-file-name" @click="openPreview(row)">
                <el-icon class="space-file-icon">
                  <component :is="fileIcon(row.file_type)" />
                </el-icon>
                <span>{{ row.name }}</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ typeLabel(row.file_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100" align="right">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="来源" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.source === 'agent' ? 'success' : 'info'"
                effect="plain"
              >
                {{ row.source === "agent" ? "AI 生成" : "用户上传" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updated_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openPreview(row)">预览</el-button>
              <el-button
                v-hasPerm="'module_ai:space:download'"
                size="small"
                link
                type="primary"
                @click="downloadFile(row)"
              >
                下载
              </el-button>
              <el-button
                v-hasPerm="'module_ai:space:manage'"
                size="small"
                link
                type="primary"
                @click="openRename(row)"
              >
                重命名
              </el-button>
              <el-button
                v-hasPerm="'module_ai:space:manage'"
                size="small"
                link
                type="primary"
                @click="openMove(row)"
              >
                移动
              </el-button>
              <el-button
                v-hasPerm="'module_ai:space:delete'"
                size="small"
                link
                type="danger"
                @click="deleteFiles([row.id], row.name)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="space-table-footer">
          <div>
            <el-button
              v-if="selectedIds.length"
              v-hasPerm="'module_ai:space:delete'"
              size="small"
              type="danger"
              plain
              :icon="Delete"
              @click="deleteFiles(selectedIds, `${selectedIds.length} 个文件`)"
            >
              删除选中（{{ selectedIds.length }}）
            </el-button>
          </div>
          <el-pagination
            v-model:current-page="pageNo"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next, total"
            @current-change="loadFiles()"
          />
        </div>
      </el-card>
    </div>

    <!-- 新建/重命名文件夹 -->
    <el-dialog v-model="folderDialogVisible" :title="folderDialogTitle" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="folderName" placeholder="请输入文件夹名称" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFolder">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重命名文件 -->
    <el-dialog v-model="renameVisible" title="重命名文件" width="420px">
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="文件名">
          <el-input v-model="renameName" placeholder="请输入文件名（含扩展名）" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="submitRename">确定</el-button>
      </template>
    </el-dialog>

    <!-- 移动文件 -->
    <el-dialog v-model="moveVisible" title="移动到文件夹" width="420px">
      <el-tree
        :data="treeData"
        node-key="id"
        :props="{ label: 'name', children: 'children' }"
        highlight-current
        :expand-on-click-node="false"
        @node-click="(d: any) => (moveTarget = d.id)"
      />
      <template #footer>
        <el-button @click="moveVisible = false">取消</el-button>
        <el-button type="primary" :disabled="moveTarget == null" @click="submitMove">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 文件预览 -->
    <el-dialog v-model="previewVisible" :title="previewName" width="760px" append-to-body>
      <div v-loading="previewLoading" class="space-preview">
        <img
          v-if="previewKind === 'image' && previewImageUrl"
          :src="previewImageUrl"
          class="space-preview-img"
        />
        <VuePdfEmbed v-else-if="previewKind === 'pdf' && previewPdfUrl" :source="previewPdfUrl" />
        <div v-else-if="previewKind === 'docx'" class="space-preview-html" v-html="previewHtml" />
        <div v-else class="space-preview-text">{{ previewContent || "（空文档）" }}</div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Delete,
  Document,
  Folder,
  MoreFilled,
  Picture,
  Plus,
  Search,
  Upload,
  VideoPlay,
  Headset,
} from "@element-plus/icons-vue";
import VuePdfEmbed from "vue-pdf-embed";
import mammoth from "mammoth";

import {
  createSpaceFolder,
  deleteSpaceFiles,
  deleteSpaceFolder,
  downloadSpaceFile,
  getSpaceFileList,
  getSpaceFolderTree,
  getSpaceQuota,
  moveSpaceFile,
  previewSpaceFile,
  renameSpaceFile,
  updateSpaceFolder,
  uploadSpaceFile,
  type SpaceFileItem,
  type SpaceFolder,
} from "@/api/module_ai/space";

// ---------------------------------------------------------------- 状态
const treeData = ref<SpaceFolder[]>([]);
const currentFolderId = ref<number | null>(null);
const breadcrumb = ref<SpaceFolder[]>([]);
const keyword = ref("");
const typeFilter = ref("");
const loading = ref(false);

const files = ref<SpaceFileItem[]>([]);
const total = ref(0);
const pageNo = ref(1);
const pageSize = ref(20);
const selectedIds = ref<number[]>([]);

const quotaUsed = ref(0);
const quotaTotal = ref(1);
const quotaPercent = computed(() =>
  quotaTotal.value ? Math.min(100, Math.round((quotaUsed.value / quotaTotal.value) * 100)) : 0
);
const quotaText = computed(
  () => `${formatSize(quotaUsed.value)} / ${formatSize(quotaTotal.value)}`
);

const typeOptions = [
  { value: "image", label: "图片" },
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "文档" },
  { value: "txt", label: "文本" },
  { value: "md", label: "Markdown" },
  { value: "csv", label: "CSV" },
  { value: "json", label: "JSON" },
  { value: "video", label: "视频" },
  { value: "audio", label: "音频" },
];

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

// ---------------------------------------------------------------- 工具
function formatSize(bytes: number): string {
  if (bytes == null || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatTime(t?: string): string {
  if (!t) return "—";
  return String(t).replace("T", " ").slice(0, 19);
}

function typeLabel(ft: string): string {
  return typeLabels[ft] || ft || "其他";
}

function fileIcon(ft: string) {
  if (ft === "image") return Picture;
  if (ft === "video") return VideoPlay;
  if (ft === "audio") return Headset;
  return Document;
}

function findBreadcrumb(
  nodes: SpaceFolder[],
  id: number | null,
  trail: SpaceFolder[] = []
): SpaceFolder[] {
  if (id == null) return trail;
  for (const n of nodes) {
    const next = [...trail, n];
    if (n.id === id) return next;
    const hit = findBreadcrumb(n.children || [], id, next);
    if (hit.length) return hit;
  }
  return [];
}

// ---------------------------------------------------------------- 加载
async function loadTree() {
  const r = await getSpaceFolderTree();
  treeData.value = r.data?.data || [];
  breadcrumb.value = findBreadcrumb(treeData.value, currentFolderId.value);
}

async function loadFiles(page = pageNo.value) {
  loading.value = true;
  try {
    const r = await getSpaceFileList({
      folder_id: currentFolderId.value,
      keyword: keyword.value || undefined,
      file_type: typeFilter.value || undefined,
      page_no: page,
      page_size: pageSize.value,
    });
    files.value = r.data?.data?.items || [];
    total.value = r.data?.data?.total || 0;
    pageNo.value = page;
  } finally {
    loading.value = false;
  }
}

async function loadQuota() {
  try {
    const r = await getSpaceQuota();
    const q = r.data?.data;
    if (q) {
      quotaUsed.value = q.used_bytes;
      quotaTotal.value = q.quota_bytes;
    }
  } catch {
    // 配额加载失败不阻断页面
  }
}

async function refreshAll() {
  await Promise.all([loadTree(), loadFiles(pageNo.value), loadQuota()]);
}

onMounted(refreshAll);

// ---------------------------------------------------------------- 文件夹操作
function onFolderClick(id: number | null) {
  currentFolderId.value = id;
  breadcrumb.value = findBreadcrumb(treeData.value, id);
  loadFiles(1);
}

const folderDialogVisible = ref(false);
const folderDialogTitle = ref("");
const folderMode = ref<"create" | "rename">("create");
const folderIdForRename = ref<number | null>(null);
const folderParentForCreate = ref<number | null>(null);
const folderName = ref("");

function openFolderCreate(parentId: number | null) {
  folderMode.value = "create";
  folderDialogTitle.value = "新建文件夹";
  folderParentForCreate.value = parentId;
  folderName.value = "";
  folderDialogVisible.value = true;
}

function openFolderRename(row: any) {
  folderMode.value = "rename";
  folderDialogTitle.value = "重命名文件夹";
  folderIdForRename.value = row.id;
  folderName.value = row.name;
  folderDialogVisible.value = true;
}

async function onFolderCmd(row: any, cmd: string) {
  if (cmd === "addchild") openFolderCreate(row.id);
  else if (cmd === "rename") openFolderRename(row);
  else if (cmd === "delete") {
    const count = await countFilesInTree(row);
    try {
      await ElMessageBox.confirm(
        `将删除文件夹「${row.name}」及其全部子文件夹，共 ${count} 个文件，且不可恢复。`,
        "删除文件夹",
        { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
      );
    } catch {
      return;
    }
    try {
      await deleteSpaceFolder(row.id);
      ElMessage.success("已删除");
      if (currentFolderId.value === row.id) onFolderClick(null);
      await refreshAll();
    } catch (e: any) {
      ElMessage.error(e?.message || "删除失败");
    }
  }
}

// 统计树内文件数（前端本地估算，确认文案用）
async function countFilesInTree(row: any): Promise<number> {
  const r = await getSpaceFileList({ folder_id: row.id, page_size: 1 });
  return r.data?.data?.total || 0;
}

async function submitFolder() {
  const name = folderName.value.trim();
  if (!name) {
    ElMessage.warning("请输入文件夹名称");
    return;
  }
  try {
    if (folderMode.value === "create") {
      await createSpaceFolder({ name, parent_id: folderParentForCreate.value });
      ElMessage.success("创建成功");
    } else if (folderIdForRename.value != null) {
      await updateSpaceFolder(folderIdForRename.value, { name });
      ElMessage.success("修改成功");
    }
    folderDialogVisible.value = false;
    await refreshAll();
  } catch (e: any) {
    ElMessage.error(e?.message || "操作失败");
  }
}

// ---------------------------------------------------------------- 上传
async function doUpload(options: any) {
  const file: File = options.file;
  try {
    await uploadSpaceFile(file, currentFolderId.value);
    ElMessage.success(`已上传 ${file.name}`);
    await Promise.all([loadFiles(1), loadQuota()]);
  } catch (e: any) {
    ElMessage.error(e?.message || "上传失败");
  } finally {
    options.onSuccess?.();
  }
}

// ---------------------------------------------------------------- 文件操作
async function downloadFile(row: any) {
  try {
    const r: any = await downloadSpaceFile(row.id);
    const blob = r.data instanceof Blob ? r.data : new Blob([r.data]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = row.name || "file";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e: any) {
    ElMessage.error(e?.message || "下载失败");
  }
}

const renameVisible = ref(false);
const renameId = ref<number | null>(null);
const renameName = ref("");

function openRename(row: any) {
  renameId.value = row.id;
  renameName.value = row.name;
  renameVisible.value = true;
}

async function submitRename() {
  const name = renameName.value.trim();
  if (!name || renameId.value == null) {
    ElMessage.warning("请输入文件名");
    return;
  }
  try {
    await renameSpaceFile({ file_id: renameId.value, name });
    ElMessage.success("修改成功");
    renameVisible.value = false;
    await loadFiles(pageNo.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "操作失败");
  }
}

const moveVisible = ref(false);
const moveFileId = ref<number | null>(null);
const moveTarget = ref<number | null>(null);

function openMove(row: any) {
  moveFileId.value = row.id;
  moveTarget.value = null;
  moveVisible.value = true;
}

async function submitMove() {
  if (moveFileId.value == null || moveTarget.value == null) return;
  try {
    await moveSpaceFile({ file_id: moveFileId.value, folder_id: moveTarget.value });
    ElMessage.success("移动成功");
    moveVisible.value = false;
    await loadFiles(pageNo.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "移动失败");
  }
}

async function deleteFiles(ids: number[], label: string) {
  try {
    await ElMessageBox.confirm(`将删除 ${label}（共 ${ids.length} 个），且不可恢复。`, "删除文件", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  try {
    const r = await deleteSpaceFiles(ids);
    ElMessage.success(`已删除 ${r.data?.data?.deleted ?? ids.length} 个文件`);
    selectedIds.value = [];
    await Promise.all([loadFiles(1), loadQuota()]);
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
}

// ---------------------------------------------------------------- 预览
const previewVisible = ref(false);
const previewName = ref("");
const previewKind = ref("text");
const previewContent = ref("");
const previewHtml = ref("");
const previewImageUrl = ref("");
const previewPdfUrl = ref("");
const previewLoading = ref(false);

async function openPreview(row: any) {
  previewVisible.value = true;
  previewName.value = row.name;
  previewContent.value = "";
  previewHtml.value = "";
  previewImageUrl.value = "";
  previewPdfUrl.value = "";
  previewLoading.value = true;
  const ft = (row.file_type || "").toLowerCase();
  try {
    if (ft === "image" || ft === "pdf" || ft === "docx") {
      previewKind.value = ft;
      const r: any = await downloadSpaceFile(row.id);
      const blob = r.data instanceof Blob ? r.data : new Blob([r.data]);
      if (ft === "image") {
        previewImageUrl.value = URL.createObjectURL(blob);
      } else if (ft === "pdf") {
        previewPdfUrl.value = URL.createObjectURL(blob);
      } else {
        const ab = await blob.arrayBuffer();
        const res = await mammoth.convertToHtml({ arrayBuffer: ab });
        previewHtml.value = res.value || "";
      }
    } else {
      previewKind.value = "text";
      const r = await previewSpaceFile(row.id);
      previewContent.value = r.data?.data?.content || "";
    }
  } catch (e: any) {
    previewKind.value = "text";
    previewContent.value = "";
    ElMessage.error(e?.message || "预览失败");
  } finally {
    previewLoading.value = false;
  }
}
</script>

<style lang="scss" scoped>
.ai-space-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.space-layout {
  display: flex;
  flex: 1;
  gap: var(--el-margin-base, 12px);
  min-height: 0;
}

.space-side {
  flex-shrink: 0;
  width: 240px;
  overflow: auto;
}

.space-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.space-tree-node {
  display: flex;
  gap: 4px;
  align-items: center;
  padding-right: 8px;
}

.space-tree-icon {
  color: var(--el-color-info);
}

.space-tree-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-tree-more {
  opacity: 0;
  transition: opacity 0.2s;
}

.space-tree-node:hover .space-tree-more {
  opacity: 1;
}

.space-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.space-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.space-toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.space-quota {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 8px 0 4px;
}

.space-quota-label {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.space-quota-bar {
  flex: 1;
}

.space-quota-text {
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.space-file-name {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: var(--el-color-primary);
  cursor: pointer;
}

.space-file-icon {
  color: var(--el-text-color-secondary);
}

.space-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.space-preview {
  min-height: 200px;
  max-height: 60vh;
  overflow: auto;
}

.space-preview-img {
  max-width: 100%;
}

.space-preview-text {
  color: var(--el-text-color-primary);
  word-break: break-all;
  white-space: pre-wrap;
}

.space-preview-html {
  :deep(img) {
    max-width: 100%;
  }
}
</style>
