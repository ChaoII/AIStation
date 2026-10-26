<!-- 系统配置 -->
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
        <!-- 与 PageContent 默认工具栏一致：flex 换行，避免 el-row/el-col 与外层 flex 挤压右侧按钮 -->
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_system:param:create']"
          :perm-delete="['module_system:param:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.param.export')">
                <el-button
                  v-hasPerm="['module_system:param:export']"
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
              <el-empty :image-size="80" :description="t('system.param.noData')" />
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
              :label="t('system.param.serial')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'config_name')?.show"
              key="config_name"
              :label="t('system.param.configName')"
              prop="config_name"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'config_key')?.show"
              key="config_key"
              :label="t('system.param.configKey')"
              prop="config_key"
              min-width="200"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'config_value')?.show"
              key="config_value"
              :label="t('system.param.configValue')"
              prop="config_value"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'config_type')?.show"
              key="config_type"
              :label="t('system.param.configType')"
              prop="config_type"
              min-width="100"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.config_type" type="success">
                  {{ t("system.param.yes") }}
                </el-tag>
                <el-tag v-else type="danger">{{ t("system.param.no") }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.param.description')"
              prop="description"
              min-width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.param.createdTime')"
              prop="created_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              key="updated_time"
              :label="t('system.param.updatedTime')"
              prop="updated_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.param.action')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:param:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.param.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:param:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.param.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:param:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.param.delete") }}
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
          <el-descriptions-item :label="t('system.param.configName')" :span="2">
            {{ detailFormData.config_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.configType')" :span="2">
            <el-tag v-if="detailFormData.config_type" type="success">
              {{ t("system.param.yes") }}
            </el-tag>
            <el-tag v-else type="danger">{{ t("system.param.no") }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.configKey')" :span="2">
            {{ detailFormData.config_key }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.configValue')" :span="2">
            {{ detailFormData.config_value }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.description')" :span="2">
            {{ detailFormData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.param.updatedTime')" :span="2">
            {{ detailFormData.updated_time }}
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
          <el-form-item :label="t('system.param.configName')" prop="config_name">
            <el-input
              v-model="formData.config_name"
              :placeholder="t('system.param.inputConfigName')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.param.configKey')" prop="config_key">
            <el-input
              v-model="formData.config_key"
              :placeholder="t('system.param.inputConfigKey')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.param.configValue')" prop="config_value">
            <el-input
              v-model="formData.config_value"
              :placeholder="t('system.param.inputConfigValue')"
              :maxlength="100"
            />
          </el-form-item>
          <el-form-item :label="t('system.param.configType')" prop="config_type">
            <el-radio-group v-model="formData.config_type">
              <el-radio :value="true">{{ t("system.param.yes") }}</el-radio>
              <el-radio :value="false">{{ t("system.param.no") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('system.param.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.param.inputDescription')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.param.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type !== 'detail'"
            v-hasPerm="['module_system:param:create']"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.param.confirm") }}
          </el-button>
          <el-button
            v-else
            v-hasPerm="['module_system:param:detail']"
            type="primary"
            @click="handleCloseDialog"
          >
            {{ t("system.param.confirm") }}
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
import { ElMessage } from "element-plus";
import { ref, reactive, computed, unref } from "vue";
import { useI18n } from "vue-i18n";
import { fetchAllPages } from "@/utils/fetchAllPages";
import ParamsAPI, { ConfigTable, ConfigForm, ConfigPageQuery } from "@/api/module_system/params";
import { useConfigStore } from "@/store";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig, IObject } from "@/components/CURD/types";

defineOptions({
  name: "Params",
  inheritAttrs: false,
});

const { t } = useI18n();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const submitLoading = ref(false);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:param",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "config_name",
      label: t("system.param.configName"),
      type: "input",
      attrs: { placeholder: t("system.param.inputConfigName"), clearable: true },
    },
    {
      prop: "config_key",
      label: t("system.param.configKeyName"),
      type: "input",
      attrs: { placeholder: t("system.param.inputConfigKeyName"), clearable: true },
    },
    {
      prop: "config_type",
      label: t("system.param.configType"),
      type: "select",
      options: [
        { label: t("system.param.yes"), value: "true" },
        { label: t("system.param.no"), value: "false" },
      ],
      attrs: {
        placeholder: t("system.param.selectConfigType"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.param.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.param.to"),
        startPlaceholder: t("system.param.startDate"),
        endPlaceholder: t("system.param.endDate"),
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
  { prop: "selection", label: t("system.param.selection"), show: true },
  { prop: "index", label: t("system.param.serial"), show: true },
  { prop: "config_name", label: t("system.param.configName"), show: true },
  { prop: "config_key", label: t("system.param.configKey"), show: true },
  { prop: "config_value", label: t("system.param.configValue"), show: true },
  { prop: "config_type", label: t("system.param.configType"), show: true },
  { prop: "description", label: t("system.param.description"), show: true },
  { prop: "created_time", label: t("system.param.createdTime"), show: true },
  { prop: "updated_time", label: t("system.param.updatedTime"), show: true },
  { prop: "operation", label: t("system.param.action"), show: true },
]);

const configStore = useConfigStore();

function normalizeListQuery(params: IObject): ConfigPageQuery {
  const q = { ...params } as IObject;
  if (typeof q.config_type === "string") {
    q.config_type = q.config_type === "true";
  }
  return q as unknown as ConfigPageQuery;
}

const contentConfig = reactive<IContentConfig<ConfigPageQuery>>({
  permPrefix: "module_system:param",
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
    const res = await ParamsAPI.listParams(normalizeListQuery(params as IObject));
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await ParamsAPI.deleteParams(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    configStore.isConfigLoaded = false;
    await configStore.getConfig();
  },
  deleteConfirm: {
    title: t("system.param.warnTitle"),
    message: t("system.param.deleteConfirmMessage"),
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const detailFormData = ref<ConfigTable>({} as ConfigTable);

const formData = reactive<ConfigForm>({
  id: undefined,
  config_name: "",
  config_key: "",
  config_value: "",
  config_type: false,
  description: "",
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  config_name: [{ required: true, message: t("system.param.requiredConfigName"), trigger: "blur" }],
  config_key: [{ required: true, message: t("system.param.requiredConfigKey"), trigger: "blur" }],
  config_value: [
    { required: true, message: t("system.param.requiredConfigValue"), trigger: "blur" },
  ],
  config_type: [{ required: true, message: t("system.param.requiredConfigType"), trigger: "blur" }],
});

const initialFormData: ConfigForm = {
  id: undefined,
  config_name: "",
  config_key: "",
  config_value: "",
  config_type: false,
  description: "",
};

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => (unref(contentRef.value?.pageData) ?? []) as ConfigTable[]);

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as ConfigTable[]
);

const exportColumns = [
  { prop: "config_name", label: t("system.param.configName") },
  { prop: "config_key", label: t("system.param.configKey") },
  { prop: "config_value", label: t("system.param.configValue") },
  { prop: "config_type", label: t("system.param.configType") },
  { prop: "description", label: t("system.param.description") },
  { prop: "created_time", label: t("system.param.createdTime") },
  { prop: "updated_time", label: t("system.param.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:param",
  cols: exportColumns as any,
  exportsAction: async (params: any) => {
    const query = { ...normalizeListQuery(params) } as Record<string, unknown>;
    return fetchAllPages({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await ParamsAPI.listParams(q as unknown as ConfigPageQuery);
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
    const response = await ParamsAPI.detailParams(id);
    if (type === "detail") {
      dialogVisible.title = t("system.param.configDetail");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.param.updateConfig");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.param.createConfig");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: any) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          await ParamsAPI.updateParams(id, { id, ...formData });
        } else {
          await ParamsAPI.createParams(formData);
        }
        ElMessage.success(t("system.param.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        configStore.isConfigLoaded = false;
        await configStore.getConfig();
      } catch (error: any) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}
</script>
