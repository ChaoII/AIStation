<!-- 租户管理 -->
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
          :perm-create="['module_system:tenant:create']"
          :perm-delete="['module_system:tenant:delete']"
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
              <el-empty :image-size="80" :description="t('system.tenant.noData')" />
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
              :label="t('system.tenant.index')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('system.tenant.tenantName')"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'code')?.show"
              key="code"
              :label="t('system.tenant.tenantCode')"
              prop="code"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('system.tenant.status')"
              prop="status"
              min-width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0"
                      ? t("system.tenant.normal")
                      : t("system.tenant.disabled")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'start_time')?.show"
              key="start_time"
              :label="t('system.tenant.startTime')"
              prop="start_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'end_time')?.show"
              key="end_time"
              :label="t('system.tenant.endTime')"
              prop="end_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.tenant.description')"
              prop="description"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.tenant.createTime')"
              prop="created_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.tenant.operation')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:tenant:query']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.tenant.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:tenant:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.tenant.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:tenant:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.tenant.delete") }}
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
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('system.tenant.tenantName')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.tenantCode')" :span="2">
            {{ detailFormData.code }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.status')">
            <el-tag :type="detailFormData.status === '0' ? 'success' : 'danger'">
              {{
                detailFormData.status === "0"
                  ? t("system.tenant.normal")
                  : t("system.tenant.disabled")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.startTime')">
            {{ detailFormData.start_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.endTime')">
            {{ detailFormData.end_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.description')" :span="2">
            {{ detailFormData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.tenant.createTime')" :span="2">
            {{ detailFormData.created_time }}
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
          <el-form-item :label="t('system.tenant.tenantName')" prop="name">
            <el-input
              v-model="formData.name"
              :placeholder="t('system.tenant.placeholderTenantName')"
              :maxlength="100"
            />
          </el-form-item>
          <el-form-item :label="t('system.tenant.tenantCode')" prop="code">
            <el-input
              v-model="formData.code"
              :placeholder="t('system.tenant.codeHelp')"
              :maxlength="100"
              :disabled="dialogVisible.type === 'update'"
            />
          </el-form-item>
          <el-form-item :label="t('system.tenant.status')" prop="status">
            <el-select
              v-model="formData.status"
              :placeholder="t('system.tenant.placeholderSelectStatus')"
              style="width: 100%"
            >
              <el-option :label="t('system.tenant.normal')" value="0" />
              <el-option :label="t('system.tenant.disabled')" value="1" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('system.tenant.description')" prop="description">
            <el-input
              v-model="formData.description"
              type="textarea"
              :rows="3"
              :placeholder="t('system.tenant.placeholderDescription')"
              :maxlength="255"
            />
          </el-form-item>
          <el-form-item :label="t('system.tenant.startTime')" prop="start_time">
            <el-date-picker
              v-model="formData.start_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('system.tenant.optional')"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="t('system.tenant.endTime')" prop="end_time">
            <el-date-picker
              v-model="formData.end_time"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('system.tenant.optional')"
              style="width: 100%"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.tenant.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type === 'create'"
            v-hasPerm="['module_system:tenant:create']"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.tenant.confirm") }}
          </el-button>
          <el-button
            v-else-if="dialogVisible.type === 'update'"
            v-hasPerm="['module_system:tenant:update']"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.tenant.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.tenant.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { ref, reactive } from "vue";
import { useI18n } from "vue-i18n";
import TenantAPI, {
  TenantForm,
  TenantCreateForm,
  TenantUpdateForm,
  TenantPageQuery,
  TenantTable,
} from "@/api/module_system/tenant";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";

defineOptions({
  name: "Tenant",
  inheritAttrs: false,
});

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const { t } = useI18n();
const dataFormRef = ref();
const submitLoading = ref(false);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:tenant",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("system.tenant.tenantName"),
      type: "input",
      attrs: { placeholder: t("system.tenant.placeholderTenantName"), clearable: true },
    },
    {
      prop: "code",
      label: t("system.tenant.tenantCode"),
      type: "input",
      attrs: { placeholder: t("system.tenant.placeholderTenantCode"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.tenant.status"),
      type: "select",
      attrs: {
        placeholder: t("system.tenant.placeholderSelectStatus"),
        clearable: true,
        options: [
          { label: t("system.tenant.normal"), value: "0" },
          { label: t("system.tenant.disabled"), value: "1" },
        ],
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.tenant.createTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.tenant.to"),
        startPlaceholder: t("system.tenant.startDatePlaceholder"),
        endPlaceholder: t("system.tenant.endDatePlaceholder"),
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
  { prop: "selection", label: t("system.tenant.selection"), show: true },
  { prop: "index", label: t("system.tenant.index"), show: true },
  { prop: "name", label: t("system.tenant.tenantName"), show: true },
  { prop: "code", label: t("system.tenant.tenantCode"), show: true },
  { prop: "status", label: t("system.tenant.status"), show: true },
  { prop: "description", label: t("system.tenant.description"), show: true },
  { prop: "created_time", label: t("system.tenant.createTime"), show: true },
  { prop: "operation", label: t("system.tenant.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<TenantPageQuery>>({
  permPrefix: "module_system:tenant",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["import", "export", "refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await TenantAPI.listTenant(params as TenantPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    const idList = ids
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => !Number.isNaN(n));
    await TenantAPI.deleteTenant(idList);
  },
  deleteConfirm: {
    title: t("system.tenant.deleteConfirmTitle"),
    message: t("system.tenant.deleteConfirmMessage"),
    type: "warning",
  },
});

const detailFormData = ref<TenantTable>({ code: "", name: "", status: "0" });

const currentEditId = ref<number | null>(null);

const formData = reactive<TenantForm>({
  name: "",
  code: "",
  status: "0",
  description: "",
  start_time: undefined,
  end_time: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const CODE_PATTERN = /^[A-Za-z0-9]+$/;

const validateTimeRange = (rule: any, value: any, callback: any) => {
  if (formData.start_time && formData.end_time && formData.start_time > formData.end_time) {
    callback(new Error(t("system.tenant.ruleTimeRange")));
  } else {
    callback();
  }
};

const rules = reactive({
  name: [{ required: true, message: t("system.tenant.ruleTenantNameRequired"), trigger: "blur" }],
  code: [
    { required: true, message: t("system.tenant.ruleTenantCodeRequired"), trigger: "blur" },
    {
      pattern: CODE_PATTERN,
      message: t("system.tenant.ruleCodePattern"),
      trigger: "blur",
    },
  ],
  end_time: [{ validator: validateTimeRange, trigger: "change" }],
});

const initialFormData: TenantForm = {
  name: "",
  code: "",
  status: "0",
  description: "",
  start_time: undefined,
  end_time: undefined,
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
  currentEditId.value = null;
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await TenantAPI.detailTenant(id);
    if (type === "detail") {
      dialogVisible.title = t("system.tenant.tenantDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.tenant.updateTenant");
      Object.assign(formData, response.data.data);
      currentEditId.value = id;
    }
  } else {
    dialogVisible.title = t("system.tenant.addTenant");
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = currentEditId.value;
      try {
        if (id) {
          const payload: TenantUpdateForm = {
            name: formData.name,
            start_time: formData.start_time,
            end_time: formData.end_time,
          };
          await TenantAPI.updateTenant(id, payload);
        } else {
          const payload: TenantCreateForm = {
            name: formData.name as string,
            code: formData.code as string,
            start_time: formData.start_time,
            end_time: formData.end_time,
          };
          await TenantAPI.createTenant(payload);
        }
        ElMessage.success(t("system.tenant.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}
</script>
