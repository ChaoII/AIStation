<!-- 部门配置 -->
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
          :perm-create="['module_system:dept:create']"
          :perm-delete="['module_system:dept:delete']"
          :perm-patch="['module_system:dept:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
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
            stripe
            row-key="id"
            :data="data"
            :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
            height="100%"
            border
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('system.dept.empty')" />
            </template>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              min-width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              type="index"
              fixed
              :label="t('system.dept.index')"
              min-width="60"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('system.dept.name')"
              prop="name"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'code')?.show"
              key="code"
              :label="t('system.dept.code')"
              prop="code"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('system.dept.status')"
              prop="status"
              min-width="60"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{ scope.row.status ? t("system.dept.enabled") : t("system.dept.disabled") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'order')?.show"
              key="order"
              :label="t('system.dept.order')"
              prop="order"
              min-width="60"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.dept.description')"
              prop="description"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.dept.createdTime')"
              prop="created_time"
              min-width="120"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              key="updated_time"
              :label="t('system.dept.updatedTime')"
              prop="updated_time"
              min-width="120"
              sortable
            />

            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.dept.operation')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:dept:create']"
                  type="success"
                  size="small"
                  link
                  icon="plus"
                  @click="handleOpenDialog('create', undefined, scope.row.id)"
                >
                  {{ t("system.dept.add") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dept:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.dept.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dept:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.dept.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dept:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.dept.delete") }}
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
      @close="handleCloseDialog"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <el-descriptions :column="4" border>
          <el-descriptions-item :label="t('system.dept.name')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.code')" :span="2">
            {{ detailFormData.code }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.parentDept')" :span="2">
            {{ detailFormData.parent_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.status')" :span="2">
            <el-tag :type="detailFormData.status ? 'success' : 'danger'">
              {{ detailFormData.status ? t("system.dept.enabled") : t("system.dept.disabled") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.order')" :span="2">
            {{ detailFormData.order }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.updatedTime')" :span="2">
            {{ detailFormData.updated_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dept.description')" :span="4">
            {{ detailFormData.description }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template v-else>
        <el-form
          ref="dataFormRef"
          :model="formData"
          :rules="rules"
          label-suffix=":"
          label-width="auto"
          label-position="right"
        >
          <el-form-item :label="t('system.dept.name')" prop="name">
            <el-input
              v-model="formData.name"
              :placeholder="t('system.dept.placeholderName')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.dept.code')" prop="code">
            <el-input
              v-model="formData.code"
              :placeholder="t('system.dept.codeFormat')"
              :maxlength="16"
              show-word-limit
            />
          </el-form-item>
          <el-form-item :label="t('system.dept.parentDept')" prop="parent_id">
            <el-tree-select
              v-model="formData.parent_id"
              :placeholder="t('system.dept.placeholderParent')"
              :data="deptOptions"
              filterable
              check-strictly
              :render-after-expand="false"
            />
          </el-form-item>
          <el-form-item :label="t('system.dept.order')" prop="order">
            <el-input-number
              v-model="formData.order"
              controls-position="right"
              :min="1"
              :max="999"
            />
          </el-form-item>
          <el-form-item :label="t('system.dept.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.dept.enabled") }}</el-radio>
              <el-radio value="1">{{ t("system.dept.disabled") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('system.dept.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.dept.placeholderDescription')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button v-if="dialogVisible.type !== 'detail'" type="primary" @click="handleSubmit">
            {{ t("system.dept.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.dept.confirm") }}
          </el-button>
          <el-button @click="handleCloseDialog">{{ t("system.dept.cancel") }}</el-button>
        </div>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Dept",
  inheritAttrs: false,
});

import DeptAPI, { DeptTable, DeptForm, DeptPageQuery } from "@/api/module_system/dept";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { ElMessage } from "element-plus";
import { useUserStore } from "@/store";
import { formatTree } from "@/utils/common";
import { ref, reactive } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:dept",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("system.dept.name"),
      type: "input",
      attrs: { placeholder: t("system.dept.placeholderName"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.dept.status"),
      type: "select",
      options: [
        { label: t("system.dept.enabled"), value: "0" },
        { label: t("system.dept.disabled"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.dept.placeholderStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.dept.createdTime"),
      type: "date-picker",
      attrs: {
        type: "datetimerange",
        rangeSeparator: t("system.dept.separator"),
        startPlaceholder: t("system.dept.startDate"),
        endPlaceholder: t("system.dept.endDate"),
        format: "YYYY-MM-DD HH:mm:ss",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        style: { width: "340px" },
      },
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
  { prop: "selection", label: t("system.dept.selection"), show: true },
  { prop: "index", label: t("system.dept.index"), show: true },
  { prop: "name", label: t("system.dept.name"), show: true },
  { prop: "code", label: t("system.dept.code"), show: true },
  { prop: "order", label: t("system.dept.order"), show: true },
  { prop: "status", label: t("system.dept.status"), show: true },
  { prop: "description", label: t("system.dept.description"), show: true },
  { prop: "created_time", label: t("system.dept.createdTime"), show: true },
  { prop: "updated_time", label: t("system.dept.updatedTime"), show: true },
  { prop: "operation", label: t("system.dept.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<DeptPageQuery>>({
  permPrefix: "module_system:dept",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: false,
  indexAction: async (params) => {
    const res = await DeptAPI.listDept(params as DeptPageQuery);
    const tree = res.data.data || [];
    deptOptions.value = formatTree(tree);
    return tree;
  },
  deleteAction: async (ids) => {
    await DeptAPI.deleteDept(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    const userStore = useUserStore();
    await userStore.getUserInfo();
  },
  deleteConfirm: {
    title: t("system.dept.warning"),
    message: t("system.dept.deleteConfirm"),
    type: "warning",
  },
});

const deptOptions = ref<OptionType[]>([]);

const detailFormData = ref<DeptTable>({ code: "" });

const formData = reactive<DeptForm>({
  id: undefined,
  name: undefined,
  code: "",
  order: 1,
  parent_id: undefined,
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const CODE_PATTERN = /^[A-Za-z][A-Za-z0-9_]{1,15}$/;

const rules = reactive({
  name: [{ required: true, message: t("system.dept.placeholderName"), trigger: "blur" }],
  code: [
    { required: true, message: t("system.dept.codeRequired"), trigger: "blur" },
    {
      pattern: CODE_PATTERN,
      message: t("system.dept.codeFormat"),
      trigger: "blur",
    },
  ],
  order: [{ required: true, message: t("system.dept.orderRequired"), trigger: "blur" }],
  status: [{ required: true, message: t("system.dept.placeholderStatus"), trigger: "blur" }],
});

const initialFormData: DeptForm = {
  id: undefined,
  name: undefined,
  code: "",
  order: 1,
  parent_id: undefined,
  status: "0",
  description: undefined,
};

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

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

async function handleOpenDialog(
  type: "create" | "update" | "detail",
  id?: number,
  parentId?: number
) {
  dialogVisible.type = type;
  if (id) {
    const response = await DeptAPI.detailDept(id);
    if (type === "detail") {
      dialogVisible.title = t("system.dept.deptDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.dept.updateDept");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.dept.addDept");
    formData.id = undefined;
    if (parentId) {
      formData.parent_id = parentId;
    }
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      const id = formData.id;
      try {
        if (id) {
          await DeptAPI.updateDept(id, { id, ...formData });
        } else {
          await DeptAPI.createDept(formData);
        }
        ElMessage.success(t("system.dept.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        const userStore = useUserStore();
        await userStore.getUserInfo();
      } catch (error: unknown) {
        console.error(error);
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as DeptTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.dept.selectFirst"));
    return;
  }
  ElMessageBox.confirm(
    t("system.dept.confirmToggle", {
      action: status === "0" ? t("system.dept.enabled") : t("system.dept.disabled"),
    }),
    t("system.dept.warning"),
    {
      confirmButtonText: t("system.dept.confirm"),
      cancelButtonText: t("system.dept.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await DeptAPI.batchDept({ ids, status });
        ElMessage.success(t("system.dept.operationSuccess"));
        refreshList();
        const userStore = useUserStore();
        await userStore.getUserInfo();
      } catch (error: unknown) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}
</script>
