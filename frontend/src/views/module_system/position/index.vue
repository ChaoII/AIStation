<!-- 岗位管理 -->
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
          :perm-create="['module_system:position:create']"
          :perm-delete="['module_system:position:delete']"
          :perm-patch="['module_system:position:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.position.export')">
                <el-button
                  v-hasPerm="['module_system:position:export']"
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
              <el-empty :image-size="80" :description="t('system.position.noData')" />
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
              :label="t('system.position.index')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('system.position.name')"
              prop="name"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('system.position.status')"
              prop="status"
              min-width="80"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0"
                      ? t("system.position.enable")
                      : t("system.position.disable")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'order')?.show"
              key="order"
              :label="t('system.position.order')"
              prop="order"
              min-width="80"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.position.description')"
              prop="description"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.position.createdTime')"
              prop="created_time"
              min-width="200"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              key="updated_time"
              :label="t('system.position.updatedTime')"
              prop="updated_time"
              min-width="200"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_id')?.show"
              key="created_id"
              :label="t('system.position.createdBy')"
              min-width="100"
            >
              <template #default="scope">
                {{ scope.row.created_by?.name }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_id')?.show"
              key="updated_id"
              :label="t('system.position.updatedBy')"
              min-width="100"
            >
              <template #default="scope">
                {{ scope.row.updated_by?.name }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.position.operation')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:position:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.position.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:position:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.position.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:position:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.position.delete") }}
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
          <el-descriptions-item :label="t('system.position.name')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.orderShort')" :span="2">
            {{ detailFormData.order }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.status')" :span="2">
            <el-tag v-if="detailFormData.status === '0'" type="success">
              {{ t("system.position.enable") }}
            </el-tag>
            <el-tag v-else type="danger">{{ t("system.position.disable") }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.createdBy')" :span="2">
            {{ detailFormData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.updatedBy')" :span="2">
            {{ detailFormData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.updatedTime')" :span="2">
            {{ detailFormData.updated_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.position.description')" :span="4">
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
          <el-form-item :label="t('system.position.name')" prop="name">
            <el-input
              v-model="formData.name"
              :placeholder="t('system.position.namePlaceholder')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.position.orderShort')" prop="order">
            <el-input-number v-model="formData.order" controls-position="right" :min="1" />
          </el-form-item>
          <el-form-item :label="t('system.position.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.position.enable") }}</el-radio>
              <el-radio value="1">{{ t("system.position.disable") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('system.position.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.position.descriptionPlaceholder')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.position.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type !== 'detail'"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.position.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.position.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>

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
  name: "Position",
  inheritAttrs: false,
});

import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import { ref, reactive, computed, markRaw, nextTick, unref } from "vue";
import { fetchAllPages } from "@/utils/fetchAllPages";
import PositionAPI, {
  PositionTable,
  PositionForm,
  PositionPageQuery,
} from "@/api/module_system/position";
import { useUserStore } from "@/store";
import UserTableSelect from "@/views/module_system/user/components/UserTableSelect.vue";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";

const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const submitLoading = ref(false);

function triggerUserSearch() {
  nextTick(() => refreshList());
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:position",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("system.position.name"),
      type: "input",
      attrs: { placeholder: t("system.position.namePlaceholder"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.position.status"),
      type: "select",
      options: [
        { label: t("system.position.enable"), value: "0" },
        { label: t("system.position.disable"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.position.statusPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.position.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.position.rangeSeparator"),
        startPlaceholder: t("system.position.startDate"),
        endPlaceholder: t("system.position.endDate"),
        style: { width: "340px" },
      },
    },
    {
      prop: "created_id",
      label: t("system.position.createdBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
  ],
  customComponents: {
    "user-table-select": markRaw(UserTableSelect),
  },
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: t("system.position.selection"), show: true },
  { prop: "index", label: t("system.position.index"), show: true },
  { prop: "name", label: t("system.position.name"), show: true },
  { prop: "order", label: t("system.position.order"), show: true },
  { prop: "status", label: t("system.position.status"), show: true },
  { prop: "description", label: t("system.position.description"), show: true },
  { prop: "created_time", label: t("system.position.createdTime"), show: true },
  { prop: "updated_time", label: t("system.position.updatedTime"), show: true },
  { prop: "created_id", label: t("system.position.createdBy"), show: true },
  { prop: "updated_id", label: t("system.position.updatedBy"), show: true },
  { prop: "operation", label: t("system.position.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<PositionPageQuery>>({
  permPrefix: "module_system:position",
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
    const res = await PositionAPI.listPosition(params as PositionPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await PositionAPI.deletePosition(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    const userStore = useUserStore();
    await userStore.getUserInfo();
  },
  deleteConfirm: {
    title: t("system.position.confirmTitle"),
    message: t("system.position.deleteConfirmMessage"),
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => (unref(contentRef.value?.pageData) ?? []) as PositionTable[]);

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as PositionTable[]
);

const exportColumns = [
  { prop: "name", label: t("system.position.name") },
  { prop: "order", label: t("system.position.order") },
  { prop: "status", label: t("system.position.status") },
  { prop: "description", label: t("system.position.description") },
  { prop: "created_time", label: t("system.position.createdTime") },
  { prop: "updated_time", label: t("system.position.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:position",
  cols: exportColumns as unknown as IContentConfig["cols"],
  exportsAction: async (params: Record<string, unknown>) => {
    const query = { ...params } as Record<string, unknown>;
    return fetchAllPages<PositionTable>({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await PositionAPI.listPosition(q as unknown as PositionPageQuery);
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

const detailFormData = ref<PositionTable>({});

const formData = reactive<PositionForm>({
  id: undefined,
  name: undefined,
  order: 1,
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  name: [{ required: true, message: t("system.position.nameRequired"), trigger: "blur" }],
  order: [{ required: true, message: t("system.position.orderRequired"), trigger: "blur" }],
  status: [{ required: true, message: t("system.position.statusRequired"), trigger: "blur" }],
});

const initialFormData: PositionForm = {
  id: undefined,
  name: undefined,
  order: 1,
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
    const response = await PositionAPI.detailPosition(id);
    if (type === "detail") {
      dialogVisible.title = t("system.position.detailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.position.updateTitle");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.position.createTitle");
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
          await PositionAPI.updatePosition(id, { id, ...formData });
        } else {
          await PositionAPI.createPosition(formData);
        }
        ElMessage.success(t("system.position.operationSuccess"));
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
  const rows = contentRef.value?.getSelectionData() as PositionTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.position.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(
    t("system.position.confirmStatusMessage", {
      action:
        status === "0"
          ? t("system.position.confirmStatusEnable")
          : t("system.position.confirmStatusDisable"),
    }),
    t("system.position.confirmTitle"),
    {
      confirmButtonText: t("system.position.confirm"),
      cancelButtonText: t("system.position.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await PositionAPI.batchPosition({ ids, status });
        ElMessage.success(t("system.position.operationSuccess"));
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
