<!-- AI 智能体大厅：分类侧栏 + 卡片网格 + 新建/编辑弹窗 + 对话入口 -->
<template>
  <div class="app-container ai-agent-page">
    <el-row :gutter="12" style="height: 100%">
      <!-- 分类侧栏 -->
      <el-col :xs="24" :sm="5" :md="4" :lg="3">
        <el-card shadow="never" class="agent-category-card">
          <div class="category-header">
            <span class="category-title">分类</span>
            <el-button
              v-hasPerm="['module_ai:agent:create']"
              link
              type="primary"
              :icon="Plus"
              @click="openCategoryDialog()"
            />
          </div>
          <div class="category-list">
            <div
              class="category-item"
              :class="{ active: currentCategory === null }"
              @click="selectCategory(null)"
            >
              全部
            </div>
            <div
              v-for="c in categories"
              :key="c.id"
              class="category-item"
              :class="{ active: currentCategory === c.id }"
              @click="selectCategory(c.id)"
            >
              {{ c.name }}
              <el-dropdown
                trigger="click"
                style="margin-left: auto"
                @command="onCategoryCmd(c, $event)"
              >
                <el-icon class="category-more" :class="{ active: currentCategory === c.id }">
                  <MoreFilled />
                </el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">重命名</el-dropdown-item>
                    <el-dropdown-item command="delete" style="color: #f56c6c">
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 智能体卡片 -->
      <el-col :xs="24" :sm="19" :md="20" :lg="21">
        <div class="agent-toolbar">
          <div class="agent-toolbar__left">
            <el-button
              v-hasPerm="['module_ai:agent:create']"
              type="primary"
              :icon="Plus"
              @click="openAgentDialog()"
            >
              新建智能体
            </el-button>
          </div>
          <div class="agent-toolbar__right">
            <el-input
              v-model="keyword"
              placeholder="搜索智能体"
              clearable
              :prefix-icon="Search"
              style="width: 220px"
            />
          </div>
        </div>

        <el-row v-loading="loading" :gutter="12">
          <el-col v-for="a in filteredAgents" :key="a.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
            <el-card shadow="hover" class="agent-card" :body-style="{ padding: '16px' }">
              <div class="agent-card__head">
                <div class="agent-avatar" :style="{ background: a.color || '#409eff' }">
                  {{ a.agent_name.slice(0, 1) }}
                </div>
                <div class="agent-card__meta">
                  <div class="agent-card__name">{{ a.agent_name }}</div>
                  <el-tag size="small" :type="a.enabled ? 'success' : 'info'">
                    {{ a.enabled ? "启用" : "停用" }}
                  </el-tag>
                </div>
              </div>
              <div class="agent-card__role">{{ a.agent_role || "—" }}</div>
              <div class="agent-card__tags">
                <el-tag v-if="a.workflow_id" size="small" effect="plain" type="primary">
                  编排
                </el-tag>
                <el-tag v-if="a.prompt_id" size="small" effect="plain">提示词</el-tag>
                <el-tag v-if="(a.tool_ids || []).length" size="small" effect="plain" type="warning">
                  {{ a.tool_ids.length }} 工具
                </el-tag>
                <el-tag
                  v-if="(a.knowledge_ids || []).length"
                  size="small"
                  effect="plain"
                  type="success"
                >
                  知识库
                </el-tag>
                <el-tag
                  v-if="(a.skill_ids || []).length"
                  size="small"
                  effect="plain"
                  type="warning"
                >
                  技能
                </el-tag>
              </div>
              <div class="agent-card__actions">
                <el-button
                  v-hasPerm="['module_ai:agent:query']"
                  type="primary"
                  size="small"
                  :icon="ChatDotRound"
                  @click="runAgent(a)"
                >
                  对话
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:agent:update']"
                  size="small"
                  :icon="Edit"
                  @click="openAgentDialog(a)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:agent:delete']"
                  size="small"
                  type="danger"
                  :icon="Delete"
                  @click="deleteAgent(a)"
                />
              </div>
            </el-card>
          </el-col>
          <el-col v-if="!loading && filteredAgents.length === 0" :span="24">
            <el-empty description="暂无智能体" />
          </el-col>
        </el-row>
      </el-col>
    </el-row>

    <!-- 智能体编辑弹窗 -->
    <el-dialog
      v-model="agentDialogVisible"
      :title="editingAgent ? '编辑智能体' : '新建智能体'"
      width="620px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="agentForm" label-width="90px" size="default">
        <el-form-item label="名称" required>
          <el-input v-model="agentForm.agent_name" placeholder="智能体名称" />
        </el-form-item>
        <el-form-item label="角色描述">
          <el-input
            v-model="agentForm.agent_role"
            type="textarea"
            :rows="2"
            placeholder="这个智能体是做什么的"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select
            v-model="agentForm.category_id"
            clearable
            placeholder="选择分类"
            style="width: 100%"
          >
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="运行方式">
          <el-radio-group v-model="agentForm.runMode" @change="onRunModeChange">
            <el-radio value="workflow">绑定工作流</el-radio>
            <el-radio value="model">模型+提示词</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="agentForm.runMode === 'workflow'" label="工作流">
          <el-select
            v-model="agentForm.workflow_id"
            clearable
            placeholder="选择工作流"
            style="width: 100%"
          >
            <el-option v-for="w in workflowOptions" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <template v-else>
          <el-form-item label="模型">
            <el-select
              v-model="agentForm.model_id"
              clearable
              placeholder="选择模型"
              style="width: 100%"
            >
              <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="提示词">
            <el-select
              v-model="agentForm.prompt_id"
              clearable
              placeholder="选择提示词"
              style="width: 100%"
            >
              <el-option v-for="p in promptOptions" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="工具">
            <el-select
              v-model="agentForm.tool_ids"
              multiple
              filterable
              placeholder="选择工具"
              style="width: 100%"
            >
              <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="技能">
            <el-select
              v-model="agentForm.skill_ids"
              multiple
              filterable
              placeholder="绑定技能广场技能"
              style="width: 100%"
            >
              <el-option v-for="s in skillOptions" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="温度">
            <el-slider
              v-model="agentForm.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              style="width: 100%"
            />
          </el-form-item>
        </template>
        <el-form-item label="主题色">
          <el-color-picker v-model="agentForm.color" />
          <span class="color-hint">用于卡片头像底色</span>
        </el-form-item>
        <el-form-item label="Markdown">
          <el-switch v-model="agentForm.markdown" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="agentForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="agentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingAgent" @click="saveAgent">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分类弹窗 -->
    <el-dialog
      v-model="catDialogVisible"
      :title="editingCat ? '重命名分类' : '新建分类'"
      width="420px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="catForm.name" placeholder="分类名称" />
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
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search, MoreFilled, ChatDotRound, Edit, Delete } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import {
  getAiAgentList,
  createAiAgent,
  updateAiAgent,
  deleteAiAgent,
  getAgentCategoryList,
  createAgentCategory,
  updateAgentCategory,
  deleteAgentCategory,
} from "@/api/module_ai/agent";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getAiSkillList } from "@/api/module_ai/skill";

defineOptions({ name: "AiAgent" });

const router = useRouter();
const loading = ref(false);
const agents = ref<any[]>([]);
const categories = ref<any[]>([]);
const keyword = ref("");
const currentCategory = ref<number | null>(null);

const modelOptions = ref<{ id: number; name: string }[]>([]);
const promptOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string }[]>([]);
const workflowOptions = ref<{ id: number; name: string }[]>([]);
const skillOptions = ref<{ id: number; name: string }[]>([]);

const filteredAgents = computed(() => {
  let list = agents.value;
  if (currentCategory.value != null) {
    list = list.filter((a) => a.category_id === currentCategory.value);
  }
  if (keyword.value) {
    const k = keyword.value.toLowerCase();
    list = list.filter((a) => a.agent_name.toLowerCase().includes(k));
  }
  return list;
});

const loadData = async () => {
  loading.value = true;
  try {
    const [ar, cr, mr, pr, tr, wr, sr] = await Promise.all([
      getAiAgentList({}),
      getAgentCategoryList(),
      getAiModelList({}),
      getAiPromptList({}),
      getAiToolList({}),
      getAiWorkflowList(),
      getAiSkillList({}),
    ]);
    agents.value = ar.data?.data || [];
    categories.value = cr.data?.data || [];
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    promptOptions.value = (pr.data?.data || []).map((p: any) => ({ id: p.id, name: p.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
    workflowOptions.value = (wr.data?.data || []).map((w: any) => ({ id: w.id, name: w.name }));
    skillOptions.value = (sr.data?.data || []).map((s: any) => ({ id: s.id, name: s.name }));
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
};

function selectCategory(id: number | null) {
  currentCategory.value = id;
}

// ---------- 智能体 ----------
const agentDialogVisible = ref(false);
const savingAgent = ref(false);
const editingAgent = ref<any>();
const agentForm = reactive<any>({});

function openAgentDialog(a?: any) {
  editingAgent.value = a || undefined;
  if (a) {
    Object.assign(agentForm, {
      ...a,
      runMode: a.workflow_id ? "workflow" : "model",
      temperature: a.temperature ?? 0.7,
    });
  } else {
    Object.assign(agentForm, {
      agent_name: "",
      agent_role: "",
      category_id: null,
      runMode: "model",
      workflow_id: null,
      model_id: null,
      prompt_id: null,
      tool_ids: [],
      skill_ids: [],
      temperature: 0.7,
      color: "#409eff",
      markdown: true,
      enabled: true,
      order: 0,
    });
  }
  agentDialogVisible.value = true;
}

function onRunModeChange(mode: any) {
  const m = String(mode);
  if (m === "workflow") {
    agentForm.workflow_id = null;
  } else {
    agentForm.model_id = null;
    agentForm.prompt_id = null;
    agentForm.tool_ids = [];
  }
}

async function saveAgent() {
  if (!agentForm.agent_name) {
    ElMessage.warning("请填写智能体名称");
    return;
  }
  savingAgent.value = true;
  try {
    const payload: any = {
      agent_name: agentForm.agent_name,
      agent_role: agentForm.agent_role,
      category_id: agentForm.category_id,
      workflow_id: agentForm.runMode === "workflow" ? agentForm.workflow_id : null,
      model_id: agentForm.runMode === "model" ? agentForm.model_id : null,
      prompt_id: agentForm.runMode === "model" ? agentForm.prompt_id : null,
      tool_ids: agentForm.runMode === "model" ? agentForm.tool_ids : [],
      skill_ids: agentForm.runMode === "model" ? agentForm.skill_ids : [],
      temperature: agentForm.runMode === "model" ? agentForm.temperature : null,
      color: agentForm.color,
      markdown: agentForm.markdown,
      enabled: agentForm.enabled,
      order: agentForm.order || 0,
    };
    if (editingAgent.value) {
      await updateAiAgent(editingAgent.value.id, payload);
    } else {
      await createAiAgent(payload);
    }
    ElMessage.success("保存成功");
    agentDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    savingAgent.value = false;
  }
}

function runAgent(a: any) {
  router.push({ path: "/ai/chat", query: { agent_id: a.id } });
}

function deleteAgent(a: any) {
  ElMessageBox.confirm(`确定删除智能体「${a.agent_name}」吗？删除后不可恢复。`, "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiAgent([a.id]);
      ElMessage.success("删除成功");
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
}

// ---------- 分类 ----------
const catDialogVisible = ref(false);
const editingCat = ref<any>();
const catForm = reactive<{ name: string }>({ name: "" });

function openCategoryDialog(c?: any) {
  editingCat.value = c || undefined;
  catForm.name = c?.name || "";
  catDialogVisible.value = true;
}

async function saveCategory() {
  if (!catForm.name) {
    ElMessage.warning("请填写分类名称");
    return;
  }
  try {
    if (editingCat.value) {
      await updateAgentCategory(editingCat.value.id, { name: catForm.name });
    } else {
      await createAgentCategory({ name: catForm.name, parent_id: null, sort: 0 });
    }
    ElMessage.success("保存成功");
    catDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  }
}

function onCategoryCmd(c: any, cmd: string) {
  if (cmd === "edit") openCategoryDialog(c);
  else if (cmd === "delete") {
    ElMessageBox.confirm(`确定删除分类「${c.name}」吗？`, "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
      .then(async () => {
        await deleteAgentCategory(c.id);
        ElMessage.success("删除成功");
        if (currentCategory.value === c.id) currentCategory.value = null;
        loadData();
      })
      .catch(() => {
        /* 取消 */
      });
  }
}

onMounted(loadData);
</script>

<style scoped lang="scss">
.ai-agent-page {
  height: 100%;
}

.agent-category-card {
  height: 100%;
  :deep(.el-card__body) {
    padding: 12px;
  }
}

.category-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;

  .category-title {
    font-weight: 600;
  }
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 6px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);

  &:hover {
    background: var(--el-fill-color-light);
  }

  &.active {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  .category-more {
    visibility: hidden;
    font-size: 14px;
  }

  &:hover .category-more {
    visibility: visible;
  }
}

.agent-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.agent-card {
  margin-bottom: 12px;

  .agent-card__head {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .agent-avatar {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    color: #fff;
    font-size: 18px;
    border-radius: 10px;
  }

  .agent-card__meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .agent-card__name {
    font-size: var(--el-font-size-base);
    font-weight: 600;
  }

  .agent-card__role {
    margin: 10px 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    min-height: 34px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .agent-card__tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    min-height: 24px;
  }

  .agent-card__actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;

    :deep(.el-button + .el-button) {
      margin-left: 0;
    }
  }
}

.color-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
