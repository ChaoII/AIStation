<!-- AI 工作流编排：列表 + 打开画布编辑器 -->
<template>
  <div class="app-container ai-workflow-page">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <div class="data-table__toolbar--left">
          <el-button
            v-hasPerm="['module_ai:workflow:create']"
            type="primary"
            :icon="Plus"
            @click="handleOpen()"
          >
            新建工作流
          </el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading }">
        <el-table v-loading="loading" :data="data" row-key="id">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column prop="version" label="版本" width="80" align="center" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updated_time" label="更新时间" width="170" />
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button
                v-hasPerm="['module_ai:workflow:update']"
                link
                type="primary"
                size="small"
                @click="handleOpen(row)"
              >
                编辑
              </el-button>
              <el-button
                v-hasPerm="['module_ai:workflow:delete']"
                link
                type="danger"
                size="small"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </PageContent>

    <WorkflowEditor
      v-model:visible="editorVisible"
      :workflow="currentWorkflow"
      @refresh="refreshList"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { getAiWorkflowList, deleteAiWorkflow } from "@/api/module_ai/workflow";
import WorkflowEditor from "./components/WorkflowEditor.vue";

defineOptions({ name: "AiWorkflow" });

const searchConfig = reactive<ISearchConfig>({ formItems: [] });

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:workflow",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: false,
  indexAction: async () => {
    const res = await getAiWorkflowList();
    return res.data?.data || [];
  },
  deleteAction: async (ids: string) => {
    const idList = ids
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => !Number.isNaN(n));
    await deleteAiWorkflow(idList);
  },
  deleteConfirm: { title: "警告", message: "确认删除所选工作流?", type: "warning" },
});

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const editorVisible = ref(false);
const currentWorkflow = ref<any>();

function handleOpen(row?: any) {
  currentWorkflow.value = row || undefined;
  editorVisible.value = true;
}

function handleDelete(row: any) {
  ElMessageBox.confirm(`确定删除工作流「${row.name}」吗？删除后不可恢复。`, "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiWorkflow([row.id]);
      ElMessage.success("删除成功");
      refreshList();
    })
    .catch(() => {
      /* 取消 */
    });
}
</script>
