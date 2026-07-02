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
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_annotation:dataset:create']"
          :perm-delete="['module_annotation:dataset:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
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
              v-if="contentCols.find((col) => col.prop === 'task_count')?.show"
              key="task_count"
              label="引用任务"
              prop="task_count"
              width="90"
              align="center"
            >
              <template #default="scope">
                <el-tag type="warning" effect="plain" size="small">
                  {{ scope.row.task_count ?? 0 }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              prop="status"
              width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status ? 'success' : 'danger'" size="small">
                  {{ scope.row.status ? "启用" : "停用" }}
                </el-tag>
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
              min-width="220"
            >
              <template #default="scope">
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
                <el-button
                  v-hasPerm="['module_annotation:dataset:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
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
        <el-form-item label="标注类型" prop="annotation_type">
          <el-select v-model="formData.annotation_type" placeholder="请选择标注类型" style="width:100%">
            <el-option v-for="opt in annotationTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
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
        <div class="el-upload__text">拖拽文件到此处，或<em>点击选择</em></div>
      </el-upload>
      <template #footer>
        <el-button @click="handleCloseUpload">取消</el-button>
        <el-button type="primary" :loading="uploadLoading" @click="handleUploadSubmit">
          开始上传
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";
import type { ISearchConfig, IContentConfig, IObject } from "@/components/CURD/types";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import { ElMessage } from "element-plus";

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
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "启用", value: "true" },
        { label: "停用", value: "false" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "167.5px" } },
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
  { prop: "task_count", label: "引用任务", show: true },
  { prop: "status", label: "状态", show: true },
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
    title: "警告",
    message: "确认删除所选数据集? 图片和标注数据将一并删除。",
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const annotationTypeOptions = [
  { value: "detection", label: "目标检测" },
  { value: "rotated_detection", label: "旋转框检测" },
  { value: "segmentation", label: "分割" },
  { value: "keypoint", label: "关键点" },
  { value: "ocr", label: "OCR文本" },
  { value: "classification", label: "图像分类" },
]

const formData = reactive({
  id: undefined as number | undefined,
  name: "",
  annotation_type: "detection",
  status: true,
  description: "",
});

const initialFormData = {
  id: undefined as number | undefined,
  name: "",
  annotation_type: "detection",
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
          await AnnotationAPI.updateDataset(id, { name: formData.name, annotation_type: formData.annotation_type, description: formData.description });
        } else {
          await AnnotationAPI.createDataset({ name: formData.name, annotation_type: formData.annotation_type, description: formData.description });
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
    ElMessage.success("上传成功");
    uploadVisible.value = false;
    fileList.value = [];
    refreshList();
  } catch {
    //
  } finally {
    uploadLoading.value = false;
  }
}
</script>

<style scoped>
.upload-alert {
  margin-bottom: 16px;
}
</style>