<!-- AI 工作台：左「分类」独立卡片 + 右「工具栏 + 卡片网格」独立卡片（区域隔离，参照个人工作空间） -->
<template>
  <div class="app-container ai-workspace-page">
    <div class="ws-layout">
      <!-- 左：分类树（独立卡片） -->
      <el-card shadow="never" class="ws-side">
        <template #header>
          <div class="ws-side-head">
            <span>分类</span>
            <el-button link type="primary" :icon="Plus" @click="openCatCreate(null)" />
          </div>
        </template>
        <el-tree
          class="ai-tree"
          :data="treeData"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="currentCategoryId ?? undefined"
          highlight-current
          default-expand-all
          :expand-on-click-node="false"
          @node-click="onCatClick"
        >
          <template #default="{ data }">
            <span class="ai-tree-node">
              <el-icon class="ai-tree-node__icon"><Folder /></el-icon>
              <span class="ai-tree-node__label" :title="data.name">{{ data.name }}</span>
              <span class="ai-tree-node__count">{{ catCount(data.id) }}</span>
              <el-dropdown trigger="click" @command="(c: string) => onCatCmd(data, c)">
                <el-icon class="ws-tree-more" @click.stop><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="addchild" icon="plus">新建子分类</el-dropdown-item>
                    <el-dropdown-item icon="EditPen" command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item
                      icon="delete"
                      command="delete"
                      style="color: var(--el-color-danger)"
                      divided
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </template>
        </el-tree>
      </el-card>

      <!-- 右：工具栏 + 智能体家族卡片（独立卡片） -->
      <el-card shadow="never" class="ws-main">
        <div class="ws-toolbar">
          <el-select v-model="typeFilter" style="width: 150px" @change="page = 1">
            <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
          <div class="ws-toolbar-right">
            <el-input
              v-model="keyword"
              placeholder="搜索条目"
              clearable
              :prefix-icon="Search"
              style="width: 200px"
              @clear="page = 1"
            />
            <!-- 全部类别：下拉二选一；已选具体类别：直接新建该类（语境收敛） -->
            <el-dropdown v-if="typeFilter === 'all'" trigger="click" @command="onCreate">
              <el-button type="primary" :icon="Plus">新建</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="agent">传统智能体</el-dropdown-item>
                  <el-dropdown-item command="workflow">工作流</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-else type="primary" :icon="Plus" @click="onCreate(typeFilter)">
              新建{{ typeFilter === "agent" ? "智能体" : "工作流" }}
            </el-button>
          </div>
        </div>
        <div class="ws-grid-wrap">
          <el-row v-loading="loading" :gutter="16" class="ws-card-grid">
            <el-col
              v-for="it in pagedItems"
              :key="`${it.type}-${it.id}`"
              :xs="24"
              :sm="12"
              :md="12"
              :lg="8"
              :xl="6"
            >
              <div class="ws-card" @click="openChat(it)">
                <div class="ws-card__head">
                  <IconTile :item="{ icon: it.icon, asset_type: it.type }" :size="'sm'" />
                  <div class="ws-card__title">
                    <div class="ws-card__name">{{ it.name }}</div>
                    <!-- 副行（参照能力市场）：类型 + 角色 + 分类 -->
                    <div class="ws-card__sub">
                      <el-tag
                        v-if="typeFilter === 'all'"
                        size="small"
                        :type="typeTag[it.type]"
                        effect="plain"
                      >
                        {{ it.label }}
                      </el-tag>
                      <span v-if="roleOf(it)" class="ws-card__role">{{ roleOf(it) }}</span>
                      <span v-if="categoryName(it.category_id)" class="ws-card__cat">
                        {{ categoryName(it.category_id) }}
                      </span>
                    </div>
                  </div>
                  <el-switch
                    :model-value="it.enabled"
                    size="small"
                    @click.stop
                    @change="(v: any) => toggleEnable(it, v)"
                  />
                </div>
                <!-- 描述：固定两行高度（无描述显示占位符），与能力市场卡片一致 -->
                <div class="ws-card__desc" :class="{ 'is-empty': !it.description }">
                  {{ it.description || "暂无描述" }}
                </div>
                <!-- 能力标签：模型/工具/技能/知识库/MCP/节点（固定占位，保证卡片大小统一） -->
                <div class="ws-card__tags">
                  <el-tag
                    v-for="t in capTags(it)"
                    :key="t.text"
                    size="small"
                    :type="t.type"
                    effect="plain"
                  >
                    {{ t.text }}
                  </el-tag>
                </div>
                <div class="ws-card__foot">
                  <span class="ws-card__time">
                    <el-icon><Clock /></el-icon>
                    {{ fmtTime(it.created_time) }}
                  </span>
                  <div class="ws-card__actions">
                    <el-button
                      type="primary"
                      size="small"
                      :icon="ChatDotRound"
                      @click.stop="openChat(it)"
                    >
                      对话
                    </el-button>
                    <el-dropdown trigger="click" @command="(cmd: string) => onCardMore(it, cmd)">
                      <el-button link :icon="MoreFilled" class="ws-card__more" @click.stop />
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="edit" :icon="Edit">编辑</el-dropdown-item>
                          <el-dropdown-item
                            command="delete"
                            :icon="Delete"
                            divided
                            style="color: var(--el-color-danger)"
                          >
                            删除
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </div>
              </div>
            </el-col>
            <el-col v-if="!loading && !pagedItems.length" :span="24">
              <el-empty description="当前分类暂无条目" />
            </el-col>
          </el-row>
        </div>
        <div v-if="pagedItems.length > pageSize" class="ws-pagination">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="filteredItems.length"
            layout="total, sizes, prev, pager, next"
            background
          />
        </div>
      </el-card>
    </div>

    <!-- 新建/重命名分类弹窗 -->
    <el-dialog v-model="catDialogVisible" :title="catDialogTitle" width="520px">
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
import {
  ChatDotRound,
  Clock,
  Delete,
  Edit,
  Folder,
  MoreFilled,
  Plus,
  Search,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import {
  createWorkspaceCategory,
  deleteWorkspaceCategory,
  getWorkspaceCategoryTree,
  getWorkspaceItems,
  updateWorkspaceCategory,
  type WorkspaceCategory,
  type WorkspaceItem,
} from "@/api/module_ai/workspace";
import { batchAgentStatus, deleteAiAgent, getAiAgentDetail } from "@/api/module_ai/agent";
import { deleteAiWorkflow, getAiWorkflowDetail, updateAiWorkflow } from "@/api/module_ai/workflow";
import { getAiModelList } from "@/api/module_ai/model";
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
/** 类别筛选：`all` 为「全部」（el-select 对空串按无值处理，会误显 placeholder） */
const typeFilter = ref("all");
const page = ref(1);
const pageSize = 12;

/** 类别筛选（替代原顶部类型 tab）：工作台只服务智能体家族（传统智能体 + 工作流编排） */
const typeOptions = [
  { label: "全部", value: "all" },
  { label: "传统智能体", value: "agent" },
  { label: "工作流", value: "workflow" },
];

/** el-tag 的主题类型（Element Plus 原生枚举） */
type TagType = "primary" | "success" | "warning" | "info" | "danger";

const typeTag: Record<string, TagType> = {
  agent: "primary",
  workflow: "success",
};

// 模型列表（用于卡片显示模型名）
const modelOptions = ref<{ id: number; name: string }[]>([]);
function modelName(id?: number | null): string {
  if (!id) return "";
  return modelOptions.value.find((m) => m.id === id)?.name || "";
}
async function loadModelOptions() {
  try {
    const res: any = await getAiModelList({});
    modelOptions.value = (res.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
  } catch {
    modelOptions.value = [];
  }
}

/** 副行角色：智能体用 agent_role（meta.role）；工作流无该字段，返回空串 */
function roleOf(it: WorkspaceItem): string {
  return String(it.meta?.role || "");
}

/** 卡片能力标签：统一口径 —— 模型必显示（无绑定标「默认」），其余计数仅在有值时显示 */
function capTags(it: WorkspaceItem): { text: string; type: TagType }[] {
  const m = it.meta || {};
  const tags: { text: string; type: TagType }[] = [];
  if (it.type === "agent") {
    const mn = modelName(m.model_id);
    tags.push({ text: `模型 ${mn || "默认"}`, type: "primary" });
    if (m.tools) tags.push({ text: `工具 ${m.tools}`, type: "warning" });
    if (m.skills) tags.push({ text: `技能 ${m.skills}`, type: "success" });
    if (m.knowledge) tags.push({ text: `知识库 ${m.knowledge}`, type: "success" });
    if (m.mcp) tags.push({ text: `MCP ${m.mcp}`, type: "danger" });
  } else if (it.type === "workflow") {
    if (m.nodes) tags.push({ text: `节点 ${m.nodes}`, type: "success" });
  }
  return tags;
}

// 时间格式化（YYYY-MM-DD HH:mm）
function fmtTime(t?: string | null): string {
  if (!t) return "";
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return String(t);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const filteredItems = computed(() => {
  // 工作台只服务智能体家族：应用在「AI应用」菜单、定时任务在「定时任务」菜单，均不再聚合展示
  let list = allItems.value.filter((i) => i.type === "agent" || i.type === "workflow");
  if (typeFilter.value !== "all") list = list.filter((i) => i.type === typeFilter.value);
  if (keyword.value) list = list.filter((i) => (i.name || "").includes(keyword.value));
  return list;
});
const pagedItems = computed(() =>
  filteredItems.value.slice((page.value - 1) * pageSize, page.value * pageSize)
);

/** 分类计数（含子分类）：该分类及子孙分类下的智能体/工作流数量（与树形计数徽章对应） */
function catCount(id: number): number {
  const ids = new Set<number>([id]);
  const walk = (list: WorkspaceCategory[]) => {
    for (const n of list || []) {
      if (ids.has(n.id) && n.children?.length) walk(n.children);
    }
  };
  walk(treeData.value);
  return allItems.value.filter(
    (i) =>
      (i.type === "agent" || i.type === "workflow") &&
      i.category_id != null &&
      ids.has(i.category_id)
  ).length;
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
    const res: any = await getWorkspaceItems({ category_id: currentCategoryId.value ?? undefined });
    allItems.value = res.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadTree();
  loadItems();
  loadModelOptions();
});

function onCatClick(data: WorkspaceCategory) {
  currentCategoryId.value = data.id;
  page.value = 1;
  loadItems();
}

function openChat(it: WorkspaceItem) {
  router.push(`/ai/workspace/chat/${it.type}/${it.id}`);
}

// 卡片「更多」：编辑（内嵌对应编辑器） + 删除（确认后按类型删）
async function onCardMore(it: WorkspaceItem, cmd: string) {
  if (cmd === "edit") {
    if (it.type === "agent") openAgentEdit(it);
    else if (it.type === "workflow") await openWorkflowEdit(it);
    return;
  }
  if (cmd === "delete") {
    await ElMessageBox.confirm(`将删除「${it.name}」，是否继续？`, "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    // 先收窄类型再取删除函数（WorkspaceItem.type 声明仍含历史的 app/cron）
    if (it.type === "agent" || it.type === "workflow") {
      const del = { agent: deleteAiAgent, workflow: deleteAiWorkflow }[it.type];
      await del([it.id]);
      ElMessage.success("已删除");
      loadItems();
    }
  }
}

function onCreate(cmd: string) {
  if (cmd === "agent") openAgentCreate();
  else if (cmd === "workflow") openWorkflowCreate();
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

/** 启停：真实落库（agent 走批量状态接口；workflow 走部分更新），失败回滚开关 */
async function toggleEnable(it: WorkspaceItem, val: boolean) {
  const prev = it.enabled;
  it.enabled = val;
  try {
    if (it.type === "agent") await batchAgentStatus([it.id], val);
    else if (it.type === "workflow") await updateAiWorkflow(it.id, { enabled: val });
    ElMessage.success(val ? "已启用" : "已停用");
  } catch {
    it.enabled = prev;
  }
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
  ElMessage.success("保存成功");
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
    ElMessage.success("删除成功");
    if (currentCategoryId.value === data.id) currentCategoryId.value = null;
    loadTree();
    loadItems();
  }
}
</script>

<style lang="scss">
.app-container.ai-workspace-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  overflow: hidden;
}

/* 布局：左分类卡片 + 右内容卡片，两块各自独立（参照个人工作空间） */
.ai-workspace-page .ws-layout {
  display: flex;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
}

/* 左：分类树卡片（独立容器，不再与内容挤在同一面板） */
.ai-workspace-page .ws-side {
  flex: 0 0 240px;
  min-width: 0;
  overflow: auto;
}

.ai-workspace-page .ws-side > .el-card__header {
  padding: 12px 16px;
}

.ai-workspace-page .ws-side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* 右：工具栏 + 卡片网格（独立容器） */
.ai-workspace-page .ws-main {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
}

.ai-workspace-page .ws-main > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-workspace-page .ws-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.ai-workspace-page .ws-toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ai-workspace-page .ws-grid-wrap {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 16px;
  overflow-x: hidden;
  overflow-y: auto;
}

/* 卡片网格：行距 16px（列距由 el-row gutter 负责） */
.ai-workspace-page .ws-card-grid {
  row-gap: 16px;
}

.ai-workspace-page .ws-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  padding-top: 8px;
}

.ai-workspace-page .ws-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 4px;
}

.ai-workspace-page .ws-tree-more {
  cursor: pointer;
  opacity: 0;
}
.ai-workspace-page .ws-tree-node:hover .ws-tree-more {
  opacity: 1;
}

.ai-workspace-page .ws-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px;
  cursor: pointer;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
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

.ai-workspace-page .ws-card__head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.ai-workspace-page .ws-card__title {
  flex: 1;
  min-width: 0;
}

.ai-workspace-page .ws-card__name {
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
}

/* 副行（参照能力市场）：类型 tag + 角色 + 分类 */
.ai-workspace-page .ws-card__sub {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ai-workspace-page .ws-card__role,
.ai-workspace-page .ws-card__cat {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 描述：固定两行高度（无描述显示占位符），与能力市场卡片一致 */
.ai-workspace-page .ws-card__desc {
  display: -webkit-box;
  min-height: 40px;
  margin: 12px 0;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  color: var(--el-text-color-regular);
  -webkit-box-orient: vertical;
}

.ai-workspace-page .ws-card__desc.is-empty {
  color: var(--el-text-color-placeholder);
}

/* 能力标签区：固定最小高度，保证各卡大小统一 */
.ai-workspace-page .ws-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  margin-bottom: 10px;
}

.ai-workspace-page .ws-card__foot {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  margin-top: auto;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ai-workspace-page .ws-card__time {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.ai-workspace-page .ws-card__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  align-items: center;
}

/* 「更多」：link 图标按钮，去掉 circle 边框（用户反馈圆圈很丑） */
.ai-workspace-page .ws-card__more {
  color: var(--el-text-color-secondary);
}

.ai-workspace-page .ws-card__more:hover {
  color: var(--el-color-primary);
}
</style>
