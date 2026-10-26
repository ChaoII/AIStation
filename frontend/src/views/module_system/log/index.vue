<!-- 日志管理 -->
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
          :perm-delete="['module_system:log:delete']"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.log.export')">
                <el-button
                  v-hasPerm="['module_system:log:export']"
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
              <el-empty :image-size="80" :description="t('system.log.noData')" />
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
              :label="t('system.log.serialNumber')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'type')?.show"
              :label="t('system.log.logType')"
              prop="type"
              min-width="100"
            >
              <template #default="scope">
                <el-tag :type="scope.row.type === 1 ? 'success' : 'primary'">
                  {{
                    scope.row.type === 1 ? t("system.log.loginLog") : t("system.log.operationLog")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'request_path')?.show"
              :label="t('system.log.requestPath')"
              prop="request_path"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'request_method')?.show"
              :label="t('system.log.requestMethod')"
              prop="request_method"
              min-width="100"
            >
              <template #default="scope">
                <el-tag :type="getMethodType(scope.row.request_method)">
                  {{ scope.row.request_method }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'response_code')?.show"
              :label="t('system.log.statusCode')"
              prop="response_code"
              min-width="100"
            >
              <template #default="scope">
                <el-tag :type="getStatusCodeType(scope.row.response_code)">
                  {{ scope.row.response_code }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'request_ip')?.show"
              :label="t('system.log.requestIp')"
              prop="request_ip"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-text>{{ scope.row.request_ip }}</el-text>
                <CopyButton
                  v-if="scope.row.request_ip"
                  :text="scope.row.request_ip"
                  :style="{ marginLeft: '2px' }"
                />
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'process_time')?.show"
              :label="t('system.log.processTime')"
              prop="process_time"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'request_browser')?.show"
              :label="t('system.log.browser')"
              prop="request_browser"
              min-width="220"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'request_os')?.show"
              :label="t('system.log.requestOs')"
              prop="request_os"
              min-width="100"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              :label="t('system.log.description')"
              prop="description"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              :label="t('system.log.createdTime')"
              prop="created_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_id')?.show"
              :label="t('system.log.createdBy')"
              prop="created_id"
              min-width="120"
            >
              <template #default="scope">
                {{ scope.row.created_by?.name }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_id')?.show"
              :label="t('system.log.updatedBy')"
              prop="updated_id"
              min-width="120"
            >
              <template #default="scope">
                {{ scope.row.updated_by?.name }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.log.operation')"
              align="center"
              min-width="150"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:log:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.log.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:log:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.log.delete") }}
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
        <el-descriptions :column="8" border label-width="200px">
          <el-descriptions-item :label="t('system.log.logType')" :span="2">
            <el-tag :type="formData.type === 1 ? 'success' : 'primary'">
              {{ formData.type === 1 ? t("system.log.loginLog") : t("system.log.operationLog") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.requestPath')" :span="2">
            {{ formData.request_path }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.requestMethod')" :span="2">
            <el-tag :type="getMethodType(formData.request_method)">
              {{ formData.request_method }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.responseStatusCode')" :span="2">
            <el-tag :type="getStatusCodeType(formData.response_code)">
              {{ formData.response_code }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.requestIp')" :span="2">
            {{ formData.request_ip }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.processTime')" :span="2">
            {{ formData.process_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.browser')" :span="2">
            {{ formData.request_browser }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.operatingSystem')" :span="2">
            {{ formData.request_os }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.requestParams')" :span="8">
            <JsonPretty :value="formData.request_payload" height="80px" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.responseData')" :span="8">
            <JsonPretty :value="formData.response_json" height="140px" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.loginLocation')" :span="4">
            {{ formData.login_location }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.description')" :span="8">
            {{ formData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.createdBy')" :span="4">
            {{ formData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.updatedBy')" :span="4">
            {{ formData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.createdTime')" :span="4">
            {{ formData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.log.updatedTime')" :span="4">
            {{ formData.updated_time }}
          </el-descriptions-item>
        </el-descriptions>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.log.cancel") }}</el-button>
          <el-button
            v-hasPerm="['module_system:log:detail']"
            type="primary"
            @click="handleCloseDialog"
          >
            {{ t("system.log.confirm") }}
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
  name: "Log",
  inheritAttrs: false,
});

import { ref, reactive, computed, unref, markRaw, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { fetchAllPages } from "@/utils/fetchAllPages";
import LogAPI, { LogTable, LogPageQuery } from "@/api/module_system/log";
import UserTableSelect from "@/views/module_system/user/components/UserTableSelect.vue";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import JsonPretty from "@/components/JsonPretty/index.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";

const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

function triggerUserSearch() {
  nextTick(() => refreshList());
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:log",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "request_path",
      label: t("system.log.requestPath"),
      type: "input",
      attrs: { placeholder: t("system.log.requestPathPlaceholder"), clearable: true },
    },
    {
      prop: "type",
      label: t("system.log.logType"),
      type: "select",
      options: [
        { label: t("system.log.loginLog"), value: 1 },
        { label: t("system.log.operationLog"), value: 2 },
      ],
      attrs: {
        placeholder: t("system.log.logTypePlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_id",
      label: t("system.log.createdBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
    {
      prop: "created_time",
      label: t("system.log.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.log.rangeSeparator"),
        startPlaceholder: t("system.log.startDate"),
        endPlaceholder: t("system.log.endDate"),
        style: { width: "340px" },
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
  { prop: "selection", label: t("system.log.selection"), show: true },
  { prop: "index", label: t("system.log.serialNumber"), show: true },
  { prop: "type", label: t("system.log.logType"), show: true },
  { prop: "request_path", label: t("system.log.requestPath"), show: true },
  { prop: "request_method", label: t("system.log.requestMethod"), show: true },
  { prop: "response_code", label: t("system.log.statusCode"), show: true },
  { prop: "request_ip", label: t("system.log.requestIp"), show: true },
  { prop: "process_time", label: t("system.log.processTime"), show: true },
  { prop: "request_browser", label: t("system.log.browser"), show: true },
  { prop: "request_os", label: t("system.log.requestOs"), show: true },
  { prop: "description", label: t("system.log.description"), show: true },
  { prop: "created_time", label: t("system.log.createdTime"), show: true },
  { prop: "created_id", label: t("system.log.createdBy"), show: true },
  { prop: "updated_id", label: t("system.log.updatedBy"), show: true },
  { prop: "operation", label: t("system.log.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<LogPageQuery>>({
  permPrefix: "module_system:log",
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
    const res = await LogAPI.listLog(params as LogPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await LogAPI.deleteLog(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: {
    title: t("system.log.warning"),
    message: t("system.log.deleteConfirmMessage"),
    type: "warning",
  },
});

const formData = ref<LogTable>({});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const getStatusCodeType = (code?: number) => {
  if (code === undefined) {
    return "info";
  }
  if (code >= 200 && code < 300) {
    return "success";
  } else if (code >= 300 && code < 400) {
    return "warning";
  } else if (code >= 400 && code < 500) {
    return "danger";
  } else {
    return "danger";
  }
};

const getMethodType = (method?: string) => {
  if (method === undefined) {
    return "info";
  }
  if (method === "GET") {
    return "info";
  } else if (method === "POST") {
    return "success";
  } else if (method === "PUT" || method === "PATCH") {
    return "warning";
  } else if (method === "DELETE") {
    return "danger";
  } else {
    return "info";
  }
};

async function resetForm() {
  formData.value.id = undefined;
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await LogAPI.detailLog(id);
    if (type === "detail") {
      dialogVisible.title = t("system.log.logDetail");
      Object.assign(formData.value, response.data.data);
    }
  }
  dialogVisible.visible = true;
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => {
  const pd = contentRef.value?.pageData;
  return (unref(pd) ?? []) as LogTable[];
});

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as LogTable[]
);

const exportColumns = [
  { prop: "type", label: t("system.log.logType") },
  { prop: "request_path", label: t("system.log.requestPath") },
  { prop: "request_method", label: t("system.log.requestMethod") },
  { prop: "response_code", label: t("system.log.statusCode") },
  { prop: "request_ip", label: t("system.log.requestIp") },
  { prop: "login_location", label: t("system.log.loginLocation") },
  { prop: "process_time", label: t("system.log.processTime") },
  { prop: "request_browser", label: t("system.log.browser") },
  { prop: "request_os", label: t("system.log.requestOs") },
  { prop: "description", label: t("system.log.description") },
  { prop: "created_time", label: t("system.log.createdTime") },
  { prop: "updated_time", label: t("system.log.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:log",
  cols: exportColumns as any,
  exportsAction: async (params: any) => {
    const query: Record<string, unknown> = { ...params };
    return fetchAllPages({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await LogAPI.listLog(q as unknown as LogPageQuery);
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
</script>

<style lang="scss" scoped></style>
