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
      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-button
            v-hasPerm="['module_ai:workflow:create']"
            type="primary"
            :icon="Plus"
            @click="handleOpen()"
          >
            新建工作流
          </el-button>
          <el-button :icon="DataAnalysis" @click="openCompare">对比</el-button>
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
          <el-table-column label="节点" width="80" align="center">
            <template #default="{ row }">{{ (row.graph?.nodes || []).length }}</template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="80" align="center" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                {{ row.enabled ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updated_time" label="更新时间" width="170" />
          <el-table-column label="操作" width="220" fixed="right">
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
                v-hasPerm="['module_ai:workflow:create']"
                link
                type="success"
                size="small"
                @click="handleCopy(row)"
              >
                复制
              </el-button>
              <el-button
                v-hasPerm="['module_ai:workflow:update']"
                link
                type="warning"
                size="small"
                @click="handleToggleEnable(row)"
              >
                {{ row.enabled ? "停用" : "启用" }}
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

    <!-- 多工作流对比 -->
    <el-dialog v-model="compareVisible" title="多工作流对比" width="560px" append-to-body>
      <div class="cmp-selects">
        <el-select v-model="compareA" filterable placeholder="选择工作流 A" style="flex: 1">
          <el-option v-for="w in compareWorkflows" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
        <el-select v-model="compareB" filterable placeholder="选择工作流 B" style="flex: 1">
          <el-option v-for="w in compareWorkflows" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
        <el-button type="primary" @click="runCompare">对比</el-button>
        <el-button :disabled="!compareResult.length" @click="exportCompare">导出</el-button>
      </div>
      <div v-if="compareResult.length" class="cmp-result">
        <div class="cmp-result__title">差异（A → B）</div>
        <div v-for="(d, i) in compareResult" :key="i" class="cmp-item">
          <el-tag
            size="small"
            :type="d.status === '新增' ? 'success' : d.status === '删除' ? 'danger' : 'warning'"
          >
            {{ d.status }}
          </el-tag>
          <span class="cmp-label">{{ d.label }}</span>
          <span class="cmp-detail">{{ d.detail }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, DataAnalysis } from "@element-plus/icons-vue";
import { useCrudList } from "@/components/CURD/useCrudList";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import {
  getAiWorkflowList,
  deleteAiWorkflow,
  createAiWorkflow,
  updateAiWorkflow,
} from "@/api/module_ai/workflow";
import { nodeDefOf } from "./nodes";
import WorkflowEditor from "./components/WorkflowEditor.vue";

defineOptions({ name: "AiWorkflow" });

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_ai:workflow",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "名称",
      type: "input",
      attrs: { placeholder: "工作流名称", clearable: true, style: { width: "200px" } },
    },
    {
      prop: "enabled",
      label: "启用",
      type: "select",
      options: [
        { label: "启用", value: "true" },
        { label: "停用", value: "false" },
      ],
      attrs: { placeholder: "状态", clearable: true, style: { width: "160px" } },
    },
  ],
});

const contentConfig = reactive<IContentConfig>({
  permPrefix: "module_ai:workflow",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params: any) => {
    const res = await getAiWorkflowList();
    let list = res.data?.data || [];
    const name = (params?.name || "").trim().toLowerCase();
    if (name) list = list.filter((w: any) => (w.name || "").toLowerCase().includes(name));
    const en = params?.enabled;
    if (en !== undefined && en !== "") {
      list = list.filter((w: any) => String(w.enabled) === String(en));
    }
    const pn = Number(params?.page_no || 1);
    const ps = Number(params?.page_size || 10);
    const total = list.length;
    return { total, list: list.slice((pn - 1) * ps, pn * ps) };
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

// ---------- 多工作流对比 ----------
const compareVisible = ref(false);
const compareWorkflows = ref<any[]>([]);
const compareA = ref();
const compareB = ref();
const compareResult = ref<{ label: string; status: string; detail: string }[]>([]);
async function openCompare() {
  const res = await getAiWorkflowList();
  compareWorkflows.value = res.data?.data || [];
  compareA.value = undefined;
  compareB.value = undefined;
  compareResult.value = [];
  compareVisible.value = true;
}
function runCompare() {
  if (compareA.value == null || compareB.value == null) {
    ElMessage.warning("请选择两个工作流");
    return;
  }
  const a = compareWorkflows.value.find((w) => w.id === compareA.value);
  const b = compareWorkflows.value.find((w) => w.id === compareB.value);
  if (!a || !b) return;
  const aMap = new Map(((a.graph?.nodes || []) as any[]).map((n) => [n.id, n]));
  const bMap = new Map(((b.graph?.nodes || []) as any[]).map((n) => [n.id, n]));
  const items: { label: string; status: string; detail: string }[] = [];
  bMap.forEach((n, id) => {
    const av = aMap.get(id);
    if (!av) items.push({ label: nodeDefOf(n.type).label, status: "新增", detail: "B 新增节点" });
    else if (JSON.stringify(n.data || {}) !== JSON.stringify(av.data || {}))
      items.push({ label: nodeDefOf(n.type).label, status: "修改", detail: "参数已变化" });
  });
  aMap.forEach((n, id) => {
    if (!bMap.has(id))
      items.push({ label: nodeDefOf(n.type).label, status: "删除", detail: "B 中已移除" });
  });
  compareResult.value = items;
}
function exportCompare() {
  if (!compareResult.value.length) return;
  const a = compareWorkflows.value.find((w) => w.id === compareA.value);
  const b = compareWorkflows.value.find((w) => w.id === compareB.value);
  const lines: string[] = [
    `# 工作流对比：${a?.name}  vs  ${b?.name}`,
    "",
    "| 状态 | 节点 | 说明 |",
    "| --- | --- | --- |",
  ];
  compareResult.value.forEach((d) => {
    lines.push(`| ${d.status} | ${d.label} | ${d.detail} |`);
  });
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const el = document.createElement("a");
  el.href = url;
  el.download = "workflow-compare.md";
  el.click();
  URL.revokeObjectURL(url);
  ElMessage.success("已导出对比报告");
}

async function handleCopy(row: any) {
  ElMessageBox.confirm(`将复制工作流「${row.name}」为新工作流，是否继续？`, "复制确认", {
    confirmButtonText: "复制",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await createAiWorkflow({
        name: `${row.name}（副本）`,
        description: row.description || "",
        graph: row.graph || { nodes: [], edges: [] },
        enabled: false,
      });
      ElMessage.success("已复制为新工作流");
      refreshList();
    })
    .catch(() => {
      /* 取消 */
    });
}

async function handleToggleEnable(row: any) {
  await updateAiWorkflow(row.id, { enabled: !row.enabled });
  ElMessage.success(row.enabled ? "已停用" : "已启用");
  refreshList();
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

<style lang="scss">
.cmp-selects {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.cmp-result {
  padding: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;

  .cmp-result__title {
    margin-bottom: 8px;
    font-weight: 600;
  }

  .cmp-item {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px dashed var(--el-border-color-lighter);

    .cmp-detail {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }
}
</style>
