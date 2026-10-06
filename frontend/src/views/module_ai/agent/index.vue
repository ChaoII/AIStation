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

        <div class="agent-batchbar">
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="isIndeterminate"
            @change="toggleSelectAll"
          >
            全选
          </el-checkbox>
          <el-button size="small" :disabled="!agentSelIds.length" @click="batchAgent(true)">
            批量启用
          </el-button>
          <el-button size="small" :disabled="!agentSelIds.length" @click="batchAgent(false)">
            批量停用
          </el-button>
          <el-tag size="small" type="info" effect="plain" class="summary-tag">
            共 {{ agentSummary.total }} 个智能体 · 启用 {{ agentSummary.enabled }} · 停用
            {{ agentSummary.disabled }}
          </el-tag>
        </div>

        <el-row v-if="!activeChatAgent" v-loading="loading" :gutter="12">
          <el-col v-for="a in pagedAgents" :key="a.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
            <el-card shadow="hover" class="agent-card" :body-style="{ padding: '16px' }">
              <div class="agent-card__head">
                <el-checkbox
                  :model-value="isSelected(a)"
                  class="agent-card__check"
                  @change="toggleSelect(a)"
                />
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
                <el-button v-hasPerm="['module_ai:agent:query']" size="small" @click="viewAgent(a)">
                  详情
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
                  v-hasPerm="['module_ai:agent:create']"
                  size="small"
                  :icon="CopyDocument"
                  @click="copyAgent(a)"
                >
                  复制
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
            <el-empty description="暂无智能体，点击「新建智能体」创建" />
          </el-col>
        </el-row>

        <div v-if="!activeChatAgent && filteredAgents.length > 0" class="agent-pagination">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="filteredAgents.length"
            :page-sizes="[12, 24, 48]"
            layout="total, sizes, prev, pager, next"
            background
          />
        </div>
      </el-col>
    </el-row>

    <!-- 智能体内嵌对话面板（页内展开） -->
    <div v-if="activeChatAgent" class="agent-chat-panel">
      <div class="agent-chat-head">
        <button class="agent-chat-back" @click="closeAgentChat">返回列表</button>
        <div class="agent-chat-title">
          <div
            class="agent-chat-avatar"
            :style="{ background: activeChatAgent.color || '#409eff' }"
          >
            {{ activeChatAgent.agent_name?.slice(0, 1) }}
          </div>
          <div>
            <div class="agent-chat-name">{{ activeChatAgent.agent_name }}</div>
            <div class="agent-chat-sub">与智能体对话 · 自动检索知识库 / 问数 / 工具</div>
          </div>
        </div>
        <div class="agent-chat-head-right">
          <el-tag
            v-if="activeChatAgent.knowledge_ids?.length"
            size="small"
            type="success"
            effect="plain"
          >
            知识库
          </el-tag>
          <el-tag v-if="activeChatAgent.query_enabled" size="small" type="warning" effect="plain">
            问数
          </el-tag>
          <el-tag v-if="(activeChatAgent.tool_ids || []).length" size="small" effect="plain">
            {{ activeChatAgent.tool_ids.length }} 工具
          </el-tag>
        </div>
      </div>

      <div ref="chatBodyRef" class="agent-chat-body">
        <el-empty v-if="!chatMsgs.length" description="开始和智能体对话吧" :image-size="50" />
        <div v-for="(m, i) in chatMsgs" :key="i" class="agent-chat-msg" :class="m.role">
          <div v-if="m.role === 'user'" class="agent-chat-bubble user">{{ m.content }}</div>
          <div v-else class="agent-chat-bubble">
            <div v-if="m.think" class="agent-chat-think">
              <span class="agent-chat-think-title">思考过程</span>
              <div>{{ m.think }}</div>
            </div>
            <div v-if="m.tools.length" class="agent-chat-tools">
              <el-tag v-for="t in m.tools" :key="t" size="small" type="warning" effect="plain">
                🔧 {{ t }}
              </el-tag>
            </div>
            <div v-if="m.content" class="agent-chat-text">{{ m.content }}</div>
            <span v-if="m.loading" class="agent-chat-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              思考中…
            </span>
          </div>
        </div>
      </div>

      <!-- 对话输入区（CherryStudio 风格） -->
      <div class="agent-chat-composer">
        <div class="agent-composer-input">
          <el-input
            v-model="chatInput"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            :disabled="chatSending"
            @keyup.enter.exact.prevent="sendAgentChat"
          />
        </div>
        <div class="agent-composer-bar">
          <div class="agent-composer-left">
            <!-- 模型触发器 -->
            <div ref="chatModelRoot" class="cia-trigger" @click.stop="toggleModelDropdown">
              <span class="cia-trigger-initial">{{ chatModelLabel.charAt(0).toUpperCase() }}</span>
              <span class="cia-trigger-name">{{ chatModelLabel }}</span>
              <span
                class="cia-mode-badge"
                :class="{ 'cia-mode-badge--deep': chatThinkMode === 'deep' }"
              >
                {{ chatThinkMode === "deep" ? "🧠" : "⚡" }}
              </span>
              <span class="cia-chevron" :class="{ 'cia-chevron--open': chatModelOpen }">▾</span>
              <div v-if="chatModelOpen" class="cia-dropdown" @click.stop>
                <div class="cia-dropdown-title">模型</div>
                <div
                  v-for="m in modelOptions"
                  :key="m.id"
                  class="cia-model-opt"
                  :class="{ 'cia-model-opt--active': m.id === chatModelId }"
                  @click.stop="pickChatModel(m.id)"
                >
                  <span class="cia-model-opt-icon">{{ m.name.charAt(0).toUpperCase() }}</span>
                  <span class="cia-model-opt-label">{{ m.name }}</span>
                  <span v-if="m.id === chatModelId" class="cia-check">✓</span>
                </div>
                <div class="cia-dropdown-title">思考</div>
                <div class="cia-mode">
                  <button
                    type="button"
                    class="cia-mode-btn"
                    :class="{ 'cia-mode-btn--active': chatThinkMode === 'quick' }"
                    @click.stop="chatThinkMode = 'quick'"
                  >
                    ⚡ 快速
                  </button>
                  <button
                    type="button"
                    class="cia-mode-btn"
                    :class="{ 'cia-mode-btn--active': chatThinkMode === 'deep' }"
                    @click.stop="chatThinkMode = 'deep'"
                  >
                    🧠 深度
                  </button>
                </div>
                <div v-if="chatThinkMode === 'deep'" class="cia-effort">
                  <button
                    v-for="o in ['low', 'medium', 'high']"
                    :key="o"
                    type="button"
                    class="cia-effort-btn"
                    :class="{ 'cia-effort-btn--active': chatEffort === o }"
                    @click.stop="chatEffort = o"
                  >
                    {{ { low: "低", medium: "中", high: "高" }[o] }}
                  </button>
                </div>
              </div>
            </div>
            <!-- 语音合成 -->
            <button
              type="button"
              class="cia-icon-btn"
              :class="{ 'cia-icon-btn--on': chatVoice === 'auto' }"
              title="语音合成"
              @click="chatVoice = chatVoice === 'auto' ? 'none' : 'auto'"
            >
              🔊
            </button>
            <!-- 上传文件 -->
            <el-upload
              :show-file-list="false"
              multiple
              :auto-upload="false"
              :on-change="onChatFile"
            >
              <button type="button" class="cia-icon-btn" title="上传文件">📎</button>
            </el-upload>
            <el-tag v-if="chatFiles.length" size="small" type="info" effect="plain">
              {{ chatFiles.length }} 个文件
            </el-tag>
          </div>
          <el-button
            type="primary"
            class="agent-chat-send"
            :loading="chatSending"
            @click="sendAgentChat"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>

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
          <el-form-item label="知识库">
            <el-select
              v-model="agentForm.knowledge_ids"
              multiple
              filterable
              placeholder="绑定知识库（RAG）"
              style="width: 100%"
            >
              <el-option v-for="k in knowledgeOptions" :key="k.id" :label="k.name" :value="k.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="智能问数">
            <el-switch v-model="agentForm.query_enabled" />
            <span class="query-hint">启用后可回答基于系统数据的业务问题</span>
          </el-form-item>
          <el-form-item v-if="agentForm.query_enabled" label="问数数据源">
            <el-select v-model="agentForm.query_datasource" style="width: 100%">
              <el-option label="系统数据" value="system" />
              <el-option
                v-for="d in queryDatasources"
                :key="d.id"
                :label="d.name"
                :value="String(d.id)"
              />
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

    <!-- 智能体详情预览 -->
    <el-dialog
      v-model="detailVisible"
      :title="detail?.agent_name || '智能体'"
      width="560px"
      append-to-body
    >
      <el-descriptions v-if="detail" :column="2" border size="small">
        <el-descriptions-item label="名称" :span="2">{{ detail.agent_name }}</el-descriptions-item>
        <el-descriptions-item label="角色" :span="2">
          {{ detail.agent_role || "—" }}
        </el-descriptions-item>
        <el-descriptions-item label="运行方式">
          {{ detail.workflow_id ? "工作流" : "模型+提示词" }}
        </el-descriptions-item>
        <el-descriptions-item label="启用">
          <el-tag size="small" :type="detail.enabled ? 'success' : 'info'">
            {{ detail.enabled ? "启用" : "停用" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型">
          {{ modelName(detail.model_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="温度">{{ detail.temperature ?? "—" }}</el-descriptions-item>
        <el-descriptions-item v-if="detail.workflow_id" label="工作流" :span="2">
          {{ workflowName(detail.workflow_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="工具数" :span="2">
          {{ (detail.tool_ids || []).length }}
        </el-descriptions-item>
        <el-descriptions-item label="技能数" :span="2">
          {{ (detail.skill_ids || []).length }}
        </el-descriptions-item>
        <el-descriptions-item label="知识库数" :span="2">
          {{ (detail.knowledge_ids || []).length }}
        </el-descriptions-item>
        <el-descriptions-item label="Markdown" :span="2">
          {{ detail.markdown ? "是" : "否" }}
        </el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">运行调试</el-divider>
      <div class="agent-run">
        <div class="agent-run__input">
          <el-input
            v-model="runQuery"
            placeholder="输入问题，调试智能体（Enter 发送）"
            @keyup.enter="runDebug"
          />
          <el-button type="primary" :loading="runLoading" @click="runDebug">发送</el-button>
        </div>
        <div v-loading="runLoading" class="agent-run__output">
          <template v-if="runAnswer">
            <div v-for="(l, i) in runAnswer" :key="i" class="agent-run__line">
              <el-tag v-if="l.kind === 'tool'" size="small" type="warning">工具</el-tag>
              <el-tag v-else-if="l.kind === 'error'" size="small" type="danger">错误</el-tag>
              <span class="agent-run__text">{{ l.text }}</span>
            </div>
          </template>
          <el-empty v-else description="输入问题开始调试" :image-size="50" />
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
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
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Plus,
  Search,
  MoreFilled,
  ChatDotRound,
  Edit,
  Delete,
  CopyDocument,
  Loading,
} from "@element-plus/icons-vue";
import { Auth } from "@/utils/auth";
import {
  getAiAgentList,
  createAiAgent,
  updateAiAgent,
  deleteAiAgent,
  getAgentCategoryList,
  createAgentCategory,
  updateAgentCategory,
  deleteAgentCategory,
  batchAgentStatus,
} from "@/api/module_ai/agent";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getAiSkillList } from "@/api/module_ai/skill";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { getQueryDatasources } from "@/api/module_ai/query";

defineOptions({ name: "AiAgent" });

const loading = ref(false);
const agents = ref<any[]>([]);
const categories = ref<any[]>([]);
const keyword = ref("");
const currentCategory = ref<number | null>(null);

const modelOptions = ref<{ id: number; name: string }[]>([]);
const promptOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string }[]>([]);
const queryDatasources = ref<any[]>([]);
const workflowOptions = ref<{ id: number; name: string }[]>([]);
const skillOptions = ref<{ id: number; name: string }[]>([]);
const knowledgeOptions = ref<{ id: number; name: string }[]>([]);

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

// ---- 分页 ----
const page = ref(1);
const pageSize = ref(12);
const pagedAgents = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredAgents.value.slice(start, start + pageSize.value);
});

// ---- 批量选择 / 启停 ----
const agentSelIds = ref<number[]>([]);
const agentSelSet = computed(() => new Set(agentSelIds.value));
function isSelected(a: any) {
  return agentSelSet.value.has(a.id);
}
function toggleSelect(a: any) {
  agentSelIds.value = agentSelIds.value.includes(a.id)
    ? agentSelIds.value.filter((id) => id !== a.id)
    : [...agentSelIds.value, a.id];
}
const allSelected = computed(() => {
  const ids = filteredAgents.value.map((a) => a.id);
  return ids.length > 0 && ids.every((id) => agentSelSet.value.has(id));
});
const isIndeterminate = computed(() => {
  const ids = filteredAgents.value.map((a) => a.id);
  const n = ids.filter((id) => agentSelSet.value.has(id)).length;
  return n > 0 && n < ids.length;
});
function toggleSelectAll(checked: boolean | string | number) {
  if (checked) {
    const ids = filteredAgents.value.map((a) => a.id);
    agentSelIds.value = Array.from(new Set([...agentSelIds.value, ...ids]));
  } else {
    const pageIds = new Set(filteredAgents.value.map((a) => a.id));
    agentSelIds.value = agentSelIds.value.filter((id) => !pageIds.has(id));
  }
}

// ---- 统计摘要 ----
const agentSummary = ref({ total: 0, enabled: 0, disabled: 0 });
async function batchAgent(enabled: boolean) {
  if (!agentSelIds.value.length) return;
  try {
    const r = await batchAgentStatus(agentSelIds.value, enabled);
    ElMessage.success(`已${enabled ? "启用" : "停用"} ${r.data?.data?.count || 0} 个智能体`);
    agentSelIds.value = [];
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
}

// 切换分类/关键字时回到第一页
watch([currentCategory, keyword], () => {
  page.value = 1;
});

const loadData = async () => {
  loading.value = true;
  try {
    const [ar, cr, mr, pr, tr, wr, sr, kr, dr] = await Promise.all([
      getAiAgentList({}),
      getAgentCategoryList(),
      getAiModelList({}),
      getAiPromptList({}),
      getAiToolList({}),
      getAiWorkflowList(),
      getAiSkillList({}),
      getAiKnowledgeList(),
      getQueryDatasources(),
    ]);
    agents.value = ar.data?.data || [];
    categories.value = cr.data?.data || [];
    agentSummary.value = {
      total: agents.value.length,
      enabled: agents.value.filter((x: any) => x.enabled).length,
      disabled: agents.value.filter((x: any) => !x.enabled).length,
    };
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    promptOptions.value = (pr.data?.data || []).map((p: any) => ({ id: p.id, name: p.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
    workflowOptions.value = (wr.data?.data || []).map((w: any) => ({ id: w.id, name: w.name }));
    skillOptions.value = (sr.data?.data || []).map((s: any) => ({ id: s.id, name: s.name }));
    knowledgeOptions.value = (kr.data?.data || []).map((k: any) => ({ id: k.id, name: k.name }));
    queryDatasources.value = dr.data?.data || [];
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
      knowledge_ids: [],
      query_enabled: false,
      query_datasource: "system",
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
      knowledge_ids: agentForm.runMode === "model" ? agentForm.knowledge_ids : [],
      query_enabled: agentForm.runMode === "model" ? agentForm.query_enabled : false,
      query_datasource:
        agentForm.runMode === "model" ? agentForm.query_datasource || "system" : "system",
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
  openAgentChat(a);
}

// ---- 智能体内嵌对话（点击卡片，页内展开） ----
const activeChatAgent = ref<any>(null);
const chatMsgs = ref<any[]>([]);
const chatInput = ref("");
const chatSending = ref(false);
const chatConv = ref<any[]>([]);
const chatBodyRef = ref<HTMLDivElement>();
// 对话工具栏选项（CherryStudio 风格：模型触发器 + 思考 pills + 上传/语音图标）
const chatModelId = ref<number | null>(null);
const chatModelOpen = ref(false);
const chatThinkMode = ref<"quick" | "deep">("quick");
const chatEffort = ref<string>("medium");
const chatVoice = ref<"none" | "auto">("none");
const chatFiles = ref<File[]>([]);
const chatModelRoot = ref<HTMLDivElement>();

const chatModelLabel = computed(() => {
  const m = modelOptions.value.find((x: any) => x.id === chatModelId.value);
  return m ? m.name : "选择模型";
});
function openAgentChat(a: any) {
  activeChatAgent.value = a;
  chatMsgs.value = [];
  chatConv.value = [];
  chatInput.value = "";
  chatFiles.value = [];
  chatModelId.value = a.model_id || null;
  chatThinkMode.value = "quick";
  chatEffort.value = "medium";
}
function toggleModelDropdown() {
  chatModelOpen.value = !chatModelOpen.value;
}
function pickChatModel(id: number) {
  chatModelId.value = id;
  chatModelOpen.value = false;
}
function onDocClickChat(e: Event) {
  if (!chatModelRoot.value?.contains(e.target as Node)) chatModelOpen.value = false;
}
function closeAgentChat() {
  activeChatAgent.value = null;
  chatMsgs.value = [];
  chatSending.value = false;
}
function chatScroll() {
  requestAnimationFrame(() => {
    chatBodyRef.value?.scrollTo({ top: chatBodyRef.value.scrollHeight });
  });
}
function onChatFile(files: any) {
  chatFiles.value = (files || []).slice(0, 3);
}
async function sendAgentChat() {
  const text = (chatInput.value || "").trim();
  if (!text || chatSending.value) return;
  chatInput.value = "";
  chatMsgs.value.push({ role: "user", content: text });
  chatConv.value.push({ role: "user", content: text });
  const asst = { role: "assistant", content: "", think: "", tools: [] as string[], loading: true };
  chatMsgs.value.push(asst);
  chatSending.value = true;
  chatScroll();
  const token = JSON.parse(localStorage.getItem("access_token") || '"")');
  const base = import.meta.env.VITE_APP_BASE_API || "";
  try {
    const resp = await fetch(`${base}/ai/agents/${activeChatAgent.value.id}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json;charset=utf-8",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages: [...chatConv.value], variables: null }),
    });
    if (!resp.ok || !resp.body) throw new Error(`请求失败：${resp.status}`);
    const reader = resp.body.getReader();
    const dec = new TextDecoder("utf-8");
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx = buf.indexOf("\n\n");
      while (idx >= 0) {
        const block = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (block.startsWith("data: ")) {
          const payload = block.slice(6).trim();
          if (payload === "[DONE]") break;
          try {
            handleChatEvent(JSON.parse(payload), asst);
          } catch {
            /* 忽略 */
          }
        }
        idx = buf.indexOf("\n\n");
      }
    }
  } catch (e: any) {
    asst.content = asst.content || `（出错了：${e?.message || "未知错误"}）`;
  } finally {
    asst.loading = false;
    chatSending.value = false;
    chatScroll();
  }
}
function handleChatEvent(evt: any, asst: any) {
  const t = evt.type || "";
  if (t === "reasoning-delta") asst.think += evt.delta || "";
  else if (t === "text-delta") asst.content += evt.delta || "";
  else if (t === "tool-input-available") {
    asst.tools.push(evt.toolName || "工具");
    chatScroll();
  } else if (t === "data-finish") {
    if (evt.data?.reply) asst.content = asst.content || evt.data.reply;
  }
  if (t === "text-delta" || t === "reasoning-delta") chatScroll();
}

// ---- 详情 / 复制 ----
const detailVisible = ref(false);
const detail = ref<any>(null);
function viewAgent(a: any) {
  detail.value = a;
  detailVisible.value = true;
}

const runQuery = ref("");
const runAnswer = ref<{ kind: string; text: string }[]>([]);
const runLoading = ref(false);
async function runDebug() {
  if (!detail.value || !runQuery.value.trim()) return;
  runLoading.value = true;
  runAnswer.value = [];
  try {
    const resp = await fetch(`/api/v1/ai/agents/${detail.value.id}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken()}`,
      },
      body: JSON.stringify({ messages: [{ role: "user", content: runQuery.value }] }),
    });
    if (!resp.ok || !resp.body) throw new Error("请求失败");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        const s = line.trim();
        if (!s.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(s.slice(6));
          if (evt.type === "text-delta") {
            const last = runAnswer.value[runAnswer.value.length - 1];
            if (last && last.kind === "text") last.text += evt.delta || "";
            else runAnswer.value.push({ kind: "text", text: evt.delta || "" });
          } else if (evt.type === "text") {
            runAnswer.value.push({ kind: "text", text: evt.text || "" });
          } else if (evt.type === "tool") {
            runAnswer.value.push({
              kind: "tool",
              text: `${evt.name || "工具"}：${JSON.stringify(evt.args || {})}`,
            });
          } else if (evt.type === "error") {
            runAnswer.value.push({ kind: "error", text: evt.error || evt.message || "" });
          } else if (evt.type === "finish" && evt.payload?.reply) {
            runAnswer.value.push({ kind: "text", text: evt.payload.reply });
          }
        } catch {
          /* 忽略非 JSON */
        }
      }
    }
  } catch (e: any) {
    runAnswer.value.push({ kind: "error", text: `运行失败：${e?.message || e}` });
  } finally {
    runLoading.value = false;
  }
}
function modelName(id: number | null) {
  if (!id) return "默认";
  return detail.value?.model_name || `#${id}`;
}
function workflowName(id: number | null) {
  if (!id) return "—";
  return detail.value?.workflow_name || `#${id}`;
}
async function copyAgent(a: any) {
  try {
    await createAiAgent({
      agent_name: `${a.agent_name}（副本）`,
      agent_role: a.agent_role,
      category_id: a.category_id,
      workflow_id: a.workflow_id,
      model_id: a.model_id,
      prompt_id: a.prompt_id,
      tool_ids: a.tool_ids || [],
      skill_ids: a.skill_ids || [],
      knowledge_ids: a.knowledge_ids || [],
      temperature: a.temperature,
      color: a.color,
      markdown: a.markdown,
      enabled: a.enabled,
      order: 0,
    });
    ElMessage.success("已复制智能体");
    loadData();
  } catch {
    ElMessage.error("复制失败");
  }
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

onMounted(() => {
  loadData();
  document.addEventListener("click", onDocClickChat);
});
onBeforeUnmount(() => document.removeEventListener("click", onDocClickChat));
</script>

<style scoped lang="scss">
.ai-agent-page {
  height: 100%;
}
.query-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-base);
}
.agent-chat-panel {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(31, 45, 61, 0.06);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 210px);
  min-height: 460px;
}
.agent-chat-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: linear-gradient(120deg, var(--el-color-primary) 0%, #6a7ff7 100%);
  color: #fff;
}
.agent-chat-back {
  border: none;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}
.agent-chat-back:hover {
  background: rgba(255, 255, 255, 0.3);
}
.agent-chat-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}
.agent-chat-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
}
.agent-chat-name {
  font-size: 16px;
  font-weight: 700;
}
.agent-chat-sub {
  font-size: 12px;
  opacity: 0.9;
  margin-top: 2px;
}
.agent-chat-head-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.agent-chat-body {
  flex: 1;
  overflow: auto;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--el-bg-color-page);
}
.agent-chat-msg {
  display: flex;
  flex-direction: column;
}
.agent-chat-msg.user {
  align-items: flex-end;
}
.agent-chat-bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 14px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 2px 8px rgba(31, 45, 61, 0.04);
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
}
.agent-chat-bubble.user {
  background: var(--el-color-primary);
  color: #fff;
  border: none;
  border-bottom-right-radius: 4px;
}
.agent-chat-bubble:not(.user) {
  border-bottom-left-radius: 4px;
}
.agent-chat-think {
  margin-bottom: 8px;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  border-radius: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  white-space: pre-wrap;
  border-left: 3px solid var(--el-color-primary);
}
.agent-chat-think-title {
  color: var(--el-color-primary);
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}
.agent-chat-tools {
  margin: 6px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.agent-chat-text {
  line-height: 1.7;
}
.agent-chat-loading {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.agent-chat-composer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 10px 14px 12px;
  background: var(--el-bg-color);
}
.agent-composer-input .el-textarea__inner {
  border-radius: 14px;
  box-shadow: none;
  font-size: var(--el-font-size-base);
  line-height: 1.6;
}
.agent-composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
}
.agent-composer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-chat-send {
  border-radius: 12px;
  padding: 9px 24px;
}
/* ---------- CherryStudio 风格：模型触发器 + 下拉 ---------- */
.cia-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-regular);
  transition: all 0.15s;
}
.cia-trigger:hover {
  border-color: var(--el-color-primary);
}
.cia-trigger-initial {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-fill-color-dark, #e8e6e1);
  color: var(--el-text-color-secondary);
  font-size: 10px;
  font-weight: 700;
}
.cia-trigger-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cia-mode-badge {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 6px;
  background: var(--el-fill-color-dark, #e8e6e1);
}
.cia-mode-badge--deep {
  background: var(--el-color-primary-light-8);
}
.cia-chevron {
  font-size: 10px;
  color: var(--el-text-color-secondary);
  transition: transform 0.15s;
}
.cia-chevron--open {
  transform: rotate(180deg);
}
.cia-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 100;
  width: 240px;
  max-height: 420px;
  overflow: auto;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  box-shadow: 0 12px 30px rgba(31, 45, 61, 0.1);
  padding: 6px;
}
.cia-dropdown-title {
  padding: 8px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--el-text-color-secondary);
}
.cia-model-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.cia-model-opt:hover {
  background: var(--el-fill-color-light);
}
.cia-model-opt--active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.cia-model-opt-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-fill-color-dark, #e8e6e1);
  color: var(--el-text-color-secondary);
  font-size: 10px;
  font-weight: 700;
}
.cia-model-opt-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cia-check {
  font-weight: 700;
}
.cia-mode {
  display: flex;
  gap: 6px;
  padding: 4px 8px 8px;
}
.cia-mode-btn {
  flex: 1;
  padding: 6px 0;
  font-size: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.cia-mode-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.cia-mode-btn--active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  font-weight: 600;
}
.cia-effort {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 8px 10px;
}
.cia-effort-btn {
  padding: 4px 12px;
  font-size: 11.5px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.cia-effort-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.cia-effort-btn--active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  font-weight: 600;
}
.cia-icon-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 50%;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}
.cia-icon-btn:hover {
  border-color: var(--el-color-primary);
}
.cia-icon-btn--on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
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

.agent-batchbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.agent-card__check {
  flex-shrink: 0;
}

.summary-tag {
  margin-left: 4px;
}

.agent-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
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
.agent-run__input {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.agent-run__output {
  min-height: 160px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
}
.agent-run__line {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  margin-bottom: 6px;
}
.agent-run__text {
  line-height: 1.7;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  word-break: break-word;
  white-space: pre-wrap;
}
</style>
