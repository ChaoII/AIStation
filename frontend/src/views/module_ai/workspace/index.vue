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
        <el-radio-group v-model="typeFilter" size="default">
          <el-radio-button v-for="t in typeOptions" :key="t.value" :value="t.value">
            {{ t.label }}
          </el-radio-button>
        </el-radio-group>
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
        <el-row v-loading="loading" :gutter="12">
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
  </div>
</template>

<script setup lang="ts">
import { ChatDotRound, MoreFilled, Plus, Search } from "@element-plus/icons-vue";
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
import IconTile from "@/views/module_ai/market/components/IconTile.vue";

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

function onCreate(cmd: string) {
  if (cmd === "agent") router.push("/ai/agent");
  else if (cmd === "workflow") router.push("/ai/workflow");
  else if (cmd === "app") router.push("/ai/app");
  else if (cmd === "cron") ElMessage.info("定时任务创建即将开放");
}

function toggleEnable(it: WorkspaceItem, val: boolean) {
  it.enabled = val;
  ElMessage.success("已更新启用状态");
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
</script>

<style lang="scss" scoped>
.ai-workspace-page {
  height: 100%;
  display: flex;
  flex-direction: column;
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
  margin-bottom: 12px;
  padding: 16px 18px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    transform 0.2s,
    border-color 0.2s;
  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 6px 18px rgb(0 0 0 / 8%);
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
  margin: 12px 0;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
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
