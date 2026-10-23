<!-- 公告通知配置 -->
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
          :perm-create="['module_system:notice:create']"
          :perm-delete="['module_system:notice:delete']"
          :perm-patch="['module_system:notice:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar">
            <template #prepend>
              <el-tooltip :content="t('system.notice.export')">
                <el-button
                  v-hasPerm="['module_system:notice:export']"
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
              <el-empty :image-size="70" :description="t('system.notice.empty')" />
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
              :label="t('system.notice.index')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'notice_title')?.show"
              :label="t('system.notice.noticeTitle')"
              prop="notice_title"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              :label="t('system.notice.status')"
              prop="status"
              min-width="80"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0"
                      ? t("system.notice.enable")
                      : t("system.notice.disable")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'notice_type')?.show"
              :label="t('system.notice.type')"
              prop="notice_type"
              min-width="80"
            >
              <template #default="scope">
                <el-tag :type="scope.row.notice_type === '1' ? 'primary' : 'warning'">
                  {{
                    (scope.row.notice_type
                      ? (dictStore.getDictLabel("sys_notice_type", scope.row.notice_type) as any)
                      : undefined
                    )?.dict_label || scope.row.notice_type
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'notice_content')?.show"
              :label="t('system.notice.content')"
              prop="notice_content"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              :label="t('system.notice.description')"
              prop="description"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              :label="t('system.notice.createdTime')"
              prop="created_time"
              min-width="180"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              :label="t('system.notice.updatedTime')"
              prop="updated_time"
              min-width="180"
              sortable
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_id')?.show"
              key="created_id"
              :label="t('system.notice.creator')"
              min-width="100"
            >
              <template #default="scope">
                {{ scope.row.created_by?.name }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_id')?.show"
              key="updated_id"
              :label="t('system.notice.updater')"
              min-width="100"
            >
              <template #default="scope">
                {{ scope.row.updated_by?.name }}
              </template>
            </el-table-column>

            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('system.notice.operation')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_system:notice:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("system.notice.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:notice:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("system.notice.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_system:notice:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("system.notice.delete") }}
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
        <el-descriptions :column="4" border label-width="120px">
          <el-descriptions-item :label="t('system.notice.title')" :span="2">
            {{ detailFormData.notice_title }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.type')" :span="2">
            <el-tag :type="detailFormData.notice_type === '1' ? 'primary' : 'warning'">
              {{
                (detailFormData.notice_type
                  ? (dictStore.getDictLabel("sys_notice_type", detailFormData.notice_type) as any)
                  : undefined
                )?.dict_label || detailFormData.notice_type
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.status')" :span="2">
            <el-tag :type="detailFormData.status === '0' ? 'success' : 'danger'">
              {{
                detailFormData.status === "0"
                  ? t("system.notice.enable")
                  : t("system.notice.disable")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.description')" :span="2">
            {{ detailFormData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.content')" :span="4">
            <WangEditor v-model="detailFormData.notice_content" :readonly="true" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.creator')" :span="2">
            {{ detailFormData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.updater')" :span="2">
            {{ detailFormData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.notice.updatedTime')" :span="2">
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
          :inline="true"
        >
          <el-form-item :label="t('system.notice.title')" prop="notice_title">
            <el-input
              v-model="formData.notice_title"
              :placeholder="t('system.notice.inputTitlePlaceholder')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('system.notice.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="1"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('system.notice.inputDescPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('system.notice.type')" prop="notice_type" class="w-50">
            <el-select
              v-model="formData.notice_type"
              :placeholder="t('system.notice.selectTypePlaceholder')"
              clearable
            >
              <el-option
                v-for="item in dictStore.getDictArray('sys_notice_type')"
                :key="item.dict_value"
                :value="item.dict_value"
                :label="item.dict_label"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('system.notice.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("system.notice.enable") }}</el-radio>
              <el-radio value="1">{{ t("system.notice.disable") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('system.notice.content')" prop="notice_content">
            <WangEditor v-model="formData.notice_content" />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("system.notice.cancel") }}</el-button>
          <el-button
            v-if="dialogVisible.type !== 'detail'"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("system.notice.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("system.notice.confirm") }}
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
import { ref, reactive, computed, markRaw, nextTick, onMounted, unref } from "vue";
import { useI18n } from "vue-i18n";
import { fetchAllPages } from "@/utils/fetchAllPages";
import { useDictStore, useNoticeStore } from "@/store/index";
import UserTableSelect from "@/views/module_system/user/components/UserTableSelect.vue";
import ExportModal from "@/components/CURD/ExportModal.vue";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import NoticeAPI, { NoticeTable, NoticeForm, NoticePageQuery } from "@/api/module_system/notice";

const { t } = useI18n();
const dictStore = useDictStore();
defineOptions({
  name: "Notice",
  inheritAttrs: false,
});

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const submitLoading = ref(false);

function triggerUserSearch() {
  nextTick(() => refreshList());
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_system:notice",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "notice_title",
      label: t("system.notice.title"),
      type: "input",
      attrs: {
        placeholder: t("system.notice.inputTitlePlaceholder"),
        clearable: true,
      },
    },
    {
      prop: "notice_type",
      label: t("system.notice.type"),
      type: "select",
      options: [] as { label: string; value: string }[],
      attrs: {
        placeholder: t("system.notice.selectTypePlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "status",
      label: t("system.notice.status"),
      type: "select",
      options: [
        { label: t("system.notice.enable"), value: "0" },
        { label: t("system.notice.disable"), value: "1" },
      ],
      attrs: {
        placeholder: t("system.notice.selectStatusPlaceholder"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "created_time",
      label: t("system.notice.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("system.notice.rangeSeparator"),
        startPlaceholder: t("system.notice.startDate"),
        endPlaceholder: t("system.notice.endDate"),
        style: { width: "340px" },
      },
    },
    {
      prop: "created_id",
      label: t("system.notice.creator"),
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
  { prop: "selection", label: t("system.notice.selection"), show: true },
  { prop: "index", label: t("system.notice.index"), show: true },
  { prop: "notice_title", label: t("system.notice.title"), show: true },
  { prop: "notice_type", label: t("system.notice.type"), show: true },
  { prop: "notice_content", label: t("system.notice.content"), show: true },
  { prop: "status", label: t("system.notice.status"), show: true },
  { prop: "description", label: t("system.notice.description"), show: true },
  { prop: "created_time", label: t("system.notice.createdTime"), show: true },
  { prop: "updated_id", label: t("system.notice.updater"), show: true },
  { prop: "updated_time", label: t("system.notice.updatedTime"), show: true },
  { prop: "created_id", label: t("system.notice.creator"), show: true },
  { prop: "operation", label: t("system.notice.operation"), show: true },
]);

const noticeStore = useNoticeStore();

const contentConfig = reactive<IContentConfig<NoticePageQuery>>({
  permPrefix: "module_system:notice",
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
    const res = await NoticeAPI.listNotice(params as NoticePageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await NoticeAPI.deleteNotice(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
    await noticeStore.getNotice();
  },
  deleteConfirm: {
    title: t("system.notice.warning"),
    message: t("system.notice.deleteConfirmMessage"),
    type: "warning",
  },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const exportsDialogVisible = ref(false);

const exportQueryParams = computed(() => searchRef.value?.getQueryParams() ?? {});

const exportPageData = computed(() => (unref(contentRef.value?.pageData) ?? []) as NoticeTable[]);

const exportSelectionData = computed(
  () => (contentRef.value?.getSelectionData() ?? []) as NoticeTable[]
);

const exportColumns = [
  { prop: "notice_title", label: t("system.notice.title") },
  { prop: "status", label: t("system.notice.status") },
  { prop: "notice_type", label: t("system.notice.type") },
  { prop: "notice_content", label: t("system.notice.content") },
  { prop: "description", label: t("system.notice.description") },
  { prop: "created_time", label: t("system.notice.createdTime") },
  { prop: "updated_time", label: t("system.notice.updatedTime") },
];

const curdContentConfig = {
  permPrefix: "module_system:notice",
  cols: exportColumns as any,
  exportsAction: async (params: any) => {
    const query: Record<string, unknown> = { ...params };
    if (typeof query.status === "string") query.status = query.status === "true";
    return fetchAllPages({
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await NoticeAPI.listNotice(q as unknown as NoticePageQuery);
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

const detailFormData = ref<NoticeTable>({});

const formData = reactive<NoticeForm>({
  id: undefined,
  notice_title: "",
  notice_type: "",
  notice_content: "",
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  notice_title: [{ required: true, message: t("system.notice.ruleTitle"), trigger: "blur" }],
  notice_type: [{ required: true, message: t("system.notice.ruleType"), trigger: "blur" }],
  notice_content: [{ required: true, message: t("system.notice.ruleContent"), trigger: "blur" }],
  status: [{ required: true, message: t("system.notice.ruleStatus"), trigger: "blur" }],
});

const initialFormData: NoticeForm = {
  id: undefined,
  notice_title: "",
  notice_type: "",
  notice_content: "",
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
    const response = await NoticeAPI.detailNotice(id);
    if (type === "detail") {
      dialogVisible.title = t("system.notice.detailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("system.notice.updateTitle");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("system.notice.createTitle");
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
          await NoticeAPI.updateNotice(id, { id, ...formData });
        } else {
          await NoticeAPI.createNotice(formData);
        }
        ElMessage.success(t("system.notice.operationSuccess"));
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
        await noticeStore.getNotice();
      } catch (error: any) {
        console.error(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() as NoticeTable[] | undefined;
  const ids = (rows ?? []).map((r) => r.id).filter((id): id is number => id != null);
  if (!ids.length) {
    ElMessage.warning(t("system.notice.selectDataFirst"));
    return;
  }
  ElMessageBox.confirm(
    t("system.notice.toggleConfirm", {
      action: status === "0" ? t("system.notice.enable") : t("system.notice.disable"),
    }),
    t("system.notice.warning"),
    {
      confirmButtonText: t("system.notice.confirm"),
      cancelButtonText: t("system.notice.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await NoticeAPI.batchNotice({ ids, status });
        ElMessage.success(t("system.notice.operationSuccess"));
        refreshList();
      } catch (error: any) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}

onMounted(async () => {
  await dictStore.getDict(["sys_notice_type"]);
  const typeItem = searchConfig.formItems?.find((i) => i.prop === "notice_type");
  if (typeItem && typeItem.type === "select") {
    typeItem.options = dictStore.getDictArray("sys_notice_type").map((item) => ({
      label: item.dict_label,
      value: item.dict_value,
    }));
  }
});
</script>

<style lang="scss" scoped></style>
