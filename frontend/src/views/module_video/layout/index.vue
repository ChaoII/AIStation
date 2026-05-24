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
          :perm-create="['module_video:layout:create']"
          :perm-delete="['module_video:layout:delete']"
          :perm-patch="['module_video:layout:patch']"
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
              width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              fixed
              label="序号"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="布局名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'grid_type')?.show"
              key="grid_type"
              label="画面数"
              prop="grid_type"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag size="small">{{ scope.row.grid_type }}路</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'is_default')?.show"
              key="is_default"
              label="默认布局"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.is_default" type="success" size="small">默认</el-tag>
                <span v-else style="color: var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              label="描述"
              prop="description"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  size="small"
                  type="info"
                  link
                  icon="View"
                  @click="handlePreview(scope.row.grid_type)"
                >
                  预览
                </el-button>
                <el-button
                  v-hasPerm="['module_video:layout:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:layout:delete']"
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
      width="500px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item label="布局名称" prop="name">
          <el-input v-model="formData.name" placeholder="例如：4路默认" />
        </el-form-item>
        <el-form-item label="画面数" prop="grid_type">
          <el-select v-model="formData.grid_type" style="width: 100%">
            <el-option label="1路" value="1" />
            <el-option label="4路" value="4" />
            <el-option label="6路" value="6" />
            <el-option label="8路" value="8" />
            <el-option label="9路" value="9" />
            <el-option label="16路" value="16" />
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="可选描述"
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
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { getLayoutList, createLayout, updateLayout, deleteLayout } from "@/api/module_video/layout";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:layout",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "布局名称",
      type: "input",
      attrs: { placeholder: "请输入布局名称", clearable: true },
    },
    {
      prop: "grid_type",
      label: "画面数",
      type: "select",
      options: [
        { label: "1路", value: "1" },
        { label: "4路", value: "4" },
        { label: "6路", value: "6" },
        { label: "8路", value: "8" },
        { label: "9路", value: "9" },
        { label: "16路", value: "16" },
      ],
      attrs: { placeholder: "请选择画面数", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "布局名称", show: true },
  { prop: "grid_type", label: "画面数", show: true },
  { prop: "is_default", label: "默认布局", show: true },
  { prop: "description", label: "描述", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:layout",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getLayoutList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteLayout(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

function handlePreview(gridType: string) {
  ElMessage.info(`预览 ${gridType} 路布局（功能开发中）`);
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  grid_type: "4",
  is_default: false,
  description: undefined as string | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  grid_type: "4" as const,
  is_default: false,
  description: undefined as string | undefined,
};

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
    dialogVisible.title = "编辑布局";
    const res = await getLayoutList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) Object.assign(formData, item);
  } else {
    dialogVisible.title = "新建布局";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (id) {
      await updateLayout(id, { id, ...formData });
    } else {
      await createLayout(formData);
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
</script>
