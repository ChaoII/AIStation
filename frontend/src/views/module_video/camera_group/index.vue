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
          :perm-create="['module_video:camera:create']"
          :perm-delete="['module_video:camera:delete']"
          :perm-patch="['module_video:camera:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            default-expand-all
            :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
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
              type="index"
              fixed
              label="序号"
              min-width="60"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="分组名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'sort_order')?.show"
              key="sort_order"
              label="排序"
              prop="sort_order"
              width="80"
              align="center"
            />
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
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              label="备注"
              prop="description"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_at')?.show"
              key="created_at"
              label="创建时间"
              prop="created_at"
              min-width="170"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              width="160"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:camera:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:camera:delete']"
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
        <el-form-item label="分组名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入分组名称" />
        </el-form-item>
        <el-form-item label="上级分组" prop="parent_id">
          <el-tree-select
            v-model="formData.parent_id"
            :data="treeOptions"
            :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
            value-key="value"
            placeholder="请选择上级分组（不选为顶级）"
            clearable
            filterable
            style="width: 100%"
          />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="排序" prop="sort_order">
              <el-input-number v-model="formData.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-switch v-model="formData.status" active-text="启用" inactive-text="停用" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
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
import {
  getCameraGroupList,
  createCameraGroup,
  updateCameraGroup,
  deleteCameraGroup,
} from "@/api/module_video/camera";
import { formatTree } from "@/utils/common";
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
const rawList = ref<any[]>([]);
const treeOptions = ref<any[]>([]);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:camera",
  colon: true,
  isExpandable: true,
  showNumber: 1,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "分组名称",
      type: "input",
      attrs: { placeholder: "请输入分组名称", clearable: true },
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
  { prop: "name", label: "分组名称", show: true },
  { prop: "sort_order", label: "排序", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "description", label: "备注", show: true },
  { prop: "created_at", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

async function fetchGroupData(params?: any) {
  const res = await getCameraGroupList();
  const tree = res.data.data || [];
  rawList.value = flattenTree(tree);
  const query = params?.name;
  if (query) {
    rawList.value = rawList.value.filter((item: any) => item.label?.includes(query));
  }
  return {
    total: rawList.value.length,
    list: rawList.value,
  };
}

function flattenTree(nodes: any[], result: any[] = []): any[] {
  for (const node of nodes) {
    result.push(node);
    if (node.children && node.children.length > 0) {
      flattenTree(node.children, result);
    }
  }
  return result;
}

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:camera",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 20,
    pageSizes: [10, 20, 50, 100],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    return await fetchGroupData(params);
  },
  deleteAction: async (ids) => {
    await deleteCameraGroup(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: "警告",
    message: "确认删除该分组? 子分组将一并删除。",
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

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  parent_id: undefined as number | undefined,
  sort_order: 0,
  status: true,
  description: undefined as string | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  parent_id: undefined as number | undefined,
  sort_order: 0,
  status: true,
  description: undefined as string | undefined,
};

const rules = reactive({
  name: [{ required: true, message: "请输入分组名称", trigger: "blur" }],
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

function excludeSelfAndChildren(nodes: any[], excludeId: number): any[] {
  return nodes
    .filter((n) => n.id !== excludeId)
    .map((n) => {
      if (n.children && n.children.length > 0) {
        return { ...n, children: excludeSelfAndChildren(n.children, excludeId) };
      }
      return { ...n };
    })
    .filter(
      (n) => n.children === undefined || n.children === null || n.children.length > 0 || true
    );
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  const res = await getCameraGroupList();
  const treeList = res.data.data || [];
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑分组";
    const item = rawList.value.find((i: any) => i.id === id);
    if (item) {
      formData.id = item.id;
      formData.name = item.name;
      formData.parent_id = item.parent_id;
      formData.sort_order = item.sort_order;
      formData.status = item.status;
      formData.description = item.description;
    }
    treeOptions.value = formatTree(excludeSelfAndChildren(treeList, id));
  } else {
    dialogVisible.title = "新增分组";
    Object.assign(formData, initialFormData);
    treeOptions.value = formatTree(treeList);
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
          await updateCameraGroup(id, { ...formData });
        } else {
          await createCameraGroup(formData);
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

onBeforeMount(async () => {
  const res = await getCameraGroupList();
  treeOptions.value = formatTree(res.data.data || []);
});
</script>
