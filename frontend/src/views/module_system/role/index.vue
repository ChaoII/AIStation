<!-- 角色管理 -->
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
          :perm-create="['module_system:role:create']"
          :perm-delete="['module_system:role:delete']"
          :perm-patch="['module_system:role:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.role.export')">
                <el-button
                  v-hasPerm="['module_system:role:export']"
                  type="warning"
                  icon="download"
                  circle
                  @click="handleOpenExportsModal"
                />
              </el-tooltip>
            </template>
          </CrudToolbarRight>
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
              <el-empty :image-size="80" :description="t('system.role.emptyData')" />
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
              :label="t('system.role.indexNo')"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('system.role.roleName')"
              prop="name"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'code')?.show"
              key="code"
              :label="t('system.role.roleCode')"
              prop="code"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'data_scope')?.show"
              key="data_scope"
              :label="t('system.role.dataScope')"
              prop="data_scope"
              min-width="200"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.data_scope === 1" type="primary">
                  {{ t("system.role.scopeOnlySelf") }}
                </el-tag>
                <el-tag v-else-if="scope.row.data_scope === 2" type="info">
                  {{ t("system.role.scopeDept") }}
                </el-tag>
                <el-tag v-else-if="scope.row.data_scope === 3" type="warning">
                  {{ t("system.role.scopeDeptAndBelow") }}
                </el-tag>
                <el-tag v-else-if="scope.row.data_scope === 4" type="success">
                  {{ t("system.role.scopeAll") }}
                </el-tag>
                <el-tag v-else type="danger">{{ t("system.role.scopeCustom") }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'depts')?.show"
              key="depts"
              :label="t('system.role.dept')"
              prop="depts"
              min-width="200"
            >
              <template #default="scope">
                <template v-if="scope.row.depts && scope.row.depts.length > 0">
                  <el-tag
                    v-for="dept in scope.row.depts.slice(0, 3)"
                    :key="dept.id"
                    type="info"
                    style="margin-right: 4px; margin-bottom: 4px"
                  >
                    {{ dept.name }}
                  </el-tag>
                  <el-tag v-if="scope.row.depts.length > 3" type="info" style="margin-bottom: 4px">
                    +{{ scope.row.depts.length - 3 }}
                  </el-tag>
                </template>
                <span v-else style="color: var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'order')?.show"
              key="order"
              :label="t('system.role.sort')"
              prop="order"
              min-width="80"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('system.role.status')"
              prop="status"
              min-width="80"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0" ? t("system.role.enable") : t("system.role.disable")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.role.description')"
              prop="description"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.role.createTime')"
              prop="created_time"
              min-width="200"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              key="updated_time"
              :label="t('system.role.updateTime')"
              prop="updated_time"
              min-width="200"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.role.operation')"
              align="center"
              min-width="280"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:role:permission']"
                  type="warning"
                  size="small"
                  link
                  icon="position"
                  :disabled="scope.row.id === 1"
                  @click="
                    scope.row.id === 1
                      ? ElMessage.warning(t('system.role.systemDefaultRole'))
                      : handleOpenAssignPermDialog(scope.row.id, scope.row.name)
                  "
                >
                  {{ t("system.role.assignPermission") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:role:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.role.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:role:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  :disabled="scope.row.id === 1"
                  @click="
                    scope.row.id === 1
                      ? ElMessage.warning(t('system.role.systemDefaultRole'))
                      : handleOpenDialog('update', scope.row.id)
                  "
                >
                  {{ t("system.role.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:role:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  :disabled="scope.row.id === 1"
                  @click="
                    scope.row.id === 1
                      ? ElMessage.warning(t('system.role.systemDefaultRole'))
                      : handleRowDelete(scope.row.id)
                  "
                >
                  {{ t("system.role.delete") }}
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
          <el-descriptions-item :label="t('system.role.roleName')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.sort')" :span="2">
            {{ detailFormData.order }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.roleCode')" :span="2">
            {{ detailFormData.code }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.dataScope')" :span="2">
            <el-tag v-if="detailFormData.data_scope === 1" type="primary">
              {{ t("system.role.scopeOnlySelf") }}
            </el-tag>
            <el-tag v-else-if="detailFormData.data_scope === 2" type="info">
              {{ t("system.role.scopeDept") }}
            </el-tag>
            <el-tag v-else-if="detailFormData.data_scope === 3" type="warning">
              {{ t("system.role.scopeDeptAndBelow") }}
            </el-tag>
            <el-tag v-else-if="detailFormData.data_scope === 4" type="success">
              {{ t("system.role.scopeAll") }}
            </el-tag>
            <el-tag v-else type="danger">{{ t("system.role.scopeCustom") }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.dept')" :span="2">
            <template v-if="detailFormData.depts && detailFormData.depts.length > 0">
              <el-tag
                v-for="dept in detailFormData.depts"
                :key="dept.id"
                type="info"
                style="margin-right: 4px; margin-bottom: 4px"
              >
                {{ dept.name }}
              </el-tag>
            </template>
            <span v-else style="color: var(--el-text-color-placeholder)">-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.status')" :span="2">
            <el-tag :type="detailFormData.status === '0' ? 'success' : 'danger'">
              {{
                detailFormData.status === "0" ? t("system.role.enable") : t("system.role.disable")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.createTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.updateTime')" :span="2">
            {{ detailFormData.updated_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.role.description')" :span="4">
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
          <el-form-item :label="t('system.role.roleName')" prop="name">
            <el-input v-model="formData.name" :placeholder="t('system.role.inputRoleName')" />
          </el-form-item>

          <el-form-item :label="t('system.role.sort')" prop="order">
            <el-input-number
              v-model="formData.order"
              controls-position="right"
              :min="0"
              style="width: 100px"
            />
          </el-form-item>

          <el-form-item :label="t('system.role.roleCode')" prop="code">
            <el-input
              v-model="formData.code"
              :placeholder="t('system.role.codePlaceholder')"
              maxlength="16"
              show-word-limit
            />
          </el-form-item>

          <el-form-item :label="t('system.role.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.role.enable") }}</el-radio>
              <el-radio value="1">{{ t("system.role.disable") }}</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('system.role.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.role.inputDescription')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.role.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type !== 'detail'"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.role.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.role.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>

    <PermissonDrawer
      v-if="drawerVisible"
      v-model="drawerVisible"
      :role-name="checkedRole.name"
      :role-id="checkedRole.id"
      @saved="refreshList"
    />

    <ExportModal
      v-model="exportsDialogVisible"
      :content-config="curdContentConfig"
      :query-params="exportQueryParams"
      :page-data="exportPageData"
      :selection-data="exportSelectionData"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Role",
  inheritAttrs: false,
});

import { ElMessage, ElMessageBox } from "element-plus";
import { ref, reactive, computed, unref } from "vue";
import { fetchAllPages } from "@/utils/fetchAllPages";
import RoleAPI, { RoleTable, RoleForm, TablePageQuery } from "@/api/module_system/role";
import { useUserStore } from "@/store";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import PermissonDrawer from "./components/PermissonDrawer.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const submitLoading = ref(false);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:role",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("system.role.roleName"),
      type: "input",
      attrs: { placeholder: t("system.role.inputRoleName"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.role.status"),
      type: "select",
      options: [
        { label: t("system.role.enable"), value: "true" },
        { label: t("system.role.disable"), value: "false" },
      ],
      attrs: {
        placeholder: t("system.role.selectStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.role.createTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.role.to"),
        startPlaceholder: t("system.role.startDate"),
        endPlaceholder: t("system.role.endDate"),
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
  { prop: "selection", label: t("system.role.selection"), show: true },
  { prop: "index", label: t("system.role.indexNo"), show: true },
  { prop: "name", label: t("system.role.roleName"), show: true },
  { prop: "data_scope", label: t("system.role.dataScope"), show: true },
  { prop: "depts", label: t("system.role.dept"), show: true },
  { prop: "order", label: t("system.role.sort"), show: true },
  { prop: "code", label: t("system.role.roleCode"), show: true },
  { prop: "status", label: t("system.role.status"), show: true },
  { prop: "description", label: t("system.role.description"), show: true },
  { prop: "created_time", label: t("system.role.createTime"), show: true },
  { prop: "updated_time", label: t("system.role.updateTime"), show: true },
  { prop: "operation", label: t("system.role.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_system:role",
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
    const res = await RoleAPI.listRole(params as TablePageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await RoleAPI.deleteRole(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    const userStore = useUserStore();
    await userStore.getUserInfo();
  },
  deleteConfirm: {
    title: t("system.role.warning"),
    message: t("system.role.deleteConfirmMessage"),
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const drawerVisible = ref(false);
const checkedRole = ref({ id: 0, name: "" });

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => (unref(contentRef.value?.pageData) ?? []) as RoleTable[]);

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as RoleTable[]
);

const exportColumns = [
  { prop: "name", label: t("system.role.roleName") },
  { prop: "code", label: t("system.role.roleCode") },
  { prop: "data_scope", label: t("system.role.dataScope") },
  { prop: "depts", label: t("system.role.dept") },
  { prop: "order", label: t("system.role.sort") },
  { prop: "status", label: t("system.role.status") },
  { prop: "description", label: t("system.role.description") },
  { prop: "created_time", label: t("system.role.createTime") },
  { prop: "updated_time", label: t("system.role.updateTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:role",
  cols: exportColumns as unknown as IContentConfig["cols"],
  exportsAction: async (params: Record<string, unknown>) => {
    const query: Record<string, unknown> = { ...params };
    if (typeof query.status === "string") {
      query.status = query.status === "true";
    }
    return fetchAllPages<RoleTable>({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await RoleAPI.listRole(q as unknown as TablePageQuery);
        return {
          total: res.data?.data?.total ?? 0,
          list: res.data?.data?.items ?? [],
        };
      },
    });
  },
} as unknown as IContentConfig;

function handleOpenExportsModal() {
  exportsDialogVisible.value = true;
}

const detailFormData = ref<RoleTable>({} as RoleTable);

const formData = reactive<RoleForm>({
  id: undefined,
  name: undefined,
  order: 1,
  code: "",
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
  name: [{ required: true, message: t("system.role.inputRoleName"), trigger: "blur" }],
  code: [
    { required: true, message: t("system.role.inputRoleCode"), trigger: "blur" },
    {
      pattern: CODE_PATTERN,
      message: t("system.role.codePlaceholder"),
      trigger: "blur",
    },
  ],
  order: [{ required: true, message: t("system.role.inputSort"), trigger: "blur" }],
  status: [{ required: true, message: t("system.role.selectStatus"), trigger: "blur" }],
});

const initialFormData: RoleForm = {
  id: undefined,
  name: undefined,
  order: 1,
  code: "",
  status: "0",
  description: undefined,
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

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await RoleAPI.detailRole(id);
    if (type === "detail") {
      dialogVisible.title = t("system.role.roleDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.role.updateRole");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.role.createRole");
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
          await RoleAPI.updateRole(id, { id, ...formData });
        } else {
          await RoleAPI.createRole(formData);
        }
        ElMessage.success(t("system.role.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        const userStore = useUserStore();
        await userStore.getUserInfo();
      } catch (error: unknown) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as RoleTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.role.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(
    status === "0" ? t("system.role.confirmEnable") : t("system.role.confirmDisable"),
    t("system.role.warning"),
    {
      confirmButtonText: t("system.role.confirm"),
      cancelButtonText: t("system.role.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await RoleAPI.batchRole({ ids, status });
        ElMessage.success(t("system.role.operationSuccess"));
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

function handleOpenAssignPermDialog(roleId: number, roleName: string) {
  checkedRole.value = { id: roleId, name: roleName };
  drawerVisible.value = true;
}
</script>
