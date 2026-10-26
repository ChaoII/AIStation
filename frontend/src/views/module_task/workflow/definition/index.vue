<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig" @add-click="handleCreate">
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
            <el-table-column :label="t('task.id')" prop="id" min-width="80" />
            <el-table-column
              :label="t('task.name')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('task.code')"
              prop="code"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column :label="t('task.status')" prop="status" min-width="100">
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status) as any">
                  {{ getStatusText(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('task.description')"
              prop="description"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column :label="t('task.createdTime')" prop="created_time" min-width="180" />

            <OperationColumn :list-data-length="data.length">
              <template #default="scope">
                <el-space class="flex">
                  <el-button
                    v-if="scope.row.status === 'draft'"
                    v-hasPerm="['module_task:workflow:definition:update']"
                    type="success"
                    size="small"
                    link
                    icon="upload"
                    @click="handlePublish(scope.row)"
                  >
                    {{ t("task.publish") }}
                  </el-button>
                  <el-dropdown
                    v-if="scope.row.status === 'published'"
                    v-hasPerm="['module_task:workflow:definition:execute']"
                    @command="(e: string) => handleExecute(e, scope.row)"
                  >
                    <el-button type="warning" size="small" link icon="video-play">
                      {{ t("task.execute") }}
                      <el-icon><ArrowDown /></el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="execute">
                          {{ t("task.executeNow") }}
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                  <el-button
                    v-hasPerm="['module_task:workflow:definition:update']"
                    type="primary"
                    size="small"
                    link
                    icon="edit"
                    @click="handleEdit(scope.row)"
                  >
                    {{ t("task.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_task:workflow:definition:delete']"
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

    <WorkflowDesignDrawer
      v-model:visible="createVisible"
      :workflow="selectedWorkflow"
      @refresh="refreshList"
    />
  </div>
</template>

<script lang="ts" setup>
defineOptions({
  name: "WorkflowDefinition",
  inheritAttrs: false,
});

const { t } = useI18n();

import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import { ArrowDown } from "@element-plus/icons-vue";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import OperationColumn from "@/components/OperationColumn/index.vue";
import WorkflowDefinitionAPI, {
  type WorkflowTable,
  type WorkflowPageQuery,
} from "@/api/module_task/workflow/definition";
import WorkflowDesignDrawer from "../components/WorkflowDesignDrawer.vue";
import { onMounted, reactive, ref } from "vue";

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const selectedWorkflow = ref<WorkflowTable>();
const createVisible = ref(false);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_task:workflow:definition",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("task.flowName"),
      type: "input",
      attrs: { placeholder: t("task.inputFlowName"), clearable: true },
    },
    {
      prop: "code",
      label: t("task.flowCode"),
      type: "input",
      attrs: { placeholder: t("task.inputFlowCode"), clearable: true },
    },
    {
      prop: "status",
      label: t("task.status"),
      type: "select",
      options: [
        { label: t("task.draft"), value: "draft" },
        { label: t("task.published"), value: "published" },
        { label: t("task.archived"), value: "archived" },
      ],
      attrs: { placeholder: t("task.selectStatus"), clearable: true, style: { width: "170px" } },
    },
  ],
});

function normalizeWorkflowQuery(params: Record<string, unknown>): WorkflowPageQuery {
  const p = { ...params } as Record<string, unknown>;
  if (p.status === "" || p.status === null) p.status = undefined;
  return p as unknown as WorkflowPageQuery;
}

const contentConfig = reactive<IContentConfig<WorkflowPageQuery>>({
  permPrefix: "module_task:workflow:definition",
  title: t("task.workflowListTitle"),
  tooltip: t("task.workflowListTip"),
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
    const res = await WorkflowDefinitionAPI.getWorkflowList(
      normalizeWorkflowQuery(params as unknown as Record<string, unknown>)
    );
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: (ids) =>
    WorkflowDefinitionAPI.deleteWorkflow(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n) && n > 0)
    ),
  deleteConfirm: {
    title: t("task.warn"),
    message: t("task.deleteWorkflowConfirm"),
    type: "warning",
  },
});

function handleRowDelete(id?: number) {
  if (id == null) return;
  contentRef.value?.handleDelete(id);
}

function handleCreate() {
  selectedWorkflow.value = undefined;
  createVisible.value = true;
}

function handleEdit(record: WorkflowTable) {
  selectedWorkflow.value = record;
  createVisible.value = true;
}

function getStatusType(status: string) {
  const typeMap: Record<string, string> = {
    draft: "info",
    published: "success",
    archived: "warning",
  };
  return typeMap[status] || "";
}

function getStatusText(status: string) {
  const textMap: Record<string, string> = {
    draft: t("task.draft"),
    published: t("task.published"),
    archived: t("task.archived"),
  };
  return textMap[status] || status;
}

function handlePublish(record: WorkflowTable) {
  ElMessageBox.confirm(t("task.publishConfirm"), t("task.publishConfirmTitle"), {
    confirmButtonText: t("task.confirm"),
    cancelButtonText: t("task.cancel"),
    type: "warning",
  })
    .then(async () => {
      try {
        if (!record.id) {
          ElMessage.error(t("task.workflowIdMissing"));
          return;
        }
        await WorkflowDefinitionAPI.publishWorkflow(record.id, {});
        ElMessage.success(t("task.publishSuccess"));
        refreshList();
      } catch {
        ElMessage.error(t("task.publishFailed"));
      }
    })
    .catch(() => {});
}

function handleExecute(action: string, record: WorkflowTable) {
  if (action !== "execute") return;
  ElMessageBox.confirm(t("task.executeConfirm"), t("task.executeConfirmTitle"), {
    confirmButtonText: t("task.confirm"),
    cancelButtonText: t("task.cancel"),
    type: "warning",
  })
    .then(async () => {
      try {
        if (!record.id) {
          ElMessage.error(t("task.workflowIdMissing"));
          return;
        }
        const res = await WorkflowDefinitionAPI.executeWorkflow({
          workflow_id: record.id,
          variables: {},
        });
        if (res.data?.data) {
          const result = res.data.data;
          ElMessage.success(
            t("task.executeSuccess", {
              status: result.status === "completed" ? t("task.success") : t("task.failed"),
            })
          );
        }
        refreshList();
      } catch {
        ElMessage.error(t("task.executeFailed"));
      }
    })
    .catch(() => {});
}

onMounted(() => {
  refreshList();
});
</script>

<style scoped lang="scss"></style>
