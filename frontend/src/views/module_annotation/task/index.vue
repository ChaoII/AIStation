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
          :perm-create="['module_annotation:task:create']"
          :perm-delete="['module_annotation:task:delete']"
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
            @row-click="handleRowClick"
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column fixed label="序号" width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column label="任务名称" prop="name" min-width="160" show-overflow-tooltip />
            <el-table-column
              label="数据集"
              prop="dataset_name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column label="标注类型" prop="task_type" width="120" align="center">
              <template #default="scope">
                <el-tag :type="annotationTypeTag(scope.row.task_type)" size="small" effect="plain">
                  {{ annotationTypeLabel(scope.row.task_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="进度" prop="progress" min-width="180">
              <template #default="scope">
                <el-progress
                  :percentage="scope.row.progress || 0"
                  :status="scope.row.progress >= 100 ? 'success' : undefined"
                  :stroke-width="14"
                  :text-inside="true"
                />
              </template>
            </el-table-column>
            <el-table-column label="标注员" prop="assignees" min-width="140">
              <template #default="scope">
                <el-tag
                  v-for="name in scope.row.assignees || []"
                  :key="name"
                  size="small"
                  style="margin-right: 3px; margin-bottom: 2px"
                >
                  {{ name }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" prop="status" width="100" align="center">
              <template #default="scope">
                <el-tag
                  :type="
                    scope.row.status === 'completed'
                      ? 'success'
                      : scope.row.status === 'in_progress'
                        ? 'primary'
                        : 'info'
                  "
                  size="small"
                >
                  {{
                    scope.row.status === "completed"
                      ? "已完成"
                      : scope.row.status === "in_progress"
                        ? "进行中"
                        : "待开始"
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_time" min-width="170" />
            <el-table-column label="操作" fixed="right" align="center" min-width="200">
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_annotation:task:workbench']"
                  type="success"
                  size="small"
                  link
                  icon="Edit"
                  @click.stop="handleEnterWorkbench(scope.row)"
                >
                  进入标注
                </el-button>
                <el-button
                  v-hasPerm="['module_annotation:task:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click.stop="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_annotation:task:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click.stop="handleRowDelete(scope.row.id)"
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
      width="600px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="110px"
        size="default"
      >
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="选择数据集" prop="dataset_id">
          <el-select
            v-model="formData.dataset_id"
            placeholder="请选择数据集"
            filterable
            style="width: 100%"
          >
            <el-option
              v-for="item in datasetOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标注类型" prop="task_type">
          <el-select v-model="formData.task_type" placeholder="请选择标注类型" style="width: 100%">
            <el-option label="目标检测" value="detection" />
            <el-option label="旋转框检测" value="rotated_detection" />
            <el-option label="多边形分割" value="segmentation" />
            <el-option label="关键点" value="keypoint" />
            <el-option label="OCR文本" value="ocr" />
            <el-option label="图像分类" value="classification" />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="formData.task_type === 'classification'"
          label="分类模式"
          prop="classification_mode"
        >
          <el-radio-group v-model="formData.classification_mode">
            <el-radio value="single">单标签（每张图一个类别）</el-radio>
            <el-radio value="multi">多标签（每张图多个类别）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标注员" prop="assignees">
          <el-select
            v-model="formData.assignees"
            multiple
            filterable
            placeholder="请选择标注员"
            style="width: 100%"
          >
            <el-option
              v-for="item in userOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="类别">
          <div style="width: 100%">
            <div style="display: flex; gap: 8px; margin-bottom: 8px">
              <el-input
                v-model="newClassName"
                placeholder="输入类别名称，如 person"
                @keyup.enter="handleAddClass"
              />
              <el-button type="primary" icon="plus" @click="handleAddClass">添加</el-button>
            </div>
            <div v-if="formData.classes.length" style="display: flex; flex-wrap: wrap; gap: 6px">
              <el-tag
                v-for="(cls, index) in formData.classes"
                :key="`${cls.id}-${index}`"
                :color="cls.color"
                effect="dark"
                closable
                @close="handleRemoveClass(index)"
              >
                {{ cls.name }}
              </el-tag>
            </div>
            <span v-else style="font-size: 12px; color: var(--el-text-color-secondary)">
              暂无类别，添加后可在标注工作台使用
            </span>
          </div>
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="可选备注信息"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { AnnotationAPI } from "@/api/module_annotation";
import UserAPI from "@/api/module_system/user";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";

interface TaskPageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

interface TaskClass {
  id: number;
  name: string;
  color: string;
}

const CLASS_COLORS = [
  "#409eff",
  "#67c23a",
  "#e6a23c",
  "#f56c6c",
  "#909399",
  "#b37feb",
  "#13c2c2",
  "#eb2f96",
];

const router = useRouter();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();
const datasetOptions = ref<any[]>([]);
const userOptions = ref<any[]>([]);
const newClassName = ref("");

onBeforeMount(async () => {
  try {
    const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
    datasetOptions.value = dsRes.data.data?.items || [];
  } catch {
    datasetOptions.value = [];
  }
  try {
    const uRes = await UserAPI.listUser({ page_no: 1, page_size: 100 });
    userOptions.value = uRes.data.data?.items || [];
  } catch {
    userOptions.value = [];
  }
});

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_annotation:task",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "任务名称",
      type: "input",
      attrs: { placeholder: "请输入任务名称", clearable: true },
    },
    {
      prop: "annotation_type",
      label: "标注类型",
      type: "select",
      options: [
        { label: "目标检测", value: "detection" },
        { label: "旋转框检测", value: "rotated_detection" },
        { label: "多边形分割", value: "segmentation" },
        { label: "关键点", value: "keypoint" },
        { label: "OCR文本", value: "ocr" },
        { label: "分类", value: "classification" },
      ],
      attrs: { placeholder: "请选择标注类型", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "进行中", value: "in_progress" },
        { label: "已完成", value: "completed" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "任务名称", show: true },
  { prop: "dataset_name", label: "数据集", show: true },
  { prop: "task_type", label: "标注类型", show: true },
  { prop: "progress", label: "进度", show: true },
  { prop: "assignees", label: "标注员", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TaskPageQuery>>({
  permPrefix: "module_annotation:task",
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
    const res = await AnnotationAPI.getTaskList(params as TaskPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await AnnotationAPI.deleteTask(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: "警告",
    message: "确认删除该项数据?",
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

function handleRowClick(row: any) {
  router.push(`/annotation/workbench/${row.id}`);
}

function handleEnterWorkbench(row: any) {
  router.push(`/annotation/workbench/${row.id}`);
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  dataset_id: undefined as number | undefined,
  task_type: "detection",
  assignees: [] as number[],
  description: undefined as string | undefined,
  classification_mode: undefined as string | undefined,
  classes: [] as TaskClass[],
});

// 用工厂函数返回全新对象，保证数组字段（assignees/classes）每次都是新引用，
// 避免 resetForm 里 Object.assign 之后 handleAddClass 的 push 污染初始值。
function makeInitialFormData() {
  return {
    id: undefined as number | undefined,
    name: undefined as string | undefined,
    dataset_id: undefined as number | undefined,
    task_type: "detection",
    assignees: [] as number[],
    description: undefined as string | undefined,
    classification_mode: undefined as string | undefined,
    classes: [] as TaskClass[],
  };
}

// 后端 classes 字段存在多种历史存储形态（数组 / {classes:[...]} / id 或 name 键字典），
// 编辑时必须归一化为 TaskClass[]，否则保存会清空既有类别定义。
function normalizeClasses(raw: unknown): TaskClass[] {
  const hasContent =
    (Array.isArray(raw) && raw.length > 0) ||
    (!!raw && typeof raw === "object" && Object.keys(raw as Record<string, unknown>).length > 0);

  const result: TaskClass[] = [];
  const pushClass = (id: number, name: string, color?: unknown) => {
    result.push({
      id,
      name,
      color: (typeof color === "string" && color) || CLASS_COLORS[id % CLASS_COLORS.length],
    });
  };

  if (Array.isArray(raw)) {
    raw.forEach((entry, index) => {
      if (typeof entry === "string") {
        // 裸字符串条目 → 归一化为带调色板的类别对象
        pushClass(index, entry);
      } else if (entry && typeof entry === "object") {
        const def = entry as Record<string, unknown>;
        const id = typeof def.id === "number" ? def.id : index;
        pushClass(id, String(def.name ?? `class_${id}`), def.color);
      }
    });
  } else if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.classes)) {
      return normalizeClasses(obj.classes);
    }
    let autoId = 0;
    for (const [key, value] of Object.entries(obj)) {
      if (key === "classes") continue;
      const numericId = Number(key);
      const isNameKey = Number.isNaN(numericId);
      const id = isNameKey ? autoId : numericId;
      if (typeof value === "string") {
        // 数字键：值即类别名；字符串键：键即类别名
        pushClass(id, isNameKey ? key : value);
      } else if (value && typeof value === "object") {
        const def = value as Record<string, unknown>;
        // 数字键：值是类别定义；name 键：键是类别名，值可含 color
        pushClass(id, String(def.name ?? (isNameKey ? key : `class_${id}`)), def.color);
      }
      autoId += 1;
    }
  }

  // 非空输入却解析为空 → 返回原始值，避免编辑保存时把已有类别静默清成 []
  if (result.length === 0 && hasContent) {
    return raw as unknown as TaskClass[];
  }
  return result;
}

const rules = reactive({
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
  dataset_id: [{ required: true, message: "请选择数据集", trigger: "change" }],
  task_type: [{ required: true, message: "请选择标注类型", trigger: "change" }],
});

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, makeInitialFormData());
  newClassName.value = "";
}

function handleAddClass() {
  const name = newClassName.value.trim();
  if (!name) {
    ElMessage.warning("请输入类别名称");
    return;
  }
  if (formData.classes.some((c) => c.name === name)) {
    ElMessage.warning("类别名称已存在");
    return;
  }
  const nextId = formData.classes.reduce((max, c) => Math.max(max, c.id + 1), 0);
  formData.classes.push({
    id: nextId,
    name,
    color: CLASS_COLORS[nextId % CLASS_COLORS.length],
  });
  newClassName.value = "";
}

function handleRemoveClass(index: number) {
  formData.classes.splice(index, 1);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑任务";
    const res = await AnnotationAPI.getTaskDetail(id);
    const item = res.data.data;
    if (item) {
      formData.id = item.id;
      formData.name = item.name;
      formData.dataset_id = item.dataset_id;
      formData.task_type = item.task_type;
      formData.assignees = item.assignees || [];
      formData.description = item.description;
      formData.classification_mode = item.classification_mode;
      formData.classes = normalizeClasses(item.classes);
    }
  } else {
    dialogVisible.title = "新增任务";
    formData.id = undefined;
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
          await AnnotationAPI.updateTask(id, {
            name: formData.name,
            task_type: formData.task_type,
            assignees: formData.assignees,
            classification_mode: formData.classification_mode,
            description: formData.description,
            classes: formData.classes,
          });
        } else {
          await AnnotationAPI.createTask({
            dataset_id: formData.dataset_id,
            name: formData.name,
            task_type: formData.task_type,
            assignees: formData.assignees,
            classes: formData.classes,
            classification_mode: formData.classification_mode,
            description: formData.description,
          });
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch {
        // 错误提示统一由请求拦截器负责，避免重复 toast
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

function annotationTypeLabel(type: string) {
  const map: Record<string, string> = {
    detection: "目标检测",
    rotated_detection: "旋转框检测",
    segmentation: "多边形分割",
    keypoint: "关键点",
    ocr: "OCR文本",
    classification: "图像分类",
  };
  return map[type] || type;
}

function annotationTypeTag(type: string) {
  const map: Record<string, "warning" | "danger" | "info" | undefined> = {
    detection: undefined,
    rotated_detection: "warning",
    segmentation: "danger",
    keypoint: "warning",
    ocr: "info",
    classification: "info",
  };
  return map[type];
}
</script>
