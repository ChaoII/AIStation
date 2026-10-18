<!-- AI 工作台：左侧树形分类 + 右侧多类型卡片区（智能体/工作流/定时任务/应用） -->
<template>
  <div class="app-container ai-workspace-page">
    <!-- 白色面板：铺满可用区域，四周蓝灰边框；类型 tab 在顶部，右侧搜索/新增 -->
    <el-card shadow="never" class="ws-shell" :body-style="{ padding: '0 16px 12px' }">
      <!-- 类型 tab（左）+ 右侧搜索/新增 -->
      <div class="ws-tabbar">
        <el-tabs v-model="typeFilter" class="ws-main-tabs">
          <el-tab-pane v-for="t in typeOptions" :key="t.value" :label="t.label" :name="t.value" />
        </el-tabs>
        <div class="ws-tab-actions">
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

      <!-- 主体：左分类树 + 右卡片区（同高） -->
      <div class="ws-main">
        <!-- 左：分类树 -->
        <div class="ws-side">
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
        </div>

        <!-- 右：卡片区 -->
        <div class="ws-content">
          <el-row v-loading="loading" :gutter="16" class="ws-card-grid">
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
                <!--
                  定时任务：触发方式 / 描述 / 下次运行。
                  三项都取自后端（`/cron/list` 的 trigger、trigger_args、next_run_time），前端**不自算**，
                  否则会与调度器形成第二套口径；`needs_review` 为真表示该行按新校验不通过（或迁移被跳过），
                  必须显式提示人工改写，否则会「有任务但调度不上」静默停摆。
                -->
                <div v-if="it.type === 'cron'" class="ws-card__cron">
                  <div class="ws-card__cron-line">
                    <span class="ws-card__cron-label">触发方式：</span>
                    <el-tag size="small" effect="plain" :type="triggerMeta(cronTrigger(it)).type">
                      {{ triggerMeta(cronTrigger(it)).text }}
                    </el-tag>
                    <el-tag v-if="cronNeedsReview(it)" size="small" type="warning">
                      需人工确认
                    </el-tag>
                  </div>
                  <div class="ws-card__cron-line">
                    <span class="ws-card__cron-label">描述：</span>
                    <span class="ws-card__cron-text">{{ cronArgsText(it) }}</span>
                  </div>
                  <div class="ws-card__cron-line">
                    <span class="ws-card__cron-label">下次运行：</span>
                    <span class="ws-card__cron-text">{{ cronNextRun(it) }}</span>
                  </div>
                </div>
                <!-- 能力标签：模型/工具/节点/知识库/MCP/技能/问数 -->
                <div v-if="capTags(it).length" class="ws-card__tags">
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
                  <span class="ws-card__cat">
                    <span v-if="categoryName(it.category_id)" class="ws-card__cat-name">
                      {{ categoryName(it.category_id) }}
                    </span>
                    <span class="ws-card__time">{{ fmtTime(it.created_time) }}</span>
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
        </div>
      </div>
    </el-card>

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

    <!-- 新建定时任务弹窗（触发方式统一走 TriggerEditor，描述与下次运行时间来自后端统一层） -->
    <el-dialog v-model="cronDialogVisible" title="新建定时任务" width="600px">
      <el-form label-width="90px">
        <el-form-item label="任务名称">
          <el-input v-model="cronForm.name" placeholder="任务名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="cronForm.description" placeholder="任务描述" />
        </el-form-item>
        <el-form-item label="触发方式">
          <TriggerEditor
            v-model:trigger="cronForm.trigger"
            v-model:trigger-args="cronForm.trigger_args"
            @error="cronError = $event"
          />
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
import { getAiModelList } from "@/api/module_ai/model";
import request from "@/utils/request";
import IconTile from "@/views/module_ai/market/components/IconTile.vue";
import WorkflowEditor from "@/views/module_ai/workflow/components/WorkflowEditor.vue";
import AgentFormDialog from "@/views/module_ai/workspace/components/AgentFormDialog.vue";
import TriggerEditor from "@/components/TriggerEditor/index.vue";

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

/** el-tag 的主题类型（Element Plus 原生枚举） */
type TagType = "primary" | "success" | "warning" | "info" | "danger";

const typeTag: Record<string, TagType> = {
  agent: "primary",
  workflow: "success",
  cron: "warning",
  app: "info",
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

// 卡片能力标签：按类型展示模型/工具/节点/知识库/MCP/技能/问数等
function capTags(it: WorkspaceItem): { text: string; type: TagType }[] {
  const m = it.meta || {};
  const tags: { text: string; type: TagType }[] = [];
  if (it.type === "agent") {
    const mn = modelName(m.model_id);
    if (mn) tags.push({ text: mn, type: "primary" });
    if (m.tools) tags.push({ text: `${m.tools} 工具`, type: "warning" });
    if (m.skills) tags.push({ text: `${m.skills} 技能`, type: "success" });
    if (m.knowledge) tags.push({ text: `${m.knowledge} 知识库`, type: "success" });
    if (m.mcp) tags.push({ text: `${m.mcp} MCP`, type: "danger" });
  } else if (it.type === "workflow") {
    if (m.nodes) tags.push({ text: `${m.nodes} 节点`, type: "success" });
  } else if (it.type === "app") {
    const mn = modelName(m.model_id);
    if (m.app_type) tags.push({ text: m.app_type, type: "info" });
    if (mn) tags.push({ text: mn, type: "primary" });
    if (m.tools) tags.push({ text: `${m.tools} 工具`, type: "warning" });
  } else if (it.type === "cron") {
    // 触发方式 / 描述 / 下次运行由卡片专属区块展示（见模板 ws-card__cron），这里只留执行目标
    if (m.target_type) tags.push({ text: `目标 ${m.target_type}`, type: "warning" });
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
  let list = allItems.value;
  if (typeFilter.value) list = list.filter((i) => i.type === typeFilter.value);
  if (keyword.value) list = list.filter((i) => (i.name || "").includes(keyword.value));
  return list;
});
const pagedItems = computed(() =>
  filteredItems.value.slice((page.value - 1) * pageSize, page.value * pageSize)
);

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
    // 聚合条目（卡片）+ 定时任务明细（触发方式/需人工确认）：并发取，避免串行等待
    const [itemsRes] = await Promise.all([
      getWorkspaceItems({ category_id: currentCategoryId.value ?? undefined }),
      loadCronRows(),
    ]);
    allItems.value = itemsRes.data?.data?.items || [];
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

/**
 * 定时任务列表行（`/cron/list`）：卡片展示「触发方式 / 描述 / 下次运行 / 需人工确认」所需字段。
 *
 * 聚合条目接口 `/items` 的 cron 条目只带 `meta.cron`（= trigger_args）与 `meta.next_run_time`，
 * 拿不到 `trigger`（触发类型）与 `needs_review`，故列表加载时并行取一次本模块自己的 `/cron/list`。
 * 取值一律来自后端（`TriggerUtil` 口径），前端不自算。
 */
interface CronRow {
  id: number;
  trigger?: string | null;
  trigger_args?: unknown;
  next_run_time?: string | null;
  needs_review?: boolean;
}

const cronRows = ref<Record<number, CronRow>>({});

async function loadCronRows() {
  try {
    const res: any = await request({ url: "/ai/workspace/cron/list", method: "get" });
    const rows: CronRow[] = res.data?.data?.items || [];
    const map: Record<number, CronRow> = {};
    for (const row of rows) map[row.id] = row;
    cronRows.value = map;
  } catch {
    // 取不到明细不影响主列表：卡片按聚合条目的 meta 兜底展示（见 cronTrigger/cronArgsText）
    cronRows.value = {};
  }
}

/** 触发类型 → 中文名 + 标签色（与 TriggerEditor 的四种类型一一对应） */
const TRIGGER_LABELS: Record<string, { text: string; type: TagType }> = {
  cron: { text: "定时", type: "primary" },
  interval: { text: "间隔", type: "success" },
  date: { text: "单次", type: "warning" },
  now: { text: "立即", type: "info" },
};

/** 未知/历史触发类型不做假设，原样显示（避免模板取不到标签色而报错） */
function triggerMeta(trigger: string): { text: string; type: TagType } {
  return TRIGGER_LABELS[trigger] || { text: trigger || "未配置", type: "info" };
}

function cronRow(it: WorkspaceItem): CronRow | null {
  return cronRows.value[it.id] || null;
}

/** 触发类型：列表行缺失时按后端 `_cron_dict` 同口径兜底为 `cron` */
function cronTrigger(it: WorkspaceItem): string {
  return cronRow(it)?.trigger || "cron";
}

/** 描述：后端列表未回传「人话描述」，故按原样显示 `trigger_args`（保存时的同一份契约值） */
function cronArgsText(it: WorkspaceItem): string {
  const row = cronRow(it);
  const args = row ? row.trigger_args : it.meta?.cron;
  if (args === null || args === undefined || args === "") {
    // 「立即」按契约无参数（不是缺配置），与真正的空表达式（迁移跳过）区分开
    return cronTrigger(it) === "now" ? "—" : "未配置";
  }
  return typeof args === "string" ? args : JSON.stringify(args);
}

function cronNextRun(it: WorkspaceItem): string {
  const row = cronRow(it);
  return fmtTime((row ? row.next_run_time : it.meta?.next_run_time) as string | undefined) || "—";
}

/** 需人工确认：① 表达式为空（迁移跳过）② 表达式非空但按新校验不通过（后端统一层判定） */
function cronNeedsReview(it: WorkspaceItem): boolean {
  return Boolean(cronRow(it)?.needs_review);
}

const cronDialogVisible = ref(false);
const cronForm = ref({
  name: "",
  description: "",
  /** 触发类型：cron / interval / date / now（TriggerEditor 的四种类型） */
  trigger: "cron",
  /** 触发参数：cron 为 5 段表达式，interval 为 JSON，date 为时间字符串，now 为 null */
  trigger_args: "" as unknown,
  target_type: "agent",
  target_id: 0,
  category_id: null as number | null,
  enabled: true,
});

/** TriggerEditor 上抛的非法原因（非空即拦截保存）；空串表示配置合法 */
const cronError = ref("");

function openCronCreate() {
  cronError.value = "";
  cronForm.value = {
    name: "",
    description: "",
    // 参数留空：TriggerEditor 会按类型回落到规范默认值（定时 → 每天 09:00）
    trigger: "cron",
    trigger_args: "",
    target_type: "agent",
    target_id: 0,
    category_id: currentCategoryId.value,
    enabled: true,
  };
  cronDialogVisible.value = true;
}

/**
 * 保存用的 `trigger_args`：与后端存储契约一致——
 * interval 落 JSON 字符串（后端 `TriggerUtil` 两种形态都认），date 落时间字符串，now 无参数。
 */
function serializeTriggerArgs(trigger: string, args: unknown): string | null {
  if (trigger === "now") return null;
  if (trigger === "interval") return JSON.stringify(args ?? {});
  return typeof args === "string" ? args : String(args ?? "");
}

async function saveCron() {
  if (!cronForm.value.name.trim()) {
    ElMessage.warning("请填写任务名称");
    return;
  }
  // 组件已判定非法（结论来自后端统一层）：不放行，并把可读原因提示出来
  if (cronError.value) {
    ElMessage.error(cronError.value);
    return;
  }
  const trigger = cronForm.value.trigger;
  const triggerArgs = serializeTriggerArgs(trigger, cronForm.value.trigger_args);
  // 先落到变量再传参：绕开「对象字面量多余属性检查」（新字段尚未进 api 模块的类型声明）
  const payload = {
    name: cronForm.value.name,
    description: cronForm.value.description,
    // 新字段（统一层口径）：后端优先认这两个
    trigger,
    trigger_args: triggerArgs,
    // 兼容字段：仅「定时」时带表达式，其余类型留空（避免旧后端把它当成另一套调度语义存下来）
    cron: trigger === "cron" ? String(triggerArgs ?? "") : "",
    target_type: cronForm.value.target_type,
    target_id: cronForm.value.target_id,
    category_id: cronForm.value.category_id,
    enabled: cronForm.value.enabled,
  };
  await createWorkspaceCron(payload);
  cronDialogVisible.value = false;
  ElMessage.success("定时任务已创建");
  loadItems();
}
</script>

<style lang="scss">
.app-container.ai-workspace-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 12px;
  box-sizing: border-box;
}

/* 白色面板：铺满剩余高度，蓝灰边框（参考能力市场） */
.ai-workspace-page .ws-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.ai-workspace-page .ws-shell > .el-card__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* tab 行：tabs 左，搜索/新增 右侧 */
.ai-workspace-page .ws-tabbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.ai-workspace-page .ws-main-tabs {
  flex: 1 1 auto;
  min-width: 0;
}

.ai-workspace-page .ws-main-tabs > .el-tabs__header {
  margin-bottom: 8px;
}

.ai-workspace-page .ws-tab-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 主体：左树 + 右卡片，同高 */
.ai-workspace-page .ws-main {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  gap: 12px;
}

.ai-workspace-page .ws-side {
  flex: 0 0 220px;
  min-width: 0;
  min-height: 0;
}

.ai-workspace-page .ws-content {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

/* 卡片网格：上下/左右间距统一 16px（列用 gutter，行用 row-gap） */
.ai-workspace-page .ws-card-grid {
  row-gap: 16px;
}

.ai-workspace-page .ws-tree-card {
  height: 100%;
  overflow: auto;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  padding: 12px;
}

.ai-workspace-page .ws-tree-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  margin-bottom: 8px;
}

.ai-workspace-page .ws-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 4px;
}

.ai-workspace-page .ws-tree-more {
  opacity: 0;
  cursor: pointer;
}
.ai-workspace-page .ws-tree-node:hover .ws-tree-more {
  opacity: 1;
}

.ai-workspace-page .ws-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
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

.ai-workspace-page .ws-card__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ai-workspace-page .ws-card__title {
  min-width: 0;
  flex: 1;
}

.ai-workspace-page .ws-card__name {
  font-weight: 600;
  font-size: var(--el-font-size-base);
  line-height: 1.5;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ai-workspace-page .ws-card__desc {
  margin: 12px 0 8px;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 能力标签区 */
.ai-workspace-page .ws-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  margin-bottom: 10px;
}

/* 定时任务：触发方式 / 描述 / 下次运行（次要说明统一 12px） */
.ai-workspace-page .ws-card__cron {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  font-size: 12px;
}

.ai-workspace-page .ws-card__cron-line {
  display: flex;
  gap: 4px;
  align-items: center;
  min-width: 0;
}

.ai-workspace-page .ws-card__cron-label {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
}

.ai-workspace-page .ws-card__cron-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.ai-workspace-page .ws-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ai-workspace-page .ws-card__cat {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ai-workspace-page .ws-card__cat-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.ai-workspace-page .ws-card__time {
  white-space: nowrap;
}

.ai-workspace-page .ws-card__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ai-workspace-page .ws-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}
</style>
