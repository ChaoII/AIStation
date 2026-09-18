<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <div class="data-table__toolbar--left">
          <CrudToolbarLeft
            :remove-ids="removeIds"
            :perm-create="['module_annotation:dataset:create']"
            :perm-delete="['module_annotation:dataset:delete']"
            @add="handleOpenDialog('create')"
            @delete="onToolbar('delete')"
          />
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              min-width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              fixed
              label="序号"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="数据集名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              label="描述"
              prop="description"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'image_count')?.show"
              key="image_count"
              label="图片数"
              prop="image_count"
              width="90"
              align="center"
            >
              <template #default="scope">
                <el-tag type="primary" effect="plain" size="small">
                  {{ scope.row.image_count ?? 0 }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'tasks')?.show"
              key="tasks"
              label="关联标注任务"
              min-width="320"
            >
              <template #default="scope">
                <div v-if="scope.row.tasks?.length" style="display:flex;flex-wrap:wrap;gap:4px">
                  <div
                    v-for="t in scope.row.tasks" :key="t.id"
                    class="task-badge"
                    :style="{
                      borderColor: taskTagColor(t.task_type),
                      color: taskTagColor(t.task_type),
                    }"
                    @click="router.push(`/annotation/workbench/${t.id}`)"
                  >
                    <span class="task-badge-name">{{ t.name }}</span>
                    <span class="task-badge-pct">{{ t.progress ?? 0 }}%</span>
                    <span class="task-badge-fill" :style="{ width: (t.progress ?? 0) + '%', background: taskTagColor(t.task_type) + '22' }" />
                  </div>
                </div>
                <span v-else style="color:var(--el-text-color-secondary);font-size:12px">—</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'import_status')?.show"
              key="import_status"
              label="导入状态"
              width="130"
              align="center"
            >
              <template #default="scope">
                <el-popover
                  placement="left"
                  trigger="hover"
                  :width="270"
                  :disabled="!rowImport(scope.row)"
                >
                  <template #reference>
                    <el-tag :type="importTagType(scope.row)" size="small" effect="plain">
                      {{ importTagText(scope.row) }}
                    </el-tag>
                  </template>
                  <div class="import-pop">
                    <div class="import-pop-title">{{ importTagText(scope.row) }}</div>
                    <el-progress
                      :percentage="rowImportPercent(scope.row)"
                      :status="rowImportStatus(scope.row)"
                      :indeterminate="rowImport(scope.row)?.phase === 'scanning'"
                    />
                    <div class="import-pop-row">
                      已用 {{ fmtDuration(elapsedSec(rowImport(scope.row))) }}
                      <span v-if="rowImport(scope.row)?.total">
                        · {{ rowImport(scope.row)?.processed }}/{{ rowImport(scope.row)?.total }}
                      </span>
                    </div>
                    <div v-if="rowImport(scope.row)?.taskName" class="import-pop-row">
                      任务：{{ rowImport(scope.row)?.taskName }}
                    </div>
                    <div v-if="rowImport(scope.row)?.error" class="import-pop-row import-pop-err">
                      {{ rowImport(scope.row)?.error }}
                    </div>
                    <div class="import-pop-actions">
                      <el-button
                        v-if="isRunning(rowImport(scope.row))"
                        size="small"
                        link
                        type="primary"
                        @click="openImportFor(scope.row)"
                      >
                        查看进度
                      </el-button>
                      <el-button
                        v-if="rowImport(scope.row)?.taskId"
                        size="small"
                        link
                        type="success"
                        @click="router.push(`/annotation/workbench/${rowImport(scope.row)?.taskId}`)"
                      >
                        打开任务
                      </el-button>
                      <el-button
                        v-if="['failed', 'cancelled'].includes(rowImport(scope.row)?.phase || '')"
                        size="small"
                        link
                        type="warning"
                        @click="retryImport(scope.row)"
                      >
                        重试
                      </el-button>
                    </div>
                  </div>
                </el-popover>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              label="创建时间"
              prop="created_time"
              min-width="170"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="240"
            >
              <template #default="scope">
                <el-button
                  type="primary"
                  size="small"
                  link
                  icon="Picture"
                  @click="handleOpenImages(scope.row)"
                >
                  图片
                </el-button>
                <el-button
                  v-hasPerm="['module_annotation:dataset:upload']"
                  type="success"
                  size="small"
                  link
                  icon="Upload"
                  @click="handleOpenUpload(scope.row)"
                >
                  上传
                </el-button>
                <el-button
                  v-hasPerm="['module_annotation:dataset:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-dropdown trigger="click" @command="(cmd: string) => handleMoreCommand(cmd, scope.row)">
                  <el-button size="small" link>
                    更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="import">导入标注</el-dropdown-item>
                      <el-dropdown-item command="export">导出</el-dropdown-item>
                      <el-dropdown-item command="exportHistory">导出历史</el-dropdown-item>
                      <el-dropdown-item command="clean">数据清洗</el-dropdown-item>
                      <el-dropdown-item command="train">去训练</el-dropdown-item>
                      <el-dropdown-item v-hasPerm="['module_annotation:dataset:delete']" command="delete" divided>删除</el-dropdown-item>
                      <el-dropdown-item v-hasPerm="['module_annotation:dataset:purge']" command="purge" divided>彻底删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="550px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="100px"
        size="default"
      >
        <el-form-item label="数据集名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入数据集名称" :maxlength="100" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            :maxlength="500"
            show-word-limit
            placeholder="请输入描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <EnhancedDialog
      v-model="uploadVisible"
      title="上传图片"
      append-to-body
      width="500px"
      @close="handleCloseUpload"
    >
      <el-alert
        title="支持 JPG / PNG / BMP 格式，可多选文件"
        type="info"
        :closable="false"
        show-icon
        class="upload-alert"
      />
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        multiple
        drag
        accept="image/jpeg,image/png,image/bmp"
        :file-list="fileList"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        list-type="picture-card"
      >
        <el-icon size="32"><Plus /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或
          <em>点击选择</em>
        </div>
      </el-upload>
      <template #footer>
        <el-button @click="handleCloseUpload">取消</el-button>
        <el-button type="primary" :loading="uploadLoading" @click="handleUploadSubmit">
          开始上传
        </el-button>
      </template>
    </EnhancedDialog>

    <!-- X-AnyLabeling 导入（三段进度 + 可关闭后台继续） -->
    <el-dialog
      v-model="importDialogVisible"
      :title="`导入标注到「${importDatasetName}」`"
      width="560px"
      :close-on-click-modal="false"
      :before-close="handleImportDialogClose"
      @closed="onImportDialogClosed"
    >
      <el-steps :active="importStep" simple class="import-steps">
        <el-step title="上传 ZIP" />
        <el-step title="服务端解析" />
        <el-step title="导入图片" />
      </el-steps>

      <div v-if="!dialogImport" class="import-picker">
        <el-upload
          ref="importUploadRef"
          :auto-upload="false"
          accept=".zip"
          :limit="1"
          :on-change="onImportFileChange"
        >
          <el-button type="primary" icon="Upload">选择 ZIP 文件</el-button>
        </el-upload>
        <p class="import-hint">
          压缩包需包含图片与同名 .json 标注文件，大小不超过 {{ importMaxMb }}MB。
        </p>
        <p v-if="importFile" class="import-file">
          已选：<span class="import-file-name">{{ importFile.name }}</span>
          <span class="import-file-size">{{ importFileMb }} MB</span>
        </p>
      </div>

      <div v-else class="import-progress">
        <el-progress
          :percentage="dialogPercent"
          :status="dialogProgressStatus"
          :indeterminate="dialogIndeterminate"
          :stroke-width="14"
        />
        <div class="import-line import-line--primary">{{ dialogPhaseText }}</div>
        <div v-if="dialogDetailText" class="import-line">{{ dialogDetailText }}</div>
        <div class="import-line import-line--muted">
          <span>已用 {{ fmtDuration(dialogElapsed) }}</span>
          <span>{{ dialogEtaText }}</span>
        </div>
        <el-alert
          v-if="dialogImport?.error"
          :title="dialogImport.error"
          type="error"
          :closable="false"
          show-icon
          class="import-alert"
        />
        <el-alert
          v-else-if="dialogImport?.phase === 'done'"
          type="success"
          :closable="false"
          show-icon
          class="import-alert"
        >
          <template #title>
            导入完成：{{ dialogImport.imported }} 张图片，{{ dialogImport.totalAnnotations }} 个标注
          </template>
        </el-alert>
      </div>

      <template #footer>
        <div class="import-footer">
          <el-button
            v-if="['uploading', 'scanning'].includes(dialogImport?.phase || '')"
            type="danger"
            plain
            @click="cancelImport"
          >
            取消上传
          </el-button>
          <el-button @click="requestCloseImport">
            {{ isRunningImport ? "后台继续" : "关闭" }}
          </el-button>
          <el-button
            v-if="!isRunningImport && dialogImport?.phase !== 'done'"
            type="warning"
            :disabled="!importFile"
            @click="handleImportSubmit"
          >
            {{ dialogImport ? "重试" : "开始导入" }}
          </el-button>
          <el-button
            v-else-if="dialogImport?.phase === 'done' && dialogImport.taskId"
            type="primary"
            @click="goImportTask"
          >
            打开标注任务
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Export Dialog -->
    <el-dialog v-model="exportDialogVisible" title="导出数据集" width="500px" :close-on-click-modal="!exporting" :close-on-press-escape="!exporting" :show-close="!exporting">
      <el-form label-width="120px">
        <el-form-item label="数据集"><span>{{ exportDatasetName }}</span></el-form-item>
        <el-form-item label="标注任务" required>
          <el-select v-model="exportTaskId" placeholder="请选择标注任务" filterable style="width:100%" @change="onTaskChange">
            <el-option v-for="t in exportRowTasks" :key="t.id" :value="t.id" :label="`${t.name}（${taskTypeLabel(t.task_type)}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="导出格式" required>
          <el-select v-model="exportFormat" style="width:100%">
            <el-option v-for="opt in filteredExportFormats" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
          <div v-if="exportFormat === 'paddle-ocr'" style="margin-top:8px">
            <el-checkbox v-model="ocrExportDet" label="导出检测数据集 (det)" border size="small" style="margin-right:8px" />
            <el-checkbox v-model="ocrExportRec" label="导出识别数据集 (rec)" border size="small" />
          </div>
        </el-form-item>
        <el-form-item v-if="isYoloOrPaddleFormat" label="训练集比例">
          <el-slider v-model="trainRatio" :min="50" :max="95" :step="5" show-input style="width:200px" />
          <span style="margin-left:8px;font-size:12px;color:#909399">剩余 {{ 100 - trainRatio }}% 为验证集</span>
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>将导出该数据集所有已标注图片和标注文件，打包为 ZIP 下载</template>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="exportDialogVisible = false" :disabled="exporting">取消</el-button>
        <el-button type="warning" :loading="exporting" @click="handleExportSubmit">{{ exporting ? "导出中..." : "导出并下载" }}</el-button>
      </template>
    </el-dialog>

    <ExportHistoryDrawer ref="exportHistoryRef" />
    <CleanDrawer ref="cleanRef" />
    <DatasetImageGrid
      v-model="gridVisible"
      :dataset-id="gridDatasetId"
      @open-workbench="handleOpenWorkbench"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { AnnotationAPI } from "@/api/module_annotation";
import type { ISearchConfig, IContentConfig, IObject } from "@/components/CURD/types";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import ExportHistoryDrawer from "@/components/Annotation/ExportHistoryDrawer.vue";
import CleanDrawer from "@/components/Annotation/CleanDrawer.vue";
import DatasetImageGrid from "@/components/Annotation/DatasetImageGrid.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import { ElLoading, ElMessage, ElMessageBox } from "element-plus";
import { WarningFilled } from "@element-plus/icons-vue";

const router = useRouter();

function taskTagType(t: string) {
  return ({ detection: "primary", rotated_detection: "warning", segmentation: "success", keypoint: "danger", ocr: "info", classification: "" } as any)[t] || "";
}
function taskTagColor(t: string) {
  return ({ detection: "#409eff", rotated_detection: "#e6a23c", segmentation: "#67c23a", keypoint: "#f56c6c", ocr: "#909399", classification: "#b37feb" } as any)[t] || "#909399";
}
function taskTypeLabel(t: string) {
  return ({ detection: "检测", rotated_detection: "旋转框", segmentation: "分割", keypoint: "关键点", ocr: "OCR", classification: "分类" } as any)[t] || t;
}

defineOptions({
  name: "Dataset",
  inheritAttrs: false,
});

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_annotation:dataset",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "数据集名称",
      type: "input",
      attrs: { placeholder: "请输入数据集名称", clearable: true },
    },
  ],
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "数据集名称", show: true },
  { prop: "description", label: "描述", show: true },
  { prop: "image_count", label: "图片数", show: true },
  { prop: "tasks", label: "关联标注任务", show: true },
  { prop: "import_status", label: "导入状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_annotation:dataset",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const p = params as IObject;
    if (typeof p.status === "string" && p.status !== "") {
      p.status = p.status === "true";
    }
    const res = await AnnotationAPI.getDatasetList(p);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await AnnotationAPI.deleteDataset(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: "提示",
    message: "确认删除所选数据集？可在保留期内恢复。",
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

// ── 图片网格 ──
const gridVisible = ref(false);
const gridDatasetId = ref<number | null>(null);
const gridRowTasks = ref<any[]>([]);

function handleOpenImages(row: any) {
  gridDatasetId.value = row.id;
  gridRowTasks.value = row.tasks || [];
  gridVisible.value = true;
}

function handleOpenWorkbench() {
  const task = gridRowTasks.value?.[0];
  if (!task) {
    ElMessage.warning("该数据集还没有标注任务，请先创建任务");
    return;
  }
  router.push(`/annotation/workbench/${task.id}`);
}

async function handlePurge(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认彻底删除数据集「${row.name}」？将删除全部图片、标注与导出产物，且不可恢复。`,
      "危险操作",
      { type: "error", confirmButtonText: "彻底删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const loading = ElLoading.service({
    text: "正在彻底删除（含对象存储）…",
    background: "rgba(0, 0, 0, 0.5)",
  });
  try {
    await AnnotationAPI.purgeDataset([row.id]);
    ElMessage.success("已彻底删除");
    refreshList();
  } catch (e: any) {
    ElMessage.error(e?.message || "彻底删除失败");
  } finally {
    loading.close();
  }
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: "",
  status: true,
  description: "",
});

const initialFormData = {
  id: undefined as number | undefined,
  name: "",
  status: true,
  description: "",
};

const rules = reactive({
  name: [{ required: true, message: "请输入数据集名称", trigger: "blur" }],
});

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑数据集";
    const res = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 1, id });
    const items = res.data.data.items;
    if (items && items.length > 0) {
      const item = items[0];
      formData.id = item.id;
      formData.name = item.name;
      formData.status = item.status;
      formData.description = item.description;
    }
  } else {
    dialogVisible.title = "新增数据集";
    Object.assign(formData, initialFormData);
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          await AnnotationAPI.updateDataset(id, {
            name: formData.name,
            description: formData.description,
          });
        } else {
          await AnnotationAPI.createDataset({
            name: formData.name,
            description: formData.description,
          });
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch {
        //
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

const uploadVisible = ref(false);
const uploadLoading = ref(false);
const uploadRef = ref();
const uploadDatasetId = ref<number | undefined>(undefined);
const fileList = ref<any[]>([]);

function handleOpenUpload(row: any) {
  uploadDatasetId.value = row.id;
  fileList.value = [];
  uploadVisible.value = true;
}

function handleCloseUpload() {
  uploadVisible.value = false;
  fileList.value = [];
}

function handleFileChange(_uploadFile: any, uploadFiles: any[]) {
  fileList.value = uploadFiles;
}

function handleFileRemove(_uploadFile: any, uploadFiles: any[]) {
  fileList.value = uploadFiles;
}

async function handleUploadSubmit() {
  if (!uploadDatasetId.value) return;
  if (fileList.value.length === 0) {
    ElMessage.warning("请选择需要上传的图片");
    return;
  }
  uploadLoading.value = true;
  try {
    const formData = new FormData();
    for (const file of fileList.value) {
      formData.append("files", file.raw);
    }
    await AnnotationAPI.uploadImages(uploadDatasetId.value, formData);
    uploadVisible.value = false;
    fileList.value = [];
    refreshList();
  } catch {
    /* 提示由请求拦截器统一处理 */
  } finally {
    uploadLoading.value = false;
  }
}

// ── 行内「更多」菜单 ──
function handleMoreCommand(cmd: string, row: any) {
  switch (cmd) {
    case "import":
      handleOpenImport(row);
      break;
    case "export":
      handleOpenExport(row);
      break;
    case "exportHistory":
      exportHistoryRef.value?.open(row.id);
      break;
    case "clean":
      cleanRef.value?.open(row.id);
      break;
    case "train":
      router.push(`/train/task?dataset_id=${row.id}&autoCreate=1`);
      break;
    case "delete":
      handleRowDelete(row.id);
      break;
    case "purge":
      handlePurge(row);
      break;
  }
}

// ── X-AnyLabeling 导入：页面级状态（弹窗关闭后仍在）+ 三段进度 ──
type ImportPhase =
  | "uploading"
  | "scanning"
  | "importing"
  | "done"
  | "failed"
  | "cancelled";

interface ActiveImport {
  jobId: string | null;
  phase: ImportPhase;
  uploadLoaded: number;
  uploadTotal: number;
  processed: number;
  total: number;
  imported: number;
  totalAnnotations: number;
  taskId: number | null;
  taskName: string;
  error: string;
  startedAt: number;
  fileName: string;
  fileSize: number;
  refreshed?: boolean;
}

const importDialogVisible = ref(false);
const importDatasetId = ref<number | null>(null);
const importDatasetName = ref("");
const importUploadRef = ref<any>(null);
const importFile = ref<File | null>(null);
const importMaxMb = 1024;
const activeImports = reactive<Record<number, ActiveImport>>({});
const nowTick = ref(Date.now());
let tickTimer: number | null = null;
let pollTimer: number | null = null;
let importAbort: AbortController | null = null;

const importFileMb = computed(() =>
  importFile.value ? (importFile.value.size / 1024 / 1024).toFixed(1) : "0"
);

function isRunningPhase(p?: string): boolean {
  return p === "uploading" || p === "scanning" || p === "importing";
}
function isRunning(a: any): boolean {
  return !!a && isRunningPhase(a.phase);
}
function phaseFromJob(job: any): ImportPhase {
  if (!job) return "failed";
  if (job.status === "done") return "done";
  if (job.status === "failed") return "failed";
  if (job.status === "cancelled") return "cancelled";
  if (job.phase === "import") return "importing";
  return "scanning";
}
function elapsedSec(a: any): number {
  if (!a?.startedAt) return 0;
  return Math.max(0, Math.floor((nowTick.value - a.startedAt) / 1000));
}
function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
function fmtMB(bytes: number): string {
  return (Math.max(0, bytes || 0) / 1024 / 1024).toFixed(1);
}
function startTicker() {
  if (tickTimer !== null) return;
  tickTimer = window.setInterval(() => {
    nowTick.value = Date.now();
  }, 1000);
}
function stopTickerIfIdle() {
  if (Object.values(activeImports).some((a) => isRunningPhase(a.phase))) return;
  if (tickTimer !== null) {
    window.clearInterval(tickTimer);
    tickTimer = null;
  }
}

function seedImport(dsId: number, job: any) {
  activeImports[dsId] = {
    jobId: job.job_id,
    phase: phaseFromJob(job),
    uploadLoaded: job.file_size || 0,
    uploadTotal: job.file_size || 0,
    processed: job.processed || 0,
    total: job.total || 0,
    imported: job.imported || 0,
    totalAnnotations: job.total_annotations || 0,
    taskId: job.task_id ?? null,
    taskName: job.task_name || "",
    error: job.error || "",
    startedAt: job.started_at ? job.started_at * 1000 : Date.now(),
    fileName: job.file_name || "",
    fileSize: job.file_size || 0,
  };
}

// 列表行统一取状态：优先本会话实时态，其次后端快照
function rowImport(row: any): ActiveImport | null {
  if (!row) return null;
  if (activeImports[row.id]) return activeImports[row.id];
  if (row.import) {
    const j = row.import;
    return {
      jobId: j.job_id,
      phase: phaseFromJob(j),
      uploadLoaded: j.file_size || 0,
      uploadTotal: j.file_size || 0,
      processed: j.processed || 0,
      total: j.total || 0,
      imported: j.imported || 0,
      totalAnnotations: j.total_annotations || 0,
      taskId: j.task_id ?? null,
      taskName: j.task_name || "",
      error: j.error || "",
      startedAt: j.started_at ? j.started_at * 1000 : Date.now(),
      fileName: j.file_name || "",
      fileSize: j.file_size || 0,
    };
  }
  return null;
}
function percentOf(a: ActiveImport | null): number {
  if (!a) return 0;
  if (a.phase === "uploading")
    return a.uploadTotal ? Math.min(100, Math.round((a.uploadLoaded / a.uploadTotal) * 100)) : 0;
  if (a.phase === "importing")
    return a.total ? Math.min(100, Math.round((a.processed / a.total) * 100)) : 0;
  return a.phase === "done" ? 100 : 0;
}
function importTagText(row: any): string {
  const a = rowImport(row);
  if (!a) return "已就绪";
  switch (a.phase) {
    case "uploading":
      return `上传中 ${percentOf(a)}%`;
    case "scanning":
      return "初始化中";
    case "importing":
      return `导入中 ${a.processed}/${a.total || "?"}`;
    case "done":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    default:
      return "已就绪";
  }
}
function importTagType(row: any): any {
  const a = rowImport(row);
  if (!a) return "info";
  return (
    {
      uploading: "primary",
      scanning: "warning",
      importing: "warning",
      done: "success",
      failed: "danger",
      cancelled: "info",
    } as Record<string, string>
  )[a.phase];
}
function rowImportPercent(row: any): number {
  return percentOf(rowImport(row));
}
function rowImportStatus(row: any): any {
  const p = rowImport(row)?.phase;
  if (p === "done") return "success";
  if (p === "failed") return "exception";
  return "";
}

// 弹窗（当前数据集）
const dialogImport = computed<ActiveImport | null>(() =>
  importDatasetId.value != null ? activeImports[importDatasetId.value] ?? null : null
);
const isRunningImport = computed(() => isRunning(dialogImport.value));
const importStep = computed(() => {
  const p = dialogImport.value?.phase;
  if (!p || p === "uploading") return p ? 1 : 0;
  if (p === "scanning") return 2;
  return 3;
});
const dialogPercent = computed(() => percentOf(dialogImport.value));
const dialogIndeterminate = computed(() => dialogImport.value?.phase === "scanning");
const dialogProgressStatus = computed<any>(() => {
  const p = dialogImport.value?.phase;
  if (p === "done") return "success";
  if (p === "failed") return "exception";
  return "";
});
const dialogPhaseText = computed(() => {
  const p = dialogImport.value?.phase;
  return (
    ({
      uploading: "正在上传 ZIP…",
      scanning: "服务端解析中…",
      importing: "正在导入图片…",
      done: "导入完成",
      failed: "导入失败",
      cancelled: "已取消",
    } as Record<string, string>)[p || ""] || ""
  );
});
const dialogDetailText = computed(() => {
  const a = dialogImport.value;
  if (!a) return "";
  if (a.phase === "uploading") return `已发送 ${fmtMB(a.uploadLoaded)} / ${fmtMB(a.uploadTotal)} MB`;
  if (a.phase === "importing") return `已导入 ${a.processed} / ${a.total}`;
  if (a.phase === "done") return `共 ${a.imported} 张 · ${a.totalAnnotations} 个标注`;
  return "";
});
const dialogElapsed = computed(() => elapsedSec(dialogImport.value));
const dialogEtaText = computed(() => {
  const a = dialogImport.value;
  if (!a) return "";
  const el = elapsedSec(a);
  if (el < 3) return "";
  if (a.phase === "uploading" && a.uploadTotal > 0 && a.uploadLoaded > 0) {
    const total = (el * a.uploadTotal) / a.uploadLoaded;
    return `预计还需 ${fmtDuration(total - el)}`;
  }
  if (a.phase === "importing" && a.total > 0 && a.processed > 0) {
    const total = (el * a.total) / a.processed;
    return `预计还需 ${fmtDuration(total - el)}`;
  }
  return "";
});

function handleOpenImport(row: any) {
  importDatasetId.value = row.id;
  importDatasetName.value = row.name;
  importFile.value = null;
  importUploadRef.value?.clearFiles?.();
  if (!activeImports[row.id] && row.import) seedImport(row.id, row.import);
  importDialogVisible.value = true;
  if (isRunning(activeImports[row.id])) {
    startTicker();
    ensurePolling();
  }
}
function openImportFor(row: any) {
  handleOpenImport(row);
}
function retryImport(row: any) {
  delete activeImports[row.id];
  handleOpenImport(row);
}

function onImportFileChange(_file: any, fileList: any[]) {
  importFile.value = fileList.length > 0 ? fileList[0].raw : null;
}

async function handleImportSubmit() {
  const dsId = importDatasetId.value;
  if (!dsId) {
    ElMessage.warning("缺少目标数据集");
    return;
  }
  if (!importFile.value) {
    ElMessage.warning("请选择 ZIP 文件");
    return;
  }
  const file = importFile.value;
  importAbort = new AbortController();
  activeImports[dsId] = {
    jobId: null,
    phase: "uploading",
    uploadLoaded: 0,
    uploadTotal: file.size,
    processed: 0,
    total: 0,
    imported: 0,
    totalAnnotations: 0,
    taskId: null,
    taskName: "",
    error: "",
    startedAt: Date.now(),
    fileName: file.name,
    fileSize: file.size,
  };
  startTicker();
  try {
    const r = await AnnotationAPI.importXAnyLabeling(dsId, file, {
      signal: importAbort.signal,
      onUploadProgress: (e: any) => {
        const a = activeImports[dsId];
        if (!a) return;
        a.uploadLoaded = e?.loaded || 0;
        a.uploadTotal = e?.total || file.size;
      },
    });
    const jobId = r.data?.data?.job_id;
    if (!jobId) throw new Error("未获取到导入任务ID");
    const a = activeImports[dsId];
    if (a) {
      a.jobId = jobId;
      a.phase = "scanning";
    }
    importAbort = null;
    ensurePolling();
  } catch (e: any) {
    const a = activeImports[dsId];
    if (a) {
      if (e?.name === "CanceledError" || e?.code === "ERR_CANCELED") {
        a.phase = "cancelled";
        a.error = "已取消";
      } else {
        a.phase = "failed";
        a.error = e?.message || "导入失败";
      }
    }
    importAbort = null;
    stopTickerIfIdle();
  }
}

function cancelImport() {
  if (importAbort) {
    importAbort.abort();
    importAbort = null;
  }
}

function ensurePolling() {
  if (pollTimer !== null) return;
  pollTimer = window.setInterval(pollActiveImports, 1000);
}
async function pollActiveImports() {
  const entries = Object.entries(activeImports).filter(
    ([, a]) => a.jobId && isRunningPhase(a.phase)
  );
  for (const [dsIdStr, a] of entries) {
    try {
      const r = await AnnotationAPI.getImportJob(a.jobId as string);
      const job = r.data?.data;
      if (!job) continue;
      applyJob(Number(dsIdStr), job);
    } catch {
      /* 忽略单次轮询失败 */
    }
  }
  if (!Object.values(activeImports).some((a) => a.jobId && isRunningPhase(a.phase))) {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }
  stopTickerIfIdle();
}
function applyJob(dsId: number, job: any) {
  const a = activeImports[dsId];
  if (!a) return;
  a.processed = job.processed || 0;
  a.total = job.total || 0;
  a.imported = job.imported || 0;
  a.totalAnnotations = job.total_annotations || 0;
  a.taskId = job.task_id ?? null;
  a.taskName = job.task_name || a.taskName;
  a.error = job.error || "";
  a.phase = phaseFromJob(job);
  if (a.phase === "done" && !a.refreshed) {
    a.refreshed = true;
    refreshList();
  }
}

async function handleImportDialogClose(done: () => void) {
  const a = dialogImport.value;
  if (!a || !isRunningPhase(a.phase)) {
    done();
    return;
  }
  if (a.phase === "importing") {
    try {
      await ElMessageBox.confirm(
        "导入将在后台继续，关闭后可在数据集列表的「导入状态」查看进度。",
        "提示",
        { type: "info", confirmButtonText: "关闭", cancelButtonText: "继续查看" }
      );
    } catch {
      return;
    }
    done();
    return;
  }
  // uploading / scanning：关闭即取消
  try {
    await ElMessageBox.confirm("上传/解析尚未完成，关闭将取消本次导入。", "提示", {
      type: "warning",
      confirmButtonText: "取消导入",
      cancelButtonText: "继续",
    });
  } catch {
    return;
  }
  cancelImport();
  a.phase = "cancelled";
  a.error = "已取消";
  done();
}
function requestCloseImport() {
  handleImportDialogClose(() => {
    importDialogVisible.value = false;
  });
}
function onImportDialogClosed() {
  importFile.value = null;
  importUploadRef.value?.clearFiles?.();
}
function goImportTask() {
  const tid = dialogImport.value?.taskId;
  if (tid) router.push(`/annotation/workbench/${tid}`);
}

// 列表数据变化时，为后端仍在进行的导入播种并开始轮询（刷新页面后进度继续）
watch(
  () => contentRef.value?.pageData,
  (rows) => {
    if (!Array.isArray(rows)) return;
    let seeded = false;
    for (const row of rows as any[]) {
      const j = row?.import;
      if (!j?.job_id || !row?.id) continue;
      if (activeImports[row.id]) continue;
      if (!isRunningPhase(phaseFromJob(j))) continue;
      seedImport(row.id, j);
      seeded = true;
    }
    if (seeded) {
      startTicker();
      ensurePolling();
    }
  }
);

onBeforeUnmount(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  if (tickTimer !== null) window.clearInterval(tickTimer);
});

// ── Export ──
const exportDialogVisible = ref(false);
const exportHistoryRef = ref();
const cleanRef = ref();
const exportDatasetId = ref<number | null>(null);
const exportDatasetName = ref("");
const exportFormat = ref("yolo-detection");
const exporting = ref(false);
const exportRowTasks = ref<any[]>([]);
const exportTaskId = ref<number | undefined>(undefined);
const ocrExportDet = ref(true);
const ocrExportRec = ref(true);
const trainRatio = ref(80);

const isYoloOrPaddleFormat = computed(() => {
  return exportFormat.value.startsWith("yolo-") || exportFormat.value.startsWith("paddle-");
});

const FORMAT_TASK_MAP: Record<string, string[]> = {
  "yolo-detection": ["detection"],
  "yolo-rotated_detection": ["rotated_detection"],
  "yolo-segmentation": ["segmentation"],
  "yolo-keypoint": ["keypoint"],
  "yolo-cls": ["classification"],
  "paddle-mlcls": ["classification"],
  "paddle-ocr": ["ocr"],
  "x-anylabeling": ["detection", "rotated_detection", "segmentation", "keypoint", "ocr", "classification"],
};

const filteredExportFormats = computed(() => {
  const task = exportRowTasks.value.find((t: any) => t.id === exportTaskId.value);
  if (!task) return exportFormatOptions;
  return exportFormatOptions.filter(opt => FORMAT_TASK_MAP[opt.value]?.includes(task.task_type));
});

function onTaskChange() {
  const avail = filteredExportFormats.value;
  if (avail.length > 0 && !avail.find(o => o.value === exportFormat.value)) {
    exportFormat.value = avail[0].value;
  }
}

const exportFormatOptions = [
  { value: "yolo-detection", label: "YOLO HBB（水平矩形框）" },
  { value: "yolo-rotated_detection", label: "YOLO OBB（旋转矩形框）" },
  { value: "yolo-segmentation", label: "YOLO Seg（分割）" },
  { value: "yolo-keypoint", label: "YOLO Pose（关键点）" },
  { value: "yolo-cls", label: "YOLO CLS（单标签分类）" },
  { value: "paddle-mlcls", label: "Paddle MLCLS（多标签分类）" },
  { value: "paddle-ocr", label: "PaddleOCR" },
  { value: "x-anylabeling", label: "X-AnyLabeling（通用 JSON 格式）" },
];

function handleOpenExport(row: any) {
  exportDatasetId.value = row.id;
  exportDatasetName.value = row.name;
  exportRowTasks.value = row.tasks || [];
  exportTaskId.value = exportRowTasks.value.length > 0 ? exportRowTasks.value[0].id : undefined;
  ocrExportDet.value = true;
  ocrExportRec.value = true;
  trainRatio.value = 80;
  exportFormat.value = "x-anylabeling";
  onTaskChange();
  exportDialogVisible.value = true;
}

async function handleExportSubmit() {
  if (!exportDatasetId.value) return;
  if (!exportTaskId.value) { ElMessage.warning("请选择标注任务"); return; }
  exporting.value = true;
  try {
    const { TrainAPI } = await import("@/api/module_train");
    let ocrRec: boolean | undefined;
    if (exportFormat.value === "paddle-ocr") {
      if (!ocrExportDet.value && !ocrExportRec.value) {
        ElMessage.warning("请至少选择一种 OCR 导出（det/rec）");
        return;
      }
      ocrRec = ocrExportRec.value; // det-only → false；rec 参与（rec-only 或 both）→ true
    }
    const r = await TrainAPI.exportDataset({
      dataset_id: exportDatasetId.value,
      format: exportFormat.value,
      annotation_task_id: exportTaskId.value,
      ocr_rec: ocrRec,
      train_ratio: isYoloOrPaddleFormat.value ? trainRatio.value / 100 : undefined,
    });
    const url = r.data?.data?.download_url;
    if (url) {
      // Use hidden iframe for download — bypasses CORS + popup blockers
      const iframe = document.createElement("iframe");
      iframe.style.display = "none";
      iframe.src = url;
      document.body.appendChild(iframe);
      setTimeout(() => document.body.removeChild(iframe), 120000);
    } else {
      ElMessage.warning("导出完成但未获取到下载链接，请查看后端日志");
    }
    exportDialogVisible.value = false;
  } catch {
    /* 提示由请求拦截器统一处理 */
  } finally {
    exporting.value = false;
  }
}
</script>

<style scoped>
.upload-alert {
  margin-bottom: 16px;
}
.import-steps {
  margin-bottom: 16px;
}
.import-picker {
  padding: 2px 0;
}
.import-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
.import-file {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.import-file-name {
  font-weight: 600;
}
.import-file-size {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
}
.import-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 2px 0;
}
.import-line {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.import-line--primary {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.import-line--muted {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.import-alert {
  margin-top: 2px;
}
.import-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.import-pop {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.import-pop-title {
  font-weight: 600;
  font-size: 13px;
}
.import-pop-row {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.import-pop-err {
  color: var(--el-color-danger);
  word-break: break-all;
}
.import-pop-actions {
  display: flex;
  gap: 8px;
}
.task-badge {
  position: relative; display: inline-flex; align-items: center; gap: 4px;
  padding: 0 8px; border-radius: 4px; font-size: 12px; line-height: 22px;
  cursor: pointer; overflow: hidden;
  background: #f5f7fa; border: 1.5px solid #e4e7ed;
  transition: border-color .15s;
  width: 130px;
}
.task-badge:hover { filter: brightness(.96); }
.task-badge-name {
  position: relative; z-index: 1; font-weight: 600;
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.task-badge-pct {
  position: relative; z-index: 1; font-size: 10px; opacity: .6;
  font-variant-numeric: tabular-nums; min-width: 28px; text-align: right;
}
.task-badge-fill {
  position: absolute; top: 0; left: 0; bottom: 0;
  border-radius: 3px; transition: width .5s ease;
  pointer-events: none;
}
</style>
