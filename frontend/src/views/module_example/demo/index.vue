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
          :perm-create="['module_example:demo:create']"
          :perm-delete="['module_example:demo:delete']"
          :perm-patch="['module_example:demo:patch']"
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
              <el-empty :image-size="80" :description="t('example.demo.noData')" />
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
              :label="t('example.demo.serial')"
              min-width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              :label="t('example.demo.name')"
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
              :label="t('example.demo.status')"
              prop="status"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-tag :type="scope.row.status ? 'success' : 'info'">
                  {{ scope.row.status ? t("example.demo.enabled") : t("example.demo.disabled") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'a')?.show"
              :label="t('example.demo.integer')"
              prop="a"
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'b')?.show"
              :label="t('example.demo.bigInteger')"
              prop="b"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'c')?.show"
              :label="t('example.demo.float')"
              prop="c"
              min-width="100"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'd')?.show"
              :label="t('example.demo.boolean')"
              prop="d"
              min-width="100"
              show-overflow-tooltip
            >
              <template #default="scope">
                <el-tag :type="scope.row.d ? 'success' : 'danger'">
                  {{ scope.row.d ? t("example.demo.yes") : t("example.demo.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'e')?.show"
              :label="t('example.demo.date')"
              prop="e"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'f')?.show"
              :label="t('example.demo.time')"
              prop="f"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'g')?.show"
              :label="t('example.demo.datetime')"
              prop="g"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'h')?.show"
              :label="t('example.demo.longText')"
              prop="h"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'description')?.show"
              :label="t('example.demo.description')"
              prop="description"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              :label="t('example.demo.createdTime')"
              prop="created_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'updated_time')?.show"
              :label="t('example.demo.updatedTime')"
              prop="updated_time"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_id')?.show"
              :label="t('example.demo.createdBy')"
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
              :label="t('example.demo.updatedBy')"
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
              :label="t('example.demo.action')"
              align="center"
              min-width="200"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_example:demo:detail']"
                  type="info"
                  size="small"
                  link
                  icon="View"
                  @click="handleOpenDialog('detail', scope.row.id)"
                >
                  {{ t("example.demo.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_example:demo:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("example.demo.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_example:demo:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("example.demo.delete") }}
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
      width="920px"
      @close="handleCloseDialog"
    >
      <template v-if="dialogVisible.type === 'detail'">
        <el-descriptions :column="4" border>
          <el-descriptions-item :label="t('example.demo.name')" :span="2">
            {{ detailFormData.name }}
          </el-descriptions-item>
          <el-descriptions-item label="UUID" :span="2">
            {{ detailFormData.uuid }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.status')" :span="2">
            <el-tag :type="detailFormData.status == '0' ? 'success' : 'danger'">
              {{
                detailFormData.status == "0"
                  ? t("example.demo.enabled")
                  : t("example.demo.disabled")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.integer')" :span="2">
            {{ detailFormData.a }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.bigInteger')" :span="2">
            {{ detailFormData.b }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.float')" :span="2">
            {{ detailFormData.c }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.boolean')" :span="2">
            <el-tag :type="detailFormData.d ? 'success' : 'danger'">
              {{ detailFormData.d ? t("example.demo.yes") : t("example.demo.no") }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.date')" :span="2">
            {{ detailFormData.e }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.time')" :span="2">
            {{ detailFormData.f }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.datetime')" :span="2">
            {{ detailFormData.g }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.longText')" :span="2">
            {{ detailFormData.h }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.metadata')" :span="2">
            <JsonPretty :value="detailFormData.i" height="140px" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.description')" :span="2">
            {{ detailFormData.description }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.createdBy')" :span="2">
            {{ detailFormData.created_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.updatedBy')" :span="2">
            {{ detailFormData.updated_by?.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.createdTime')" :span="2">
            {{ detailFormData.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('example.demo.updatedTime')" :span="2">
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
          inline
        >
          <el-form-item :label="t('example.demo.name')" prop="name">
            <el-input
              v-model="formData.name"
              :placeholder="t('example.demo.inputName')"
              :maxlength="50"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.status')" prop="status">
            <el-radio-group v-model="formData.status">
              <el-radio value="0">{{ t("example.demo.enabled") }}</el-radio>
              <el-radio value="1">{{ t("example.demo.disabled") }}</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="t('example.demo.integer')" prop="a">
            <el-input-number v-model="formData.a" :placeholder="t('example.demo.inputInteger')" />
          </el-form-item>
          <el-form-item :label="t('example.demo.bigInteger')" prop="b">
            <el-input-number
              v-model="formData.b"
              :placeholder="t('example.demo.inputBigInteger')"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.float')" prop="c">
            <el-input-number
              v-model="formData.c"
              :placeholder="t('example.demo.inputFloat')"
              :step="0.01"
              :precision="2"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.boolean')" prop="d">
            <el-switch v-model="formData.d" />
          </el-form-item>
          <el-form-item :label="t('example.demo.date')" prop="e">
            <el-date-picker
              v-model="formData.e"
              type="date"
              :placeholder="t('example.demo.selectDate')"
              style="width: 100%"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.time')" prop="f">
            <el-time-picker
              v-model="formData.f"
              :placeholder="t('example.demo.selectTime')"
              style="width: 100%"
              value-format="HH:mm:ss"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.datetime')" prop="g">
            <el-date-picker
              v-model="formData.g"
              type="datetime"
              :placeholder="t('example.demo.selectDatetime')"
              style="width: 100%"
              value-format="YYYY-MM-DD HH:mm:ss"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.longText')" prop="h">
            <el-input
              v-model="formData.h"
              :rows="4"
              type="textarea"
              :placeholder="t('example.demo.inputLongText')"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.description')" prop="description">
            <el-input
              v-model="formData.description"
              :rows="4"
              :maxlength="100"
              show-word-limit
              type="textarea"
              :placeholder="t('example.demo.inputDescription')"
            />
          </el-form-item>
          <el-form-item :label="t('example.demo.metadata')" prop="i">
            <div class="flex flex-col gap-2">
              <div
                v-for="(item, index) in metadataList"
                :key="index"
                class="flex items-center gap-2"
              >
                <el-input v-model="item.key" :placeholder="t('example.demo.key')" />
                <el-input v-model="item.value" :placeholder="t('example.demo.value')" />
                <el-button
                  type="primary"
                  icon="Plus"
                  circle
                  @click="metadataList.push({ key: '', value: '' })"
                />
                <el-button
                  type="danger"
                  icon="Delete"
                  circle
                  @click="metadataList.splice(index, 1)"
                />
              </div>
              <el-button
                v-if="metadataList.length === 0"
                type="primary"
                icon="Plus"
                @click="metadataList.push({ key: '', value: '' })"
              >
                {{ t("example.demo.addMetadata") }}
              </el-button>
            </div>
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("example.demo.cancel") }}</el-button>
          <el-button v-if="dialogVisible.type !== 'detail'" type="primary" @click="handleSubmit">
            {{ t("example.demo.confirm") }}
          </el-button>
          <el-button v-else type="primary" @click="handleCloseDialog">
            {{ t("example.demo.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({
  name: "Demo",
  inheritAttrs: false,
});

import { ref, reactive, onMounted, markRaw, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { fetchAllPages } from "@/utils/fetchAllPages";
import { ElMessageBox } from "element-plus";
import { ResultEnum } from "@/enums/api/result.enum";
import DemoAPI, { DemoTable, DemoForm, DemoPageQuery } from "@/api/module_example/demo";
import CrudToolbarLeft from "@/components/CURD/CrudToolbarLeft.vue";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import UserTableSelect from "@/views/module_system/user/components/UserTableSelect.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import JsonPretty from "@/components/JsonPretty/index.vue";

const { t } = useI18n();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

function triggerUserSearch() {
  nextTick(() => refreshList());
}

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_example:demo",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("example.demo.name"),
      type: "input",
      attrs: { placeholder: t("example.demo.inputName"), clearable: true },
    },
    {
      prop: "status",
      label: t("example.demo.status"),
      type: "select",
      options: [
        { label: t("example.demo.enabled"), value: "0" },
        { label: t("example.demo.disabled"), value: "1" },
      ],
      attrs: {
        placeholder: t("example.demo.selectStatus"),
        clearable: true,
        style: { width: "170px" },
      },
    },
    {
      prop: "created_id",
      label: t("example.demo.createdBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
    {
      prop: "updated_id",
      label: t("example.demo.updatedBy"),
      type: "user-table-select",
      initialValue: null,
      events: {
        "confirm-click": triggerUserSearch,
        "clear-click": triggerUserSearch,
      },
    },
    {
      prop: "created_time",
      label: t("example.demo.createdTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("example.demo.to"),
        startPlaceholder: t("example.demo.start"),
        endPlaceholder: t("example.demo.end"),
      },
    },
    {
      prop: "updated_time",
      label: t("example.demo.updatedTime"),
      type: "date-picker",
      initialValue: [],
      attrs: {
        type: "datetimerange",
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        rangeSeparator: t("example.demo.to"),
        startPlaceholder: t("example.demo.start"),
        endPlaceholder: t("example.demo.end"),
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
  { prop: "selection", label: t("example.demo.selection"), show: true },
  { prop: "index", label: t("example.demo.serial"), show: true },
  { prop: "name", label: t("example.demo.name"), show: true },
  { prop: "uuid", label: "UUID", show: true },
  { prop: "status", label: t("example.demo.status"), show: true },
  { prop: "a", label: t("example.demo.integer"), show: true },
  { prop: "b", label: t("example.demo.bigInteger"), show: true },
  { prop: "c", label: t("example.demo.float"), show: true },
  { prop: "d", label: t("example.demo.boolean"), show: true },
  { prop: "e", label: t("example.demo.date"), show: true },
  { prop: "f", label: t("example.demo.time"), show: true },
  { prop: "g", label: t("example.demo.datetime"), show: true },
  { prop: "h", label: t("example.demo.longText"), show: true },
  { prop: "i", label: t("example.demo.metadata"), show: true },
  { prop: "description", label: t("example.demo.description"), show: true },
  { prop: "created_time", label: t("example.demo.createdTime"), show: true },
  { prop: "updated_time", label: t("example.demo.updatedTime"), show: true },
  { prop: "created_id", label: t("example.demo.createdBy"), show: true },
  { prop: "updated_id", label: t("example.demo.updatedBy"), show: true },
  { prop: "operation", label: t("example.demo.action"), show: true },
]);

function normalizeDemoQuery(params: Record<string, unknown>) {
  const p = { ...params } as Record<string, unknown>;
  if (Array.isArray(p.created_time) && p.created_time.length === 0) p.created_time = undefined;
  if (Array.isArray(p.updated_time) && p.updated_time.length === 0) p.updated_time = undefined;
  return p as unknown as DemoPageQuery;
}

const contentConfig = reactive<IContentConfig<DemoPageQuery>>({
  permPrefix: "module_example:demo",
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
    const res = await DemoAPI.getDemoList(
      normalizeDemoQuery(params as unknown as Record<string, unknown>)
    );
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: (ids) =>
    DemoAPI.deleteDemo(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n) && n > 0)
    ),
  importTemplate: () => DemoAPI.downloadTemplateDemo(),
  importAction: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return DemoAPI.importDemo(fd).then((res) => {
      if (res.data.code !== ResultEnum.SUCCESS) {
        return Promise.reject(new Error(res.data.msg));
      }
    });
  },
  exportsAction: async (params: DemoPageQuery) => {
    const query: Record<string, unknown> = { ...params };
    if (typeof query.status === "string") {
      query.status = query.status === "true";
    }
    return fetchAllPages<DemoTable>({
      pageSize: 9999,
      initialQuery: query,
      fetchPage: async (q) => {
        const res = await DemoAPI.getDemoList(
          normalizeDemoQuery(q as unknown as Record<string, unknown>)
        );
        return {
          total: res.data?.data?.total ?? 0,
          list: res.data?.data?.items ?? [],
        };
      },
    });
  },
});

const detailFormData = ref<DemoTable>({});

const formData = reactive<DemoForm>({
  id: undefined,
  name: "",
  status: "0",
  description: undefined,
  a: undefined,
  b: undefined,
  c: undefined,
  d: true,
  e: undefined,
  f: undefined,
  g: undefined,
  h: undefined,
  i: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  name: [{ required: true, message: t("example.demo.requiredName"), trigger: "blur" }],
  status: [{ required: true, message: t("example.demo.requiredStatus"), trigger: "blur" }],
});

const dataFormRef = ref();

const metadataList = ref<{ key: string; value: string }[]>([]);

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const initialFormData: DemoForm = {
  id: undefined,
  name: "",
  status: "0",
  description: undefined,
  a: undefined,
  b: undefined,
  c: undefined,
  d: true,
  e: undefined,
  f: undefined,
  g: undefined,
  h: undefined,
  i: undefined,
};

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  metadataList.value = [];
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  resetForm();
}

async function handleOpenDialog(type: "create" | "update" | "detail", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await DemoAPI.getDemoDetail(id);
    if (type === "detail") {
      dialogVisible.title = t("example.demo.detailTitle");
      Object.assign(detailFormData.value, response.data.data);
    } else if (type === "update") {
      dialogVisible.title = t("example.demo.updateTitle");
      Object.assign(formData, response.data.data);
      if (formData.i && typeof formData.i === "object") {
        metadataList.value = Object.entries(formData.i).map(([key, value]) => ({
          key,
          value: String(value),
        }));
      } else {
        metadataList.value = [];
      }
    }
  } else {
    dialogVisible.title = t("example.demo.createTitle");
    formData.id = undefined;
    metadataList.value = [];
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      const submitData = { ...formData };
      if (metadataList.value.length > 0) {
        const metadataObj: Record<string, string> = {};
        metadataList.value.forEach((item) => {
          if (item.key.trim()) {
            metadataObj[item.key.trim()] = item.value;
          }
        });
        submitData.i = Object.keys(metadataObj).length > 0 ? metadataObj : undefined;
      } else {
        submitData.i = undefined;
      }
      const id = formData.id;
      try {
        if (id) {
          await DemoAPI.updateDemo(id, { id, ...submitData });
        } else {
          await DemoAPI.createDemo(submitData);
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
    t("example.demo.confirmBatch", {
      action: status === "0" ? t("example.demo.enabled") : t("example.demo.disabled"),
    }),
    t("example.demo.warning"),
    {
      confirmButtonText: t("example.demo.confirm"),
      cancelButtonText: t("example.demo.cancel"),
      type: "warning",
    }
  )
    .then(async () => {
      try {
        await DemoAPI.batchDemo({ ids, status });
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
