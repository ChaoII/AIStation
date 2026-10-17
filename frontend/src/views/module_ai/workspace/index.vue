<!-- AI 工作台：左侧树形分类 + 右侧多类型卡片区（智能体/工作流/定时任务/应用） -->
<template>
  <div class="app-container ai-workspace-page">
    <!-- 顶部工具条（白底，不落蓝灰底） -->
    <div class="ws-toolbar">
      <div class="ws-toolbar__left">
        <span class="ws-title">工作台</span>
        <el-tag size="small" effect="plain" type="info">{{ currentCatName }}</el-tag>
      </div>
      <div class="ws-toolbar__right">
        <el-input
          v-model="keyword"
          placeholder="搜索条目"
          clearable
          :prefix-icon="Search"
          style="width: 200px"
        />
        <el-dropdown trigger="click" @command="onCreate">
          <el-button type="primary" :icon="Plus">新建</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="agent">智能体</el-dropdown-item>
              <el-dropdown-item command="workflow">工作流</el-dropdown-item>
              <el-dropdown-item command="app">应用</el-dropdown-item>
              <el-dropdown-item command="cron">定时任务</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-row :gutter="12" class="ws-body">
      <!-- 左：分类树 -->
      <el-col :xs="24" :sm="6" :md="5" :lg="4" class="ws-tree-col">
        <div class="ws-tree-card">
          <div class="ws-tree-head">
            <span>分类</span>
            <el-button link type="primary" :icon="Plus" @click="openCatCreate(null)" />
          </div>
          <el-tree
            :data="treeData"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            :current-node-key="currentCategoryId ?? undefined"
            highlight-current
            @node-click="onCatClick"
          >
            <template #default="{ data }">
              <span class="ws-tree-node">
                <span class="ws-tree-label">{{ data.name }}</span>
                <el-dropdown trigger="click" @command="(c: string) => onCatCmd(data, c)">
                  <el-icon class="ws-tree-more" @click.stop><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="addchild">新建子分类</el-dropdown-item>
                      <el-dropdown-item command="rename">重命名</el-dropdown-item>
                      <el-dropdown-item command="delete" style="color: #f56c6c" divided>
                        删除
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </span>
            </template>
          </el-tree>
        </div>
      </el-col>

      <!-- 右：卡片区 -->
      <el-col :xs="24" :sm="18" :md="19" :lg="20">
        <div class="ws-type-bar">
          <el-tabs v-model="typeFilter" class="ws-type-tabs">
            <el-tab-pane v-for="t in typeOptions" :key="t.value" :label="t.label" :name="t.value" />
          </el-tabs>
        </div>
        <el-row v-loading="loading" :gutter="16">
          <el-col
            v-for="it in pagedItems"
            :key="`${it.type}-${it.id}`"
            :xs="24"
            :sm="12"
            :md="8"
            :lg="6"
          >
            <div class="ws-card" @click="openChat(it)">
              <div class="ws-card__head">
                <IconTile :item="{ icon: it.icon, asset_type: it.type }" :size="'sm'" />
                <div class="ws-card__title">
                  <div class="ws-card__name">{{ it.name }}</div>
                  <el-tag size="small" :type="typeTag[it.type]" effect="plain">
                    {{ it.label }}
                  </el-tag>
                </div>
                <el-switch
                  :model-value="it.enabled"
                  size="small"
                  @click.stop
                  @change="(v: any) => toggleEnable(it, v)"
                />
              </div>
              <div class="ws-card__desc">{{ it.description || "暂无描述" }}</div>
              <div v-if="metaText(it)" class="ws-card__meta">{{ metaText(it) }}</div>
              <div class="ws-card__foot">
                <el-button
                  type="primary"
                  size="small"
                  :icon="ChatDotRound"
                  @click.stop="openChat(it)"
                >
                  对话
                </el-button>
                <span v-if="categoryName(it.category_id)" class="ws-card__cat">
                  {{ categoryName(it.category_id) }}
                </span>
                <el-dropdown trigger="click" @command="(cmd: string) => onCardMore(it, cmd)">
                  <el-button size="small" circle :icon="MoreFilled" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit">编辑</el-dropdown-item>
                      <el-dropdown-item command="delete" style="color: #f56c6c" divided>
                        删除
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </el-col>
          <el-col v-if="!loading && !pagedItems.length" :span="24">
            <el-empty description="当前分类暂无条目" />
          </el-col>
        </el-row>
        <div v-if="pagedItems.length > pageSize" class="ws-pagination">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="filteredItems.length"
            layout="total, prev, pager, next"
            background
          />
        </div>
      </el-col>
    </el-row>

    <!-- 新建/重命名分类弹窗 -->
    <el-dialog v-model="catDialogVisible" :title="catDialogTitle" width="420px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="catForm.name" placeholder="分类名称" />
        </el-form-item>
        <el-form-item v-if="!catForm.parent_id" label="主题色">
          <el-color-picker v-model="catForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="catDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCategory">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建定时任务弹窗 -->
    <el-dialog v-model="cronDialogVisible" title="新建定时任务" width="480px">
      <el-form label-width="90px">
        <el-form-item label="任务名称">
          <el-input v-model="cronForm.name" placeholder="任务名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="cronForm.description" placeholder="任务描述" />
        </el-form-item>
        <el-form-item label="Cron 表达式">
          <el-input v-model="cronForm.cron" placeholder="如 0 9 * * 1-5（工作日 9 点）" />
        </el-form-item>
        <el-form-item label="执行目标">
          <el-select v-model="cronForm.target_type" style="width: 100%">
            <el-option label="智能体" value="agent" />
            <el-option label="工作流" value="workflow" />
            <el-option label="应用" value="app" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标ID">
          <el-input-number v-model="cronForm.target_id" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="cronForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cronDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCron">保存</el-button>
      </template>
    </el-dialog>

    <!-- 智能体内嵌新建/编辑 -->
    <AgentFormDialog v-model="agentDialogVisible" :agent="agentEditItem" @refresh="loadItems" />

    <!-- 工作流内嵌编辑器 -->
    <WorkflowEditor
      v-model:visible="workflowEditVisible"
      :workflow="workflowEditItem"
      @refresh="loadItems"
    />
  </div>
</template>

<script setup lang="ts">
import { ChatDotRound, MoreFilled, Plus, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import {
  createWorkspaceCategory,
  createWorkspaceCron,
  deleteWorkspaceCategory,
  deleteWorkspaceCron,
  getWorkspaceCategoryTree,
  getWorkspaceItems,
  updateWorkspaceCategory,
  type WorkspaceCategory,
  type WorkspaceItem,
} from "@/api/module_ai/workspace";
import { deleteAiAgent, getAiAgentDetail } from "@/api/module_ai/agent";
import { deleteAiWorkflow, getAiWorkflowDetail } from "@/api/module_ai/workflow";
import { deleteAiApp } from "@/api/module_ai/app";
import IconTile from "@/views/module_ai/market/components/IconTile.vue";
import WorkflowEditor from "@/views/module_ai/workflow/components/WorkflowEditor.vue";
import AgentFormDialog from "@/views/module_ai/workspace/components/AgentFormDialog.vue";

defineOptions({ name: "AiWorkbench" });

const router = useRouter();

const loading = ref(false);
const treeData = ref<WorkspaceCategory[]>([]);
const allItems = ref<WorkspaceItem[]>([]);
const currentCategoryId = ref<number | null>(null);
const keyword = ref("");
const typeFilter = ref("");
const page = ref(1);
const pageSize = 12;

const typeOptions = [
  { label: "全部", value: "" },
  { label: "智能体", value: "agent" },
  { label: "工作流", value: "workflow" },
  { label: "定时任务", value: "cron" },
  { label: "应用", value: "app" },
];

const typeTag: Record<string, "primary" | "success" | "warning" | "info" | "danger"> = {
  agent: "primary",
  workflow: "success",
  cron: "warning",
  app: "info",
};

function metaText(it: WorkspaceItem): string {
  const m = it.meta || {};
  if (it.type === "agent") {
    if (m.role) return m.role;
    const parts: string[] = [];
    if (m.tools) parts.push(`${m.tools} 工具`);
    if (m.skills) parts.push(`${m.skills} 技能`);
    if (m.mcp) parts.push(`${m.mcp} MCP`);
    if (m.knowledge) parts.push(`${m.knowledge} 知识库`);
    return parts.join(" · ");
  }
  if (it.type === "workflow") return m.nodes ? `${m.nodes} 节点` : "";
  if (it.type === "app") {
    const parts: string[] = [];
    if (m.app_type) parts.push(m.app_type);
    if (m.tools) parts.push(`${m.tools} 工具`);
    return parts.join(" · ");
  }
  if (it.type === "cron") {
    const parts: string[] = [];
    if (m.cron) parts.push(m.cron);
    if (m.target_type) parts.push(`目标 ${m.target_type}`);
    return parts.join(" · ");
  }
  return "";
}

const filteredItems = computed(() => {
  let list = allItems.value;
  if (typeFilter.value) list = list.filter((i) => i.type === typeFilter.value);
  if (keyword.value) list = list.filter((i) => (i.name || "").includes(keyword.value));
  return list;
});
const pagedItems = computed(() =>
  filteredItems.value.slice((page.value - 1) * pageSize, page.value * pageSize)
);

const currentCatName = computed(() => {
  if (!currentCategoryId.value) return "全部";
  const target = currentCategoryId.value;
  return treeData.value.find((n) => findCat(n, target))?.name || "全部";
});

function findCat(node: WorkspaceCategory, id: number | null): boolean {
  if (id == null) return false;
  if (node.id === id) return true;
  return (node.children || []).some((c) => findCat(c, id));
}

function categoryName(id?: number | null) {
  if (!id) return "";
  for (const n of treeData.value) {
    const found = findNode(n, id);
    if (found) return found.name;
  }
  return "";
}

function findNode(node: WorkspaceCategory, id: number): WorkspaceCategory | null {
  if (node.id === id) return node;
  for (const c of node.children || []) {
    const r = findNode(c, id);
    if (r) return r;
  }
  return null;
}

async function loadTree() {
  const res: any = await getWorkspaceCategoryTree();
  treeData.value = res.data?.data || [];
}

async function loadItems() {
  loading.value = true;
  try {
    const res: any = await getWorkspaceItems({
      category_id: currentCategoryId.value ?? undefined,
    });
    allItems.value = res.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadTree();
  loadItems();
});

function onCatClick(data: WorkspaceCategory) {
  currentCategoryId.value = data.id;
  page.value = 1;
  loadItems();
}

function openChat(it: WorkspaceItem) {
  router.push(`/ai/workspace/chat/${it.type}/${it.id}`);
}

// 卡片「更多」：编辑（跳转对应管理页） + 删除（确认后按类型删）
async function onCardMore(it: WorkspaceItem, cmd: string) {
  if (cmd === "edit") {
    if (it.type === "agent") openAgentEdit(it);
    else if (it.type === "workflow") await openWorkflowEdit(it);
    else if (it.type === "app") router.push("/ai/app");
    else if (it.type === "cron") ElMessage.info("点到对应条目编辑");
    return;
  }
  if (cmd === "delete") {
    await ElMessageBox.confirm(`将删除「${it.name}」，是否继续？`, "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    const del = {
      agent: deleteAiAgent,
      workflow: deleteAiWorkflow,
      app: deleteAiApp,
      cron: deleteWorkspaceCron,
    }[it.type];
    if (del) {
      if (it.type === "cron") await (del as any)(it.id);
      else await (del as any)([it.id]);
      ElMessage.success("已删除");
      loadItems();
    }
  }
}

function onCreate(cmd: string) {
  if (cmd === "agent") openAgentCreate();
  else if (cmd === "workflow") openWorkflowCreate();
  else if (cmd === "app") router.push("/ai/app");
  else if (cmd === "cron") openCronCreate();
}

// 智能体内嵌编辑/新建（菜单已并入工作台，不再跳 /ai/agent）
const agentDialogVisible = ref(false);
const agentEditItem = ref<any>(null);
function openAgentCreate() {
  agentEditItem.value = null;
  agentDialogVisible.value = true;
}
async function openAgentEdit(it: WorkspaceItem) {
  const res: any = await getAiAgentDetail(it.id);
  const d = res.data?.data;
  if (!d) return ElMessage.error("智能体不存在");
  agentEditItem.value = d;
  agentDialogVisible.value = true;
}

function toggleEnable(it: WorkspaceItem, val: boolean) {
  it.enabled = val;
  ElMessage.success("已更新启用状态");
}

// 工作流内嵌编辑
const workflowEditVisible = ref(false);
const workflowEditItem = ref<any>(null);
async function openWorkflowEdit(it: WorkspaceItem) {
  const res: any = await getAiWorkflowDetail(it.id);
  const d = res.data?.data;
  if (!d) return ElMessage.error("工作流不存在");
  workflowEditItem.value = d;
  workflowEditVisible.value = true;
}
function openWorkflowCreate() {
  workflowEditItem.value = null; // 新建模式：WorkflowEditor 无 workflow 时走 create
  workflowEditVisible.value = true;
}

// ---- 分类弹窗 ----
const catDialogVisible = ref(false);
const catDialogTitle = ref("新建分类");
const catForm = ref<{ id: number | null; name: string; parent_id: number | null; color: string }>({
  id: null,
  name: "",
  parent_id: null,
  color: "",
});

function openCatCreate(parent: WorkspaceCategory | null) {
  catDialogTitle.value = "新建分类";
  catForm.value = { id: null, name: "", parent_id: parent?.id ?? null, color: "" };
  catDialogVisible.value = true;
}

async function saveCategory() {
  if (!catForm.value.name.trim()) return ElMessage.warning("请输入分类名称");
  if (catForm.value.id) {
    await updateWorkspaceCategory(catForm.value.id, {
      name: catForm.value.name,
      color: catForm.value.color,
    });
  } else {
    await createWorkspaceCategory({
      name: catForm.value.name,
      parent_id: catForm.value.parent_id,
      color: catForm.value.color,
    });
  }
  catDialogVisible.value = false;
  loadTree();
}

async function onCatCmd(data: WorkspaceCategory, cmd: string) {
  if (cmd === "addchild") openCatCreate(data);
  else if (cmd === "rename") {
    catDialogTitle.value = "重命名分类";
    catForm.value = {
      id: data.id,
      name: data.name,
      parent_id: data.parent_id ?? null,
      color: data.color || "",
    };
    catDialogVisible.value = true;
  } else if (cmd === "delete") {
    await ElMessageBox.confirm(
      `将删除分类「${data.name}」（子分类与条目会被移出分类），是否继续？`,
      "删除分类",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
    await deleteWorkspaceCategory(data.id);
    if (currentCategoryId.value === data.id) currentCategoryId.value = null;
    loadTree();
    loadItems();
  }
}

// ---- 定时任务弹窗 ----
const cronDialogVisible = ref(false);
const cronForm = ref({
  name: "",
  description: "",
  cron: "",
  target_type: "agent",
  target_id: 0,
  category_id: null as number | null,
  enabled: true,
});

function openCronCreate() {
  cronForm.value = {
    name: "",
    description: "",
    cron: "",
    target_type: "agent",
    target_id: 0,
    category_id: currentCategoryId.value,
    enabled: true,
  };
  cronDialogVisible.value = true;
}

async function saveCron() {
  if (!cronForm.value.name.trim() || !cronForm.value.cron.trim()) {
    ElMessage.warning("请填写任务名称与 cron 表达式");
    return;
  }
  await createWorkspaceCron({ ...cronForm.value });
  cronDialogVisible.value = false;
  ElMessage.success("定时任务已创建");
  loadItems();
}
</script>

<style lang="scss" scoped>
.ai-workspace-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 12px;
  box-sizing: border-box;
  background: var(--el-color-white);
}

.ws-type-bar {
  margin-bottom: 12px;
}

.ws-type-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 0;
  }
  :deep(.el-tabs__nav-wrap::after) {
    height: 1px;
  }
}

.ws-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  margin-bottom: 12px;
}

.ws-title {
  font-size: var(--el-font-size-large);
  font-weight: 600;
}

.ws-toolbar__left,
.ws-toolbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ws-body {
  flex: 1 1 auto;
  min-height: 0;
}

.ws-tree-card {
  height: 100%;
  overflow: auto;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 12px;
}

.ws-tree-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 8px;
}

.ws-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 4px;
}

.ws-tree-more {
  opacity: 0;
  cursor: pointer;
}
.ws-tree-node:hover .ws-tree-more {
  opacity: 1;
}

.ws-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  margin-bottom: 16px;
  padding: 18px 20px;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    transform 0.2s,
    border-color 0.2s;
  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 8px 20px rgb(0 0 0 / 8%);
    transform: translateY(-2px);
  }
}

.ws-card__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ws-card__title {
  min-width: 0;
  flex: 1;
}

.ws-card__name {
  font-weight: 600;
  font-size: var(--el-font-size-base);
  line-height: 1.5;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ws-card__desc {
  margin: 12px 0 6px;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ws-card__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ws-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ws-card__cat {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ws-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}
</style>
