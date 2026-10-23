<!-- 字典数据 -->
<template>
  <EnhancedDrawer
    v-model="drawerVisible"
    :title="t('system.dict.drawerTitle', { label: dictLabel })"
    direction="rtl"
    :size="drawerSize"
  >
    <div class="drawer-content">
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
            :perm-create="['module_system:dict_data:create']"
            :perm-delete="['module_system:dict_data:delete']"
            :perm-patch="['module_system:dict_data:patch']"
            @add="handleOpenDialog('create')"
            @delete="onToolbar('delete')"
            @more="handleMoreClick"
          />
          <div class="data-table__toolbar--right">
            <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
              <template #prepend>
                <el-tooltip :content="t('system.dict.export')">
                  <el-button
                    v-hasPerm="['module_system:dict_data:export']"
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
                <el-empty :image-size="80" :description="t('system.dict.noData')" />
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
                :label="t('system.dict.index')"
                min-width="60"
              >
                <template #default="scope">
                  {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'dict_label')?.show"
                :label="t('system.dict.dictLabel')"
                prop="dict_label"
                min-width="150"
                show-overflow-tooltip
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'status')?.show"
                :label="t('system.dict.status')"
                prop="status"
                min-width="100"
                show-overflow-tooltip
              >
                <template #default="scope">
                  <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                    {{
                      scope.row.status === "0"
                        ? t("system.dict.enabled")
                        : t("system.dict.disabled")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'dict_type')?.show"
                :label="t('system.dict.type')"
                prop="dict_type"
                min-width="180"
                show-overflow-tooltip
              >
                <template #default="scope">
                  <el-tag type="primary">{{ scope.row.dict_type }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'dict_value')?.show"
                :label="t('system.dict.value')"
                prop="dict_value"
                min-width="100"
                show-overflow-tooltip
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'css_class')?.show"
                :label="t('system.dict.cssClass')"
                prop="css_class"
                min-width="100"
                show-overflow-tooltip
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'list_class')?.show"
                :label="t('system.dict.listClass')"
                prop="list_class"
                min-width="100"
                show-overflow-tooltip
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'dict_sort')?.show"
                :label="t('system.dict.sort')"
                prop="dict_sort"
                min-width="60"
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'is_default')?.show"
                :label="t('system.dict.isDefault')"
                prop="is_default"
                min-width="100"
              >
                <template #default="scope">
                  <el-tag v-if="scope.row.is_default" type="success">
                    {{ t("system.dict.yes") }}
                  </el-tag>
                  <el-tag v-else type="danger">{{ t("system.dict.no") }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'description')?.show"
                :label="t('system.dict.description')"
                prop="description"
                min-width="100"
                show-overflow-tooltip
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
                :label="t('system.dict.createdTime')"
                prop="created_time"
                min-width="200"
                sortable
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
                :label="t('system.dict.updatedTime')"
                prop="updated_time"
                min-width="200"
                sortable
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'operation')?.show"
                fixed="right"
                :label="t('system.dict.operation')"
                align="center"
                min-width="200"
              >
                <template #default="scope">
                  <el-button
                    v-hasPerm="['module_system:dict_data:detail']"
                    type="info"
                    size="small"
                    link
                    icon="View"
                    @click="handleOpenDialog('detail', scope.row.id)"
                  >
                    {{ t("system.dict.detail") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_system:dict_data:update']"
                    type="primary"
                    size="small"
                    link
                    icon="edit"
                    @click="handleOpenDialog('update', scope.row.id)"
                  >
                    {{ t("system.dict.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_system:dict_data:delete']"
                    type="danger"
                    size="small"
                    link
                    icon="delete"
                    @click="handleRowDelete(scope.row.id)"
                  >
                    {{ t("system.dict.delete") }}
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
            <el-descriptions-item :label="t('system.dict.dictDataLabel')" :span="2">
              {{ detailFormData.dict_label }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.dictDataType')" :span="2">
              {{ detailFormData.dict_type }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.dictDataValue')" :span="2">
              {{ detailFormData.dict_value }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.cssClass')" :span="2">
              {{ detailFormData.css_class }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.listClassProperty')" :span="2">
              {{ detailFormData.list_class }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.isDefault')" :span="2">
              <el-tag v-if="detailFormData.is_default" type="success">
                {{ t("system.dict.yes") }}
              </el-tag>
              <el-tag v-else type="danger">{{ t("system.dict.no") }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.status')" :span="2">
              <el-tag v-if="detailFormData.status === '0'" type="success">
                {{ t("system.dict.enabled") }}
              </el-tag>
              <el-tag v-else type="danger">{{ t("system.dict.disabled") }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.sort')" :span="2">
              {{ detailFormData.dict_sort }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.description')" :span="2">
              {{ detailFormData.description }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.createdTime')" :span="2">
              {{ detailFormData.created_time }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('system.dict.updatedTime')" :span="2">
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
            <el-form-item :label="t('system.dict.dictDataType')" prop="dict_type">
              <el-input
                v-model="formData.dict_type"
                :placeholder="t('system.dict.inputDataType')"
                :maxlength="50"
                :disabled="true"
              />
            </el-form-item>
            <el-form-item :label="t('system.dict.dictDataLabel')" prop="dict_label">
              <el-input
                v-model="formData.dict_label"
                :placeholder="t('system.dict.inputDataLabel')"
                :maxlength="255"
              />
            </el-form-item>
            <el-form-item :label="t('system.dict.dictDataValue')" prop="dict_value">
              <el-input
                v-model="formData.dict_value"
                :placeholder="t('system.dict.inputDataValue')"
                :maxlength="255"
              />
            </el-form-item>
            <el-form-item :label="t('system.dict.cssClass')" prop="css_class">
              <el-select
                v-model="formData.css_class"
                :placeholder="t('system.dict.selectColorOrCustom')"
                clearable
                filterable
                allow-create
                default-first-option
              >
                <el-option value="primary" :label="t('system.dict.tagPrimary')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('primary')">
                    {{ t("system.dict.tagPrimary") }}
                  </span>
                </el-option>
                <el-option value="success" :label="t('system.dict.tagSuccess')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('success')">
                    {{ t("system.dict.tagSuccess") }}
                  </span>
                </el-option>
                <el-option value="warning" :label="t('system.dict.tagWarning')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('warning')">
                    {{ t("system.dict.tagWarning") }}
                  </span>
                </el-option>
                <el-option value="danger" :label="t('system.dict.tagDanger')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('danger')">
                    {{ t("system.dict.tagDanger") }}
                  </span>
                </el-option>
                <el-option value="info" :label="t('system.dict.tagInfo')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('info')">
                    {{ t("system.dict.tagInfo") }}
                  </span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item :label="t('system.dict.listClass')" prop="list_class">
              <el-select
                v-model="formData.list_class"
                :placeholder="t('system.dict.selectListClass')"
                clearable
              >
                <el-option value="default" :label="t('system.dict.tagDefault')">
                  <span class="tag-option-preview tag-option-preview--default">
                    {{ t("system.dict.tagDefault") }}
                  </span>
                </el-option>
                <el-option value="primary" :label="t('system.dict.tagPrimary')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('primary')">
                    {{ t("system.dict.tagPrimary") }}
                  </span>
                </el-option>
                <el-option value="success" :label="t('system.dict.tagSuccess')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('success')">
                    {{ t("system.dict.tagSuccess") }}
                  </span>
                </el-option>
                <el-option value="warning" :label="t('system.dict.tagWarning')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('warning')">
                    {{ t("system.dict.tagWarning") }}
                  </span>
                </el-option>
                <el-option value="danger" :label="t('system.dict.tagDanger')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('danger')">
                    {{ t("system.dict.tagDanger") }}
                  </span>
                </el-option>
                <el-option value="info" :label="t('system.dict.tagInfo')">
                  <span class="tag-option-preview" :style="getTagPreviewStyle('info')">
                    {{ t("system.dict.tagInfo") }}
                  </span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item :label="t('system.dict.isDefault')" prop="is_default">
              <el-radio-group v-model="formData.is_default">
                <el-radio :value="true">{{ t("system.dict.yes") }}</el-radio>
                <el-radio :value="false">{{ t("system.dict.no") }}</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('system.dict.sort')" prop="dict_sort">
              <el-input-number v-model="formData.dict_sort" controls-position="right" :min="1" />
            </el-form-item>
            <el-form-item :label="t('system.dict.status')" prop="status">
              <el-switch
                v-model="formData.status"
                inline-prompt
                :active-value="'0'"
                :inactive-value="'1'"
              />
            </el-form-item>

            <el-form-item :label="t('system.dict.description')" prop="description">
              <el-input
                v-model="formData.description"
                :rows="4"
                :maxlength="100"
                show-word-limit
                type="textarea"
                :placeholder="t('system.dict.inputDescription')"
              />
            </el-form-item>
          </el-form>
        </template>

        <template #footer>
          <div class="dialog-footer">
            <el-button @click="handleCloseDialog">{{ t("system.dict.cancel") }}</el-button>
            <el-button v-if="dialogVisible.type !== 'detail'" type="primary" @click="handleSubmit">
              {{ t("system.dict.confirm") }}
            </el-button>
            <el-button v-else type="primary" @click="handleCloseDialog">
              {{ t("system.dict.confirm") }}
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
  </EnhancedDrawer>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import DictAPI, { DictDataTable, DictDataForm, DictDataPageQuery } from "@/api/module_system/dict";
import { ElMessage } from "element-plus";
import { useDictStore } from "@/store";
import { useAppStore } from "@/store/modules/app.store";
import { DeviceEnum } from "@/enums/settings/device.enum";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import EnhancedDrawer from "@/components/CURD/EnhancedDrawer.vue";
import type { ISearchConfig, IContentConfig, IObject } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { computed, ref, reactive, unref } from "vue";
import { fetchAllPages } from "@/utils/fetchAllPages";

const { t } = useI18n();

const props = defineProps({
  dictType: {
    type: String,
    required: true,
  },
  dictLabel: {
    type: String,
    required: true,
  },
  dictTypeId: {
    type: Number,
    required: true,
  },
});

const TAG_TYPE_STYLE_MAP: Record<string, { background: string; color: string; border: string }> = {
  primary: {
    background: "var(--el-color-primary-light-9)",
    color: "var(--el-color-primary)",
    border: "var(--el-color-primary-light-7)",
  },
  success: {
    background: "var(--el-color-success-light-9)",
    color: "var(--el-color-success)",
    border: "var(--el-color-success-light-7)",
  },
  warning: {
    background: "var(--el-color-warning-light-9)",
    color: "var(--el-color-warning)",
    border: "var(--el-color-warning-light-7)",
  },
  danger: {
    background: "var(--el-color-danger-light-9)",
    color: "var(--el-color-danger)",
    border: "var(--el-color-danger-light-7)",
  },
  info: {
    background: "var(--el-color-info-light-9)",
    color: "var(--el-color-info)",
    border: "var(--el-color-info-light-7)",
  },
};

const drawerVisible = defineModel<boolean>({ required: true });

const appStore = useAppStore();
const dictStore = useDictStore();
const drawerSize = computed(() => (appStore.device === DeviceEnum.DESKTOP ? "80%" : "60%"));

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:dict_data",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "dict_label",
      label: t("system.dict.dictDataLabelSearch"),
      type: "input",
      attrs: { placeholder: t("system.dict.inputDictLabel"), clearable: true },
    },
    {
      prop: "status",
      label: t("system.dict.status"),
      type: "select",
      options: [
        { label: t("system.dict.enabled"), value: "0" },
        { label: t("system.dict.disabled"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.dict.selectStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.dict.createdTime"),
      type: "date-picker",
      attrs: {
        type: "datetimerange",
        rangeSeparator: t("system.dict.to"),
        startPlaceholder: t("system.dict.startDate"),
        endPlaceholder: t("system.dict.endDate"),
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
  { prop: "selection", label: t("system.dict.checkbox"), show: true },
  { prop: "index", label: t("system.dict.index"), show: true },
  { prop: "dict_label", label: t("system.dict.dictLabel"), show: true },
  { prop: "status", label: t("system.dict.status"), show: true },
  { prop: "dict_type", label: t("system.dict.type"), show: true },
  { prop: "dict_value", label: t("system.dict.value"), show: true },
  { prop: "css_class", label: t("system.dict.cssClass"), show: true },
  { prop: "list_class", label: t("system.dict.listClass"), show: true },
  { prop: "dict_sort", label: t("system.dict.sort"), show: true },
  { prop: "is_default", label: t("system.dict.isDefault"), show: true },
  { prop: "description", label: t("system.dict.description"), show: true },
  { prop: "created_time", label: t("system.dict.createdTime"), show: true },
  { prop: "updated_time", label: t("system.dict.updatedTime"), show: true },
  { prop: "operation", label: t("system.dict.operation"), show: true },
]);

function getTagPreviewStyle(value?: string) {
  const preset = value ? TAG_TYPE_STYLE_MAP[value] : undefined;
  if (preset) {
    return {
      backgroundColor: preset.background,
      color: preset.color,
      borderColor: preset.border,
    };
  }
  if (!value) return {};
  return {
    backgroundColor: value,
    color: "#fff",
    borderColor: value,
  };
}

function mergeDictQuery(params: IObject): DictDataPageQuery {
  return {
    ...params,
    dict_type: props.dictType,
    dict_type_id: props.dictTypeId,
  } as DictDataPageQuery;
}

const contentConfig = reactive<IContentConfig<DictDataPageQuery>>({
  permPrefix: "module_system:dict_data",
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
    const res = await DictAPI.listDictData(mergeDictQuery(params as IObject));
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await DictAPI.deleteDictData(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    dictStore.clearDictData();
    if (props.dictType) {
      await dictStore.getDict([props.dictType]);
    }
  },
  deleteConfirm: {
    title: t("system.dict.warning"),
    message: t("system.dict.confirmDeleteMessage"),
    type: "warning",
  },
});

const detailFormData = ref<DictDataTable>({});

const formData = reactive<DictDataForm>({
  id: undefined,
  dict_sort: 1,
  dict_label: "",
  dict_value: "",
  dict_type: "",
  css_class: "",
  list_class: undefined,
  is_default: false,
  status: "0",
  description: "",
  dict_type_id: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  dict_label: [
    { required: true, message: t("system.dict.messageDictLabelRequired"), trigger: "blur" },
  ],
  dict_type: [
    { required: true, message: t("system.dict.messageDataTypeRequired"), trigger: "blur" },
  ],
  dict_value: [
    { required: true, message: t("system.dict.messageDictValueRequired"), trigger: "blur" },
  ],
  status: [{ required: true, message: t("system.dict.messageStatusRequired"), trigger: "blur" }],
  dict_sort: [{ required: true, message: t("system.dict.messageSortRequired"), trigger: "blur" }],
  is_default: [
    { required: true, message: t("system.dict.messageIsDefaultRequired"), trigger: "blur" },
  ],
});

const initialFormData: DictDataForm = {
  id: undefined,
  dict_sort: 1,
  dict_label: "",
  dict_value: "",
  dict_type: "",
  css_class: "",
  list_class: undefined,
  is_default: false,
  status: "0",
  description: "",
  dict_type_id: props.dictTypeId,
};

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => mergeDictQuery(searchRef.value?.getQueryParams() ?? {}));

const exportPageData = computed(() => {
  const pd = contentRef.value?.pageData;
  return (unref(pd) ?? []) as DictDataTable[];
});

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as DictDataTable[]
);

const exportColumns = [
  { prop: "dict_label", label: t("system.dict.dictDataLabel") },
  { prop: "dict_type", label: t("system.dict.dictDataType") },
  { prop: "dict_value", label: t("system.dict.dictDataValue") },
  { prop: "css_class", label: t("system.dict.cssClass") },
  { prop: "list_class", label: t("system.dict.listClass") },
  { prop: "dict_sort", label: t("system.dict.sort") },
  { prop: "is_default", label: t("system.dict.isDefault") },
  { prop: "status", label: t("system.dict.status") },
  { prop: "description", label: t("system.dict.description") },
  { prop: "created_time", label: t("system.dict.createdTime") },
  { prop: "updated_time", label: t("system.dict.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:dict_data",
  cols: exportColumns as any,
  exportsAction: async (params: any) => {
    const query: Record<string, unknown> = { ...mergeDictQuery(params) };
    return fetchAllPages({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await DictAPI.listDictData(q as unknown as DictDataPageQuery);
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

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, { ...initialFormData, dict_type_id: props.dictTypeId });
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await DictAPI.detailDictData(id);
    if (type === "detail") {
      dialogVisible.title = t("system.dict.dialogDataDetailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.dict.dialogDataUpdateTitle");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.dict.dialogDataCreateTitle");
    Object.assign(formData, initialFormData);
    formData.dict_type = props.dictType;
    formData.status = "0";
    formData.id = undefined;
    formData.dict_type_id = props.dictTypeId;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: any) => {
    if (valid) {
      const id = formData.id;
      try {
        if (id) {
          await DictAPI.updateDictData(id, { id, ...formData });
        } else {
          await DictAPI.createDictData(formData);
        }
        ElMessage.success(t("system.dict.actionSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        dictStore.clearDictData();
        if (formData.dict_type) {
          await dictStore.getDict([formData.dict_type]);
        }
      } catch (error: any) {
        console.error(error);
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as DictDataTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.dict.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(
    t("system.dict.confirmToggle", {
      status: status === "0" ? t("system.dict.enabled") : t("system.dict.disabled"),
    }),
    t("system.dict.warning"),
    {
      confirmButtonText: t("system.dict.confirm"),
      cancelButtonText: t("system.dict.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await DictAPI.batchDictData({ ids, status });
        ElMessage.success(t("system.dict.actionSuccess"));
        refreshList();
        dictStore.clearDictData();
        if (props.dictType) {
          await dictStore.getDict([props.dictType]);
        }
      } catch (error: any) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}
</script>

<style lang="scss" scoped>
.drawer-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.drawer-content :deep(.el-card.data-table) {
  flex: 1;
  min-height: 0;
  margin-top: 16px;
}

.tag-option-preview {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
  padding: 4px 10px;
  font-size: 12px;
  line-height: 18px;
  text-align: center;
  border: 1px solid transparent;
  border-radius: 4px;
}

.tag-option-preview--default {
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-color: var(--el-border-color-lighter);
}
</style>
