<!-- 字典 -->
<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent
      ref="contentRef"
      :content-config="contentConfig"
      @add-click="handleOpenDialog('create')"
    >
      <!-- 与 PageContent 默认结构一致：不再套一层 data-table__toolbar（外层已由组件提供） -->
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_system:dict_type:create']"
          :perm-delete="['module_system:dict_type:delete']"
          :perm-patch="['module_system:dict_type:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.dict.export')">
                <el-button
                  v-hasPerm="['module_system:dict_type:export']"
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
              v-if="contentCols.find((col) => col.prop === 'dict_name')?.show"
              key="dict_name"
              :label="t('system.dict.dictName')"
              prop="dict_name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'dict_type')?.show"
              key="dict_type"
              :label="t('system.dict.dictType')"
              prop="dict_type"
              min-width="180"
            >
              <template #default="scope">
                <el-tag type="primary">{{ scope.row.dict_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('system.dict.status')"
              prop="status"
              min-width="80"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0" ? t("system.dict.enabled") : t("system.dict.disabled")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              key="description"
              :label="t('system.dict.description')"
              prop="description"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              :label="t('system.dict.createdTime')"
              prop="created_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              key="updated_time"
              :label="t('system.dict.updatedTime')"
              prop="updated_time"
              min-width="200"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.dict.operation')"
              align="center"
              min-width="260"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:dict_data:query']"
                  type="warning"
                  size="small"
                  link
                  icon="Document"
                  @click="handleDictDataDrawer(scope.row)"
                >
                  {{ t("system.dict.dict") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dict_type:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.dict.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dict_type:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.dict.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:dict_type:delete']"
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
          <el-descriptions-item :label="t('system.dict.dictName')" :span="2">
            {{ detailFormData.dict_name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dict.dictType')" :span="2">
            <el-tag type="primary">{{ detailFormData.dict_type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.dict.status')" :span="2">
            <el-tag v-if="detailFormData.status === '0'" type="success">
              {{ t("system.dict.enabled") }}
            </el-tag>
            <el-tag v-else type="danger">{{ t("system.dict.disabled") }}</el-tag>
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
          <el-form-item :label="t('system.dict.dictName')" prop="dict_name">
            <el-input
              v-model="formData.dict_name"
              :placeholder="t('system.dict.inputDictName')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.dict.dictType')" prop="dict_type">
            <el-input
              v-model="formData.dict_type"
              :placeholder="t('system.dict.inputDictType')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.dict.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.dict.enabled") }}</el-radio>
              <el-radio value="1">{{ t("system.dict.disabled") }}</el-radio>
            </el-radio-group>
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
    <DataDrawer
      v-if="drawerVisible"
      v-model="drawerVisible"
      :dict-type="currentDictType"
      :dict-label="currentDictLabel"
      :dict-type-id="currentDictTypeId"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Dict",
  inheritAttrs: false,
});

import { useI18n } from "vue-i18n";
import DictAPI, { DictTable, DictForm, DictPageQuery } from "@/api/module_system/dict";
import { ElMessage } from "element-plus";
import { useDictStore } from "@/store";
import DataDrawer from "@/views/module_system/dict/components/DataDrawer.vue";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { computed, ref, reactive, unref } from "vue";
import { fetchAllPages } from "@/utils/fetchAllPages";

const { t } = useI18n();
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:dict_type",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "dict_name",
      label: t("system.dict.dictName"),
      type: "input",
      attrs: { placeholder: t("system.dict.inputDictName"), clearable: true },
    },
    {
      prop: "dict_type",
      label: t("system.dict.dictType"),
      type: "input",
      attrs: { placeholder: t("system.dict.inputDictType"), clearable: true },
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
  { prop: "dict_name", label: t("system.dict.dictName"), show: true },
  { prop: "dict_type", label: t("system.dict.dictType"), show: true },
  { prop: "status", label: t("system.dict.status"), show: true },
  { prop: "description", label: t("system.dict.description"), show: true },
  { prop: "created_time", label: t("system.dict.createdTime"), show: true },
  { prop: "updated_time", label: t("system.dict.updatedTime"), show: true },
  { prop: "operation", label: t("system.dict.operation"), show: true },
]);

const dictStore = useDictStore();

const contentConfig = reactive<IContentConfig<DictPageQuery>>({
  permPrefix: "module_system:dict_type",
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
    const res = await DictAPI.listDictType(params as DictPageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await DictAPI.deleteDictType(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    dictStore.clearDictData();
    const dictTypes = Object.keys(dictStore.dictData);
    if (dictTypes.length > 0) {
      await dictStore.getDict(dictTypes);
    }
  },
  deleteConfirm: {
    title: t("system.dict.warning"),
    message: t("system.dict.confirmDeleteMessage"),
    type: "warning",
  },
});

const detailFormData = ref<DictTable>({});

const formData = reactive<DictForm>({
  id: undefined,
  dict_name: "",
  dict_type: "",
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  dict_name: [
    { required: true, message: t("system.dict.messageDictNameRequired"), trigger: "blur" },
  ],
  dict_type: [
    { required: true, message: t("system.dict.messageDictTypeRequired"), trigger: "blur" },
  ],
  status: [
    { required: true, message: t("system.dict.messageDictStatusRequired"), trigger: "blur" },
  ],
});

const initialFormData: DictForm = {
  id: undefined,
  dict_name: "",
  dict_type: "",
  status: "0",
  description: undefined,
};

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => {
  const pd = contentRef.value?.pageData;
  return (unref(pd) ?? []) as DictTable[];
});

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as DictTable[]
);

const exportColumns = [
  { prop: "dict_name", label: t("system.dict.dictName") },
  { prop: "dict_type", label: t("system.dict.dictType") },
  { prop: "status", label: t("system.dict.status") },
  { prop: "description", label: t("system.dict.description") },
  { prop: "created_time", label: t("system.dict.createdTime") },
  { prop: "updated_time", label: t("system.dict.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:dict_type",
  cols: exportColumns as any,
  exportsAction: async (params: any) => {
    const query: Record<string, unknown> = { ...params };
    if (typeof query.status === "string") query.status = query.status === "true";
    return fetchAllPages({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await DictAPI.listDictType(q as unknown as DictPageQuery);
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
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await DictAPI.detailDictType(id);
    if (type === "detail") {
      dialogVisible.title = t("system.dict.dialogDetailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.dict.dialogUpdateTitle");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.dict.dialogCreateTitle");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: any) => {
    if (valid) {
      const id = formData.id;
      try {
        if (id) {
          await DictAPI.updateDictType(id, { id, ...formData });
        } else {
          await DictAPI.createDictType(formData);
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
  const rows = contentRef.value?.getSelectionData() as DictTable[] | undefined;
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
        await DictAPI.batchDictType({ ids, status });
        ElMessage.success(t("system.dict.actionSuccess"));
        refreshList();
        dictStore.clearDictData();
        const dictTypes = Object.keys(dictStore.dictData);
        if (dictTypes.length > 0) {
          await dictStore.getDict(dictTypes);
        }
      } catch (error: any) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}

const drawerVisible = ref(false);
const currentDictType = ref("");
const currentDictLabel = ref("");
const currentDictTypeId = ref(1);

function handleDictDataDrawer(dictType: DictTable) {
  currentDictType.value = dictType.dict_type || "";
  currentDictLabel.value = dictType.dict_name || "";
  currentDictTypeId.value = dictType.id || 0;
  drawerVisible.value = true;
}
</script>
