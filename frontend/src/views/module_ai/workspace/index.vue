<!-- AI 工作台：左「分类」独立卡片 + 右「工具栏 + 卡片网格」独立卡片（区域隔离，参照个人工作空间） -->
<template>
  <div class="app-container ai-workspace-page">
    <div class="ws-layout">      <!-- 左：分类树（独立卡片） -->
      <el-card shadow="never" class="ws-side">
        <template #header>
          <div class="ws-side-head">
            <span>{{ t("ai_chat.workspace_category") }}</span>
            <el-button link type="primary" :icon="Plus" @click="openCatCreate(null)" />
          </div>
        </template>
        <el-tree
          class="ai-tree"
          :data="treeData"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :current-node-key="currentNodeId"
          highlight-current
          default-expand-all
          :expand-on-click-node="false"
          @node-click="onCatClick"
        >
          <template #default="{ data }">
            <span class="ai-tree-node">
              <el-icon class="ai-tree-node__icon">
                <component :is="data.id === 0 ? Files : Folder" />
              </el-icon>
              <span class="ai-tree-node__label" :title="data.name">{{ data.name }}</span>
              <span class="ai-tree-node__count">{{ catCount(data.id) }}</span>
              <span v-if="data.id !== 0" class="ws-tree-actions">
                <el-button
                  link
                  type="primary"
                  class="ws-tree-add"
                  :title="t('ai_chat.workspace_addChildCategory')"
                  :icon="Plus"
                  @click.stop="openCatCreate(data)"
                />
                <el-dropdown trigger="click" @command="(c: string) => onCatCmd(data, c)">
                  <el-icon class="ws-tree-more" @click.stop><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="addchild" icon="plus">
                        {{ t("ai_chat.workspace_addChildCategory") }}
                      </el-dropdown-item>
                      <el-dropdown-item icon="EditPen" command="rename">
                        {{ t("ai_chat.workspace_rename") }}
                      </el-dropdown-item>
                      <el-dropdown-item
                        icon="delete"
                        command="delete"
                        style="color: var(--el-color-danger)"
                        divided
                      >
                        {{ t("ai_chat.workspace_delete") }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </span>
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
              :placeholder="t('ai_chat.workspace_search')"
              clearable
              :prefix-icon="Search"
              style="width: 200px"
              @clear="page = 1"
            />
            <!-- 全部类别：下拉二选一；已选具体类别：直接新建该类（语境收敛） -->
            <el-dropdown v-if="typeFilter === 'all'" trigger="click" @command="onCreate">
              <el-button type="primary" :icon="Plus">
                {{ t("ai_chat.workspace_create") }}
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="agent">
                    {{ t("ai_chat.workspace_agent") }}
                  </el-dropdown-item>
                  <el-dropdown-item command="workflow">
                    {{ t("ai_chat.workspace_workflow") }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button v-else type="primary" :icon="Plus" @click="onCreate(typeFilter)">
              {{
                t("ai_chat.workspace_createWithType", {
                  type:
                    typeFilter === "agent"
                      ? t("ai_chat.workspace_agent")
                      : t("ai_chat.workspace_workflow"),
                })
              }}
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
                  {{ it.description || t("ai_chat.workspace_noDesc") }}
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
                      {{ t("ai_chat.workspace_chat") }}
                    </el-button>
                    <el-dropdown trigger="click" @command="(cmd: string) => onCardMore(it, cmd)">
                      <el-button link :icon="MoreFilled" class="ws-card__more" @click.stop />
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="edit" :icon="Edit">
                            {{ t("ai_chat.workspace_edit") }}
                          </el-dropdown-item>
                          <el-dropdown-item
                            v-hasPerm="'module_ai:asset_embed:manage'"
                            command="embed"
                            :icon="Link"
                          >
                            {{ t("ai_workflow.asset_embed") }}
                          </el-dropdown-item>
                          <el-dropdown-item
                            command="delete"
                            :icon="Delete"
                            divided
                            style="color: var(--el-color-danger)"
                          >
                            {{ t("ai_chat.workspace_delete") }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </div>
              </div>
            </el-col>
            <el-col v-if="!loading && !pagedItems.length" :span="24">
              <el-empty :description="t('ai_chat.workspace_empty')" />
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
        <el-form-item :label="t('ai_chat.workspace_name')">
          <el-input v-model="catForm.name" :placeholder="t('ai_chat.workspace_categoryName')" />
        </el-form-item>
        <el-form-item v-if="!catForm.parent_id" :label="t('ai_chat.workspace_themeColor')">
          <el-color-picker v-model="catForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="catDialogVisible = false">
          {{ t("ai_chat.workspace_cancel") }}
        </el-button>
        <el-button type="primary" @click="saveCategory">
          {{ t("ai_chat.workspace_save") }}
        </el-button>
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

    <!-- 资产嵌入弹窗（卡片「更多 → 嵌入」） -->
    <AssetEmbedDialog
      v-model="embedVisible"
      :kind="embedItem?.type ?? 'agent'"
      :target-id="embedItem?.id ?? 0"
      :name="embedItem?.name"
    />
  </div>
</template>

<script setup lang="ts">
import {
  ChatDotRound,
  Clock,
  Delete,
  Edit,
  Files,
  Folder,
  Link,
  MoreFilled,
  Plus,
  Search,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
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
import AssetEmbedDialog from "@/views/module_ai/workspace/components/AssetEmbedDialog.vue";

defineOptions({ name: "AiWorkbench" });

const { t } = useI18n();

const router = useRouter();

const loading = ref(false);
const treeData = ref<WorkspaceCategory[]>([]);
const allItems = ref<WorkspaceItem[]>([]);
const currentCategoryId = ref<number | null>(null);
/** 树当前高亮节点（「全部」根节点 id=0；currentCategoryId=null 表示查看全部） */
const currentNodeId = ref<number>(0);
const keyword = ref("");
/** 类别筛选：`all` 为「全部」（el-select 对空串按无值处理，会误显 placeholder） */
const typeFilter = ref("all");
const page = ref(1);
const pageSize = 12;

/** 类别筛选（替代原顶部类型 tab）：工作台只服务智能体家族（传统智能体 + 工作流编排） */
const typeOptions = [
  { label: t("ai_chat.workspace_all"), value: "all" },
  { label: t("ai_chat.workspace_agent"), value: "agent" },
  { label: t("ai_chat.workspace_workflow"), value: "workflow" },
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
    tags.push({
      text: t("ai_chat.workspace_capModel", { name: mn || t("ai_chat.workspace_default") }),
      type: "primary",
    });
    if (m.tools)
      tags.push({ text: t("ai_chat.workspace_capTools", { count: m.tools }), type: "warning" });
    if (m.skills)
      tags.push({ text: t("ai_chat.workspace_capSkills", { count: m.skills }), type: "success" });
    if (m.knowledge)
      tags.push({
        text: t("ai_chat.workspace_capKnowledge", { count: m.knowledge }),
        type: "success",
      });
    if (m.mcp) tags.push({ text: t("ai_chat.workspace_capMcp", { count: m.mcp }), type: "danger" });
  } else if (it.type === "workflow") {
    if (m.nodes)
      tags.push({ text: t("ai_chat.workspace_capNodes", { count: m.nodes }), type: "success" });
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
  // 分类过滤：只显示该分类「直系」条目（不含子分类）。本地过滤，避免每点一次重新调后端转圈
  if (currentCategoryId.value != null) {
    list = list.filter((i) => i.category_id === currentCategoryId.value);
  }
  if (typeFilter.value !== "all") list = list.filter((i) => i.type === typeFilter.value);
  if (keyword.value) list = list.filter((i) => (i.name || "").includes(keyword.value));
  return list;
});
const pagedItems = computed(() =>
  filteredItems.value.slice((page.value - 1) * pageSize, page.value * pageSize)
);

/**
 * 分类计数（agent + 工作流）：只数该分类「直系」条目，不含子分类。
 * 「全部」根节点（id=0）统计所有智能体/工作流（含未分类）。
 */
function catCount(id: number): number {
  if (id === 0) {
    return allItems.value.filter((i) => i.type === "agent" || i.type === "workflow").length;
  }
  return allItems.value.filter(
    (i) => (i.type === "agent" || i.type === "workflow") && i.category_id === id
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
  const cats: WorkspaceCategory[] = res.data?.data || [];
  // 树顶加虚拟「全部」根节点（id=0），其下挂全部分类；点它=查看全部条目
  treeData.value = [
    { id: 0, name: t("ai_chat.workspace_all"), children: cats } as WorkspaceCategory,
  ];
}

async function loadItems() {
  loading.value = true;
  try {
    // 始终拉全量条目；分类筛选在前端本地做（避免每点一次/增删后触发后端慢查询转圈）
    const res: any = await getWorkspaceItems({});
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
  currentCategoryId.value = data.id === 0 ? null : data.id;
  currentNodeId.value = data.id;
  page.value = 1;
  // 本地过滤已加载的 allItems，不再重新调后端（避免每次点击都触发慢查询、转圈卡顿）
}

function openChat(it: WorkspaceItem) {
  router.push(`/ai/workspace/chat/${it.type}/${it.id}`);
}

// 资产嵌入：固定当前卡片为 agent/workflow，打开三形式嵌入弹窗
const embedVisible = ref(false);
const embedItem = ref<{ type: "agent" | "workflow"; id: number; name: string } | null>(null);
function openEmbed(it: WorkspaceItem) {
  if (it.type !== "agent" && it.type !== "workflow") return;
  embedItem.value = { type: it.type, id: it.id, name: it.name };
  embedVisible.value = true;
}

// 卡片「更多」：嵌入 / 编辑（内嵌对应编辑器） + 删除（确认后按类型删）
async function onCardMore(it: WorkspaceItem, cmd: string) {
  if (cmd === "embed") {
    openEmbed(it);
    return;
  }
  if (cmd === "edit") {
    if (it.type === "agent") openAgentEdit(it);
    else if (it.type === "workflow") await openWorkflowEdit(it);
    return;
  }
  if (cmd === "delete") {
    await ElMessageBox.confirm(
      t("ai_chat.workspace_deleteConfirm", { name: it.name }),
      t("ai_chat.workspace_deleteTitle"),
      {
        confirmButtonText: t("ai_chat.workspace_delete"),
        cancelButtonText: t("ai_chat.workspace_cancel"),
        type: "warning",
      }
    );
    // 先收窄类型再取删除函数（WorkspaceItem.type 声明仍含历史的 app/cron）
    if (it.type === "agent" || it.type === "workflow") {
      const del = { agent: deleteAiAgent, workflow: deleteAiWorkflow }[it.type];
      await del([it.id]);
      ElMessage.success(t("ai_chat.workspace_deleted"));
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
  if (!d) return ElMessage.error(t("ai_chat.workspace_agentNotFound"));
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
    ElMessage.success(val ? t("ai_chat.workspace_enabled") : t("ai_chat.workspace_disabled"));
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
  if (!d) return ElMessage.error(t("ai_chat.workspace_workflowNotFound"));
  workflowEditItem.value = d;
  workflowEditVisible.value = true;
}
function openWorkflowCreate() {
  workflowEditItem.value = null; // 新建模式：WorkflowEditor 无 workflow 时走 create
  workflowEditVisible.value = true;
}

// ---- 分类弹窗 ----
const catDialogVisible = ref(false);
const catDialogTitle = ref(t("ai_chat.workspace_createCategory"));
const catForm = ref<{ id: number | null; name: string; parent_id: number | null; color: string }>({
  id: null,
  name: "",
  parent_id: null,
  color: "",
});

function openCatCreate(parent: WorkspaceCategory | null) {
  catDialogTitle.value = t("ai_chat.workspace_createCategory");
  catForm.value = { id: null, name: "", parent_id: parent?.id ?? null, color: "" };
  catDialogVisible.value = true;
}

async function saveCategory() {
  if (!catForm.value.name.trim())
    return ElMessage.warning(t("ai_chat.workspace_inputCategoryName"));
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
  ElMessage.success(t("ai_chat.workspace_saveSuccess"));
  loadTree();
}

async function onCatCmd(data: WorkspaceCategory, cmd: string) {
  if (cmd === "addchild") openCatCreate(data);
  else if (cmd === "rename") {
    catDialogTitle.value = t("ai_chat.workspace_renameCategory");
    catForm.value = {
      id: data.id,
      name: data.name,
      parent_id: data.parent_id ?? null,
      color: data.color || "",
    };
    catDialogVisible.value = true;
  } else if (cmd === "delete") {
    await ElMessageBox.confirm(
      t("ai_chat.workspace_deleteCategoryConfirm", { name: data.name }),
      t("ai_chat.workspace_deleteCategory"),
      {
        confirmButtonText: t("ai_chat.workspace_delete"),
        cancelButtonText: t("ai_chat.workspace_cancel"),
        type: "warning",
      }
    );
    await deleteWorkspaceCategory(data.id);
    ElMessage.success(t("ai_chat.workspace_deleteSuccess"));
    if (currentCategoryId.value === data.id) {
      currentCategoryId.value = null;
      currentNodeId.value = 0;
    }
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

.ai-workspace-page .ws-tree-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 6px;
}

/* 「＋」新建子分类：默认轻微可见，悬停变醒目（保证总能发现建子目录入口） */
.ai-workspace-page .ws-tree-add {
  opacity: 0.55;
}

/* 「⋮」更多（重命名/删除）：悬停显示。注意选择器必须匹配模板的 ai-tree-node，
   此前误写 .ws-tree-node 导致悬停永不触发、按钮一直 opacity:0 看不见 */
.ai-workspace-page .ws-tree-more {
  cursor: pointer;
  opacity: 0;
}
.ai-workspace-page .ai-tree-node:hover .ws-tree-more {
  opacity: 1;
}
.ai-workspace-page .ai-tree-node:hover .ws-tree-add {
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
