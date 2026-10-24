<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig" @add-click="openDialog()">
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
              <el-empty :image-size="80" :description="t('task.noData')" />
            </template>
            <el-table-column type="selection" align="center" min-width="55" />
            <el-table-column type="index" fixed :label="t('task.serial')" min-width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column :label="t('task.id')" prop="id" min-width="70" />
            <el-table-column
              :label="t('task.name')"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('task.code')"
              prop="code"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column :label="t('task.category')" prop="category" min-width="100">
              <template #default="scope">
                {{ categoryLabel(scope.row.category) }}
              </template>
            </el-table-column>
            <el-table-column :label="t('task.sortOrder')" prop="sort_order" min-width="80" />
            <el-table-column :label="t('task.isActive')" prop="is_active" min-width="80">
              <template #default="scope">
                <el-tag :type="scope.row.is_active ? 'success' : 'info'">
                  {{ scope.row.is_active ? t("task.yes") : t("task.no") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('task.createdTime')" prop="created_time" min-width="170" />

            <OperationColumn :list-data-length="data.length">
              <template #default="scope">
                <el-space class="flex">
                  <el-button
                    v-hasPerm="['module_task:workflow:node-type:update']"
                    type="primary"
                    size="small"
                    link
                    icon="edit"
                    @click="openDialog(scope.row.id)"
                  >
                    {{ t("task.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_task:workflow:node-type:delete']"
                    type="danger"
                    size="small"
                    link
                    icon="delete"
                    @click="handleRowDelete(scope.row.id)"
                  >
                    {{ t("task.delete") }}
                  </el-button>
                </el-space>
              </template>
            </OperationColumn>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="720px"
      destroy-on-close
      @close="handleCloseDialog"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item :label="t('task.name')" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item :label="t('task.code')" prop="code">
          <el-input v-model="form.code" maxlength="64" show-word-limit :disabled="!!editingId" />
        </el-form-item>
        <el-form-item :label="t('task.category')" prop="category">
          <el-select v-model="form.category" style="width: 100%">
            <el-option :label="t('task.trigger')" value="trigger" />
            <el-option :label="t('task.action')" value="action" />
            <el-option :label="t('task.condition')" value="condition" />
            <el-option :label="t('task.control')" value="control" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('task.codeBlock')" prop="func">
          <el-input
            v-model="form.func"
            type="textarea"
            :rows="12"
            :placeholder="t('task.funcPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('task.positionalArgs')" prop="args">
          <el-input v-model="form.args" :placeholder="t('task.argsPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('task.kwArgs')" prop="kwargs">
          <el-input
            v-model="form.kwargs"
            type="textarea"
            :rows="3"
            :placeholder="t('task.kwargsPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('task.sortOrder')" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item :label="t('task.isActive')" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t("task.cancel") }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">
          {{ t("task.save") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script lang="ts" setup>
defineOptions({
  name: "WorkflowNodeType",
  inheritAttrs: false,
});

const { t } = useI18n();

import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import OperationColumn from "@/components/OperationColumn/index.vue";
import WorkflowNodeTypeAPI, {
  type WorkflowNodeTypeForm,
  type WorkflowNodeTypePageQuery,
  type WorkflowNodeTypeTable,
} from "@/api/module_task/workflow/node-type";

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const dialogVisible = ref(false);
const dialogTitle = ref(t("task.createNodeType"));
const editingId = ref<number | null>(null);
const submitting = ref(false);
const formRef = ref<FormInstance>();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_task:workflow:node-type",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("task.name"),
      type: "input",
      attrs: { placeholder: t("task.name"), clearable: true },
    },
    {
      prop: "code",
      label: t("task.code"),
      type: "input",
      attrs: { placeholder: t("task.code"), clearable: true },
    },
    {
      prop: "category",
      label: t("task.category"),
      type: "select",
      options: [
        { label: t("task.trigger"), value: "trigger" },
        { label: t("task.action"), value: "action" },
        { label: t("task.condition"), value: "condition" },
        { label: t("task.control"), value: "control" },
      ],
      attrs: { placeholder: t("task.all"), clearable: true, style: { width: "170px" } },
    },
  ],
});

function normalizeNodeTypeQuery(params: Record<string, unknown>): WorkflowNodeTypePageQuery {
  const p = { ...params } as Record<string, unknown>;
  if (p.category === "" || p.category === null) p.category = undefined;
  return p as unknown as WorkflowNodeTypePageQuery;
}

const contentConfig = reactive<IContentConfig<WorkflowNodeTypePageQuery>>({
  permPrefix: "module_task:workflow:node-type",
  cols: [],
  hideColumnFilter: true,
  toolbar: [
    { name: "add", text: t("task.add"), attrs: { icon: "plus", type: "success" }, perm: "create" },
    "delete",
  ],
  defaultToolbar: ["refresh"],
  initialFetch: false,
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await WorkflowNodeTypeAPI.getWorkflowNodeTypeList(
      normalizeNodeTypeQuery(params as unknown as Record<string, unknown>)
    );
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: (ids) =>
    WorkflowNodeTypeAPI.deleteWorkflowNodeType(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n) && n > 0)
    ),
  deleteConfirm: {
    title: t("task.warn"),
    message: t("task.deleteNodeTypeConfirm"),
    type: "warning",
  },
});

function handleRowDelete(id?: number) {
  if (id == null) return;
  contentRef.value?.handleDelete(id);
}

function categoryLabel(c?: string) {
  const m: Record<string, string> = {
    trigger: t("task.trigger"),
    action: t("task.action"),
    condition: t("task.condition"),
    control: t("task.control"),
  };
  return c ? m[c] || c : "-";
}

const defaultForm = (): WorkflowNodeTypeForm => ({
  name: "",
  code: "",
  category: "action",
  func: "",
  args: "",
  kwargs: "{}",
  sort_order: 0,
  is_active: true,
});

const form = reactive<WorkflowNodeTypeForm>(defaultForm());

const rules: FormRules = {
  name: [{ required: true, message: t("task.inputName"), trigger: "blur" }],
  code: [{ required: true, message: t("task.inputCode"), trigger: "blur" }],
  category: [{ required: true, message: t("task.selectCategory"), trigger: "change" }],
  func: [{ required: true, message: t("task.inputFunc"), trigger: "blur" }],
};

function resetForm() {
  Object.assign(form, defaultForm());
  editingId.value = null;
  formRef.value?.resetFields();
}

function handleCloseDialog() {
  resetForm();
}

async function openDialog(id?: number) {
  resetForm();
  dialogTitle.value = id ? t("task.editNodeType") : t("task.createNodeType");
  editingId.value = id ?? null;
  if (id) {
    try {
      const res = await WorkflowNodeTypeAPI.getWorkflowNodeTypeDetail(id);
      const d = res.data?.data as WorkflowNodeTypeTable | undefined;
      if (d) {
        form.name = d.name || "";
        form.code = d.code || "";
        form.category = (d.category as WorkflowNodeTypeForm["category"]) || "action";
        form.func = d.func || "";
        form.args = d.args || "";
        form.kwargs = d.kwargs || "{}";
        form.sort_order = d.sort_order ?? 0;
        form.is_active = d.is_active ?? true;
      }
    } catch {
      ElMessage.error(t("task.loadDetailFailed"));
      return;
    }
  }
  dialogVisible.value = true;
}

async function submitForm() {
  if (!formRef.value) return;
  await formRef.value.validate();
  if (form.kwargs?.trim()) {
    try {
      JSON.parse(form.kwargs);
    } catch {
      ElMessage.error(t("task.kwargsInvalidJson"));
      return;
    }
  }
  submitting.value = true;
  try {
    if (editingId.value) {
      await WorkflowNodeTypeAPI.updateWorkflowNodeType(editingId.value, form);
      ElMessage.success(t("task.updateSuccess"));
    } else {
      await WorkflowNodeTypeAPI.createWorkflowNodeType(form);
      ElMessage.success(t("task.createSuccess"));
    }
    dialogVisible.value = false;
    refreshList();
  } catch {
    ElMessage.error(editingId.value ? t("task.updateFailed") : t("task.createFailed"));
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  refreshList();
});
</script>

<style scoped lang="scss"></style>
