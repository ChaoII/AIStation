<!-- 演示示例：PageSearch + PageContent CRUD 封装 -->
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
          :perm-create="['module_example:demo01:create']"
          :perm-delete="['module_example:demo01:delete']"
          :perm-patch="['module_example:demo01:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
          @more="handleMoreClick"
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
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('example.demo01.noData')" />
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
              :label="t('example.demo01.serial')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              :label="t('example.demo01.name')"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'uuid')?.show"
              label="UUID"
              prop="uuid"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              :label="t('example.demo01.status')"
              prop="status"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === '0' ? 'success' : 'danger'">
                  {{
                    scope.row.status === "0"
                      ? t("example.demo01.enabled")
                      : t("example.demo01.disabled")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              :label="t('example.demo01.description')"
              prop="description"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              :label="t('example.demo01.createdTime')"
              prop="created_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              :label="t('example.demo01.updatedTime')"
              prop="updated_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_id')?.show"
              :label="t('example.demo01.createdBy')"
              prop="created_id"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-tag>{{ scope.row.created_by?.name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_id')?.show"
              :label="t('example.demo01.updatedBy')"
              prop="updated_id"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-tag>{{ scope.row.updated_by?.name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              :label="t('example.demo01.action')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_example:demo01:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("example.demo01.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_example:demo01:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("example.demo01.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_example:demo01:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("example.demo01.delete") }}
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
      width="560px"
      @close="handleCloseDialog"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('example.demo01.name')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item label="UUID" :span="2">
            {{ detailFormData.uuid }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.status')" :span="2">
            <el-tag :type="detailFormData.status == '0' ? 'success' : 'danger'">
              {{
                detailFormData.status == "0"
                  ? t("example.demo01.enabled")
                  : t("example.demo01.disabled")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.description')" :span="2">
            {{ detailFormData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.createdBy')" :span="2">
            {{ detailFormData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.updatedBy')" :span="2">
            {{ detailFormData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo01.updatedTime')" :span="2">
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
          <el-form-item :label="t('example.demo01.name')" prop="name">
            <el-input
              v-model="formData.name"
              :placeholder="t('example.demo01.inputNameFormat')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo01.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("example.demo01.enabled") }}</el-radio>
              <el-radio value="1">{{ t("example.demo01.disabled") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('example.demo01.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="255"
              show-word-limit
              type="textarea"
              :placeholder="t('example.demo01.inputDescription')"
            />
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("example.demo01.cancel") }}</el-button>
          <el-button v-if="dialogVisible.type !== 'detail'" type="primary" @click="handleSubmit">
            {{ t("example.demo01.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("example.demo01.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Demo01",
  inheritAttrs: false,
});

import { ref, reactive, onMounted, markRaw, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { fetchAllPages } from "@/utils/fetchAllPages";
import { ElMessageBox } from "element-plus";
import { ResultEnum } from "@/enums/api/result.enum";
import Demo01API, { Demo01Table, Demo01Form, Demo01PageQuery } from "@/api/module_example/demo01";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import UserTableSelect from "@/views/module_system/user/components/UserTableSelect.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";

const { t } = useI18n();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

function triggerUserSearch() {
  nextTick(() => refreshList());
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_example:demo01",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("example.demo01.name"),
      type: "input",
      attrs: { placeholder: t("example.demo01.inputName"), clearable: true },
    },
    {
      prop: "description",
      label: t("example.demo01.description"),
      type: "input",
      attrs: { placeholder: t("example.demo01.descriptionQuery"), clearable: true },
    },
    {
      prop: "status",
      label: t("example.demo01.status"),
      type: "select",
      options: [
        { label: t("example.demo01.enabled"), value: "0" },
        { label: t("example.demo01.disabled"), value: "1" },
      ],
      attrs: {
        placeholder: t("example.demo01.selectStatus"),
        clearable: true,
        style: { width: "170px" },
      },
    },
    {
      prop: "created_id",
      label: t("example.demo01.createdBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
    {
      prop: "updated_id",
      label: t("example.demo01.updatedBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
    {
      prop: "created_time",
      label: t("example.demo01.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("example.demo01.to"),
        startPlaceholder: t("example.demo01.start"),
        endPlaceholder: t("example.demo01.end"),
      },
    },
    {
      prop: "updated_time",
      label: t("example.demo01.updatedTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("example.demo01.to"),
        startPlaceholder: t("example.demo01.start"),
        endPlaceholder: t("example.demo01.end"),
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
  { prop: "selection", label: t("example.demo01.selection"), show: true },
  { prop: "index", label: t("example.demo01.serial"), show: true },
  { prop: "name", label: t("example.demo01.name"), show: true },
  { prop: "uuid", label: "UUID", show: true },
  { prop: "status", label: t("example.demo01.status"), show: true },
  { prop: "description", label: t("example.demo01.description"), show: true },
  { prop: "created_time", label: t("example.demo01.createdTime"), show: true },
  { prop: "updated_time", label: t("example.demo01.updatedTime"), show: true },
  { prop: "created_id", label: t("example.demo01.createdBy"), show: true },
  { prop: "updated_id", label: t("example.demo01.updatedBy"), show: true },
  { prop: "operation", label: t("example.demo01.action"), show: true },
]);

function normalizeDemo01Query(params: Record<string, unknown>) {
  const p = { ...params } as Record<string, unknown>;
  if (Array.isArray(p.created_time) && p.created_time.length === 0) p.created_time = undefined;
  if (Array.isArray(p.updated_time) && p.updated_time.length === 0) p.updated_time = undefined;
  if (p.description === "" || p.description === null) p.description = undefined;
  if (p.name === "" || p.name === null) p.name = undefined;
  return p as unknown as Demo01PageQuery;
}

const contentConfig = reactive<IContentConfig<Demo01PageQuery>>({
  permPrefix: "module_example:demo01",
  hideColumnFilter: false,
  initialFetch: false,
  cols: contentCols as IContentConfig["cols"],
  toolbar: [],
  defaultToolbar: ["import", "export", "refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await Demo01API.getDemo01List(
      normalizeDemo01Query(params as unknown as Record<string, unknown>)
    );
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: (ids) =>
    Demo01API.deleteDemo01(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n) && n > 0)
    ),
  importTemplate: () => Demo01API.downloadDemo01Template(),
  importAction: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return Demo01API.importDemo01(fd).then((res) => {
      if (res.data.code !== ResultEnum.SUCCESS) {
        return Promise.reject(new Error(res.data.msg));
      }
    });
  },
  exportsAction: async (params: Demo01PageQuery) => {
    const query: Record<string, unknown> = { ...params };
    return fetchAllPages<Demo01Table>({
      pageSize: 9999,
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await Demo01API.getDemo01List(
          normalizeDemo01Query(q as unknown as Record<string, unknown>)
        );
        return {
          total: res.data?.data?.total ?? 0,
          list: res.data?.data?.items ?? [],
        };
      },
    });
  },
});

const detailFormData = ref<Demo01Table>({});

const formData = reactive<Demo01Form>({
  id: undefined,
  name: "",
  status: "0",
  description: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  name: [
    { required: true, message: t("example.demo01.requiredName"), trigger: "blur" },
    {
      min: 2,
      max: 50,
      message: t("example.demo01.nameLengthMessage"),
      trigger: "blur",
    },
    {
      pattern: /^[A-Za-z0-9_-]+$/,
      message: t("example.demo01.namePatternMessage"),
      trigger: "blur",
    },
  ],
  status: [{ required: true, message: t("example.demo01.requiredStatus"), trigger: "change" }],
  description: [
    {
      max: 255,
      message: t("example.demo01.descriptionMaxMessage"),
      trigger: "blur",
    },
  ],
});

const dataFormRef = ref();

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const initialFormData: Demo01Form = {
  id: undefined,
  name: "",
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
  resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await Demo01API.getDemo01Detail(id);
    if (type === "detail") {
      dialogVisible.title = t("example.demo01.detailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("example.demo01.updateTitle");
      Object.assign(formData, response.data.data);
    }
  } else {
    dialogVisible.title = t("example.demo01.createTitle");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      const submitData: Demo01Form = {
        name: formData.name?.trim(),
        status: formData.status,
        description: formData.description?.trim() || undefined,
      };
      const id = formData.id;
      try {
        if (id) {
          await Demo01API.updateDemo01(id, submitData);
        } else {
          await Demo01API.createDemo01(submitData);
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      }
    }
  });
}

async function handleMoreClick(status: string) {
  const rows = contentRef.value?.getSelectionData() ?? [];
  const ids = rows.map((r: { id?: number }) => r.id).filter(Boolean) as number[];
  if (!ids.length) return;
  ElMessageBox.confirm(
    t("example.demo01.confirmBatch", {
      action: status === "0" ? t("example.demo01.enabled") : t("example.demo01.disabled"),
    }),
    t("example.demo01.warning"),
    {
      confirmButtonText: t("example.demo01.confirm"),
      cancelButtonText: t("example.demo01.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await Demo01API.batchDemo01({ ids, status });
        refreshList();
      } catch (error: unknown) {
        console.error(error);
      }
    })
    .catch(() => {
      ElMessageBox.close();
    });
}

onMounted(() => {
  refreshList();
});
</script>

<style lang="scss" scoped></style>
