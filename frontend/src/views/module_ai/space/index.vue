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
            <el-dropdown
              class="space-tree-menu"
              trigger="contextmenu"
              @command="(c: string) => onFolderCmd(data, c)"
            >
              <span class="space-tree-node">
                <el-icon class="space-tree-icon"><Folder /></el-icon>
                <span class="space-tree-label">{{ data.name }}</span>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="addchild">新建文件夹</el-dropdown-item>
                  <el-dropdown-item command="upload">上传文件到此</el-dropdown-item>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="delete" style="color: var(--el-color-danger)" divided>
                    删除
                  </el-dropdown-item>
                  <el-dropdown-item command="refresh">刷新</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
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
            <!-- 用量：放在搜索框旁（进度条 + 已用/总量 + 申请扩容） -->
            <div class="space-quota-inline">
              <el-progress
                :percentage="quotaPercent"
                :stroke-width="8"
                :status="quotaPercent >= 100 ? 'exception' : undefined"
                class="space-quota-bar"
              />
              <span class="space-quota-text">{{ quotaText }}</span>
              <el-button
                v-hasPerm="'module_ai:space:query'"
                link
                type="primary"
                @click="openQuotaDialog"
              >
                申请扩容
              </el-button>
            </div>
            <el-input
              v-model="keyword"
              placeholder="搜索个人空间文件…"
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

        <!-- 拖拽上传区（Element Plus 原生 drag） -->
        <el-upload
          v-hasPerm="'module_ai:space:upload'"
          class="space-drop"
          drag
          :show-file-list="false"
          :multiple="true"
          :http-request="doUpload"
        >
          <div class="space-drop-inner">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="space-drop-text">
              将文件拖到此处，或
              <em>点击上传</em>
            </div>
            <div class="space-drop-tip">单个文件不超过 {{ formatSize(maxFileBytes) }}</div>
          </div>
        </el-upload>

        <!-- 右键「上传文件到此」用的隐藏文件输入 -->
        <input
          ref="hiddenUploadInput"
          type="file"
          multiple
          style="display: none"
          @change="onHiddenUploadChange"
        />

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

    <!-- 申请扩容 -->
    <el-dialog v-model="quotaDialogVisible" title="申请扩容" width="560px">
      <div class="quota-current">
        <span>当前配额：{{ formatQuotaSize(quotaTotal) }}</span>
        <span>已用：{{ formatQuotaSize(quotaUsed) }}</span>
      </div>
      <el-form v-if="!quotaHasPending" label-width="90px" class="quota-form" @submit.prevent>
        <el-form-item label="目标配额">
          <el-input-number
            v-model="quotaTargetGb"
            :min="quotaTargetMinGb"
            :step="1"
            :precision="0"
          />
          <span class="quota-unit">GB</span>
        </el-form-item>
        <el-form-item label="申请理由">
          <el-input
            v-model="quotaReason"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="请说明申请扩容的原因，如：需要存储更多模型训练产物。"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="quotaHasPending"
        type="info"
        :closable="false"
        show-icon
        title="您已有一笔待审核的扩容申请，请耐心等待管理员处理。"
      />
      <div class="quota-mine">
        <div class="quota-mine-title">我的申请</div>
        <el-table
          v-loading="quotaMineLoading"
          :data="quotaMine"
          size="small"
          empty-text="暂无申请记录"
        >
          <el-table-column label="目标配额" width="110">
            <template #default="{ row }">
              {{ formatQuotaSize(row.target_mb * 1024 * 1024) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="quotaStatusType(row.status)" effect="plain">
                {{ quotaStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="申请时间" width="150">
            <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
          </el-table-column>
          <el-table-column label="审核备注" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.review_note || "—" }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="quotaDialogVisible = false">关闭</el-button>
        <el-button
          v-if="!quotaHasPending"
          type="primary"
          :loading="quotaSubmitting"
          @click="submitQuotaRequest"
        >
          提交申请
        </el-button>
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
  Picture,
  Plus,
  Search,
  Upload,
  UploadFilled,
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
  getMySpaceQuotaRequests,
  getSpaceFileList,
  getSpaceFolderTree,
  getSpaceQuota,
  moveSpaceFile,
  previewSpaceFile,
  renameSpaceFile,
  submitSpaceQuotaRequest,
  updateSpaceFolder,
  uploadSpaceFile,
  type SpaceFileItem,
  type SpaceFolder,
  type SpaceQuotaRequest,
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
const maxFileBytes = ref(0);
const quotaHasPending = ref(false);
const quotaPercent = computed(() =>
  quotaTotal.value ? Math.min(100, Math.round((quotaUsed.value / quotaTotal.value) * 100)) : 0
);
const quotaText = computed(
  () => `${formatQuotaSize(quotaUsed.value)} / ${formatQuotaSize(quotaTotal.value)}`
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

// 配额/用量展示用 2 位小数，匹配「62.86 MB / 2.00 GB」样式
function formatQuotaSize(bytes: number): string {
  if (bytes == null || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return i === 0 ? `${bytes} B` : `${v.toFixed(2)} ${units[i]}`;
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
      maxFileBytes.value = q.max_file_bytes;
      quotaHasPending.value = q.has_pending_request;
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
  else if (cmd === "refresh") await loadTree();
  else if (cmd === "upload") triggerUploadTo(row.id);
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
const uploadTargetFolderId = ref<number | null>(null);
const hiddenUploadInput = ref<HTMLInputElement | null>(null);

async function performUploadFile(file: File, folderId: number | null) {
  try {
    await uploadSpaceFile(file, folderId);
    ElMessage.success(`已上传 ${file.name}`);
    await Promise.all([loadFiles(1), loadQuota()]);
  } catch (e: any) {
    ElMessage.error(e?.message || "上传失败");
  }
}

async function doUpload(options: any) {
  await performUploadFile(options.file, currentFolderId.value);
  options.onSuccess?.();
}

// 右键「上传文件到此」：记录目标文件夹并触发文件选择
function triggerUploadTo(folderId: number | null) {
  uploadTargetFolderId.value = folderId;
  hiddenUploadInput.value?.click();
}

function onHiddenUploadChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const files = input.files;
  if (files && files.length) {
    const folderId = uploadTargetFolderId.value;
    for (const f of Array.from(files)) performUploadFile(f, folderId);
  }
  input.value = "";
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

// ---------------------------------------------------------------- 申请扩容
const quotaDialogVisible = ref(false);
const quotaTargetGb = ref(5);
const quotaReason = ref("");
const quotaSubmitting = ref(false);
const quotaMine = ref<SpaceQuotaRequest[]>([]);
const quotaMineLoading = ref(false);

const quotaTargetMinGb = computed(() =>
  Math.max(1, Math.ceil(quotaTotal.value / 1024 / 1024 / 1024))
);

function quotaStatusLabel(s: string): string {
  if (s === "approved") return "已通过";
  if (s === "rejected") return "已驳回";
  return "待审核";
}

function quotaStatusType(s: string): "success" | "danger" | "info" {
  if (s === "approved") return "success";
  if (s === "rejected") return "danger";
  return "info";
}

async function loadQuotaMine() {
  quotaMineLoading.value = true;
  try {
    const r = await getMySpaceQuotaRequests();
    quotaMine.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || "加载申请记录失败");
  } finally {
    quotaMineLoading.value = false;
  }
}

async function openQuotaDialog() {
  quotaDialogVisible.value = true;
  quotaTargetGb.value = quotaTargetMinGb.value + 1;
  quotaReason.value = "";
  await loadQuotaMine();
  quotaHasPending.value = quotaMine.value.some((r) => r.status === "pending");
}

async function submitQuotaRequest() {
  const targetMb = Math.round(quotaTargetGb.value * 1024);
  const currentMb = quotaTotal.value / 1024 / 1024;
  if (targetMb <= currentMb) {
    ElMessage.warning(`目标配额需大于当前 ${formatQuotaSize(quotaTotal.value)}`);
    return;
  }
  if (!quotaReason.value.trim()) {
    ElMessage.warning("请填写申请理由");
    return;
  }
  quotaSubmitting.value = true;
  try {
    const r = await submitSpaceQuotaRequest({
      target_mb: targetMb,
      reason: quotaReason.value.trim(),
    });
    ElMessage.success(r.data?.data?.msg || "申请已提交");
    await loadQuotaMine();
    await loadQuota();
    quotaHasPending.value = true;
  } catch (e: any) {
    ElMessage.error(e?.message || "提交失败");
  } finally {
    quotaSubmitting.value = false;
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

.space-tree-menu {
  display: flex;
  flex: 1;
  width: 100%;
  min-width: 0;
}

.space-tree-node {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
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

.space-quota-inline {
  display: flex;
  gap: 6px;
  align-items: center;
}

.space-quota-bar {
  width: 90px;
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

.space-drop {
  margin-top: 4px;
  :deep(.el-upload) {
    width: 100%;
  }
  :deep(.el-upload-dragger) {
    padding: 12px;
    border: 1px dashed var(--el-border-color);
    border-radius: var(--el-border-radius-base);
    &:hover {
      border-color: var(--el-color-primary);
    }
  }
}

.space-drop-inner {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  color: var(--el-text-color-secondary);
}

.space-drop-text {
  font-size: var(--el-font-size-base, 14px);
  em {
    color: var(--el-color-primary);
    font-style: normal;
  }
}

.space-drop-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.quota-current {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
}

.quota-form {
  margin-bottom: 16px;
}

.quota-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}

.quota-mine-title {
  margin-bottom: 8px;
}

.quota-mine {
  margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
</style>
