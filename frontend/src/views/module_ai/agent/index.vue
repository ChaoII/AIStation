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
                <el-tag v-if="a.query_enabled" size="small" effect="plain" type="primary">
                  智能问数
                </el-tag>
                <el-tag
                  v-if="(a.knowledge_ids || []).length"
                  size="small"
                  effect="plain"
                  type="success"
                >
                  知识库
                </el-tag>
                <el-tag v-if="(a.tool_ids || []).length" size="small" effect="plain" type="warning">
                  {{ a.tool_ids.length }} 工具
                </el-tag>
                <el-tag
                  v-if="(a.skill_ids || []).length"
                  size="small"
                  effect="plain"
                  type="warning"
                >
                  技能
                </el-tag>
                <el-tag v-if="a.model_id" size="small" effect="plain">模型</el-tag>
                <el-tag v-if="a.prompt_id" size="small" effect="plain">提示词</el-tag>
                <el-tag v-if="a.workflow_id" size="small" effect="plain" type="primary">
                  工作流
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
                  v-hasPerm="['module_ai:agent:update']"
                  size="small"
                  :icon="SetUp"
                  @click="openStudio(a)"
                >
                  编排
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
      <!-- 左：会话历史 -->
      <div class="agent-chat-sidebar">
        <!-- 我的智能体（分组，可切换） -->
        <div class="agent-chat-agents-wrap">
          <div class="agent-chat-sidebar-title">我的智能体</div>
          <div class="agent-chat-agents">
            <template v-for="g in groupedAgentsChat" :key="g.cat?.id ?? -1">
              <div v-if="g.cat" class="agent-chat-agent-group-name">
                {{ g.cat.emoji || "📦" }} {{ g.cat.name }}（{{ g.items.length }}）
              </div>
              <div
                v-for="ag in g.items"
                :key="ag.id"
                class="agent-chat-agent-item"
                :class="{ 'agent-chat-agent-item--active': ag.id === activeChatAgent.id }"
                @click="switchChatAgent(ag)"
              >
                <div
                  class="agent-chat-agent-item-avatar"
                  :style="{ background: ag.color || '#667eea' }"
                >
                  {{ ag.agent_name?.slice(0, 1) }}
                </div>
                <div class="agent-chat-agent-item-name">{{ ag.agent_name }}</div>
              </div>
            </template>
            <div v-if="!agents.length" class="agent-chat-sess-empty">暂无智能体</div>
          </div>
        </div>
        <div class="agent-chat-sidebar-head">
          <span>会话</span>
          <el-button size="small" :icon="Plus" @click="newChatSession">新会话</el-button>
        </div>
        <div v-loading="chatLoadingSession" class="agent-chat-sessions">
          <div
            v-for="s in chatSessions"
            :key="s.id"
            class="agent-chat-sess"
            :class="{ 'agent-chat-sess--active': s.id === chatSessionId }"
            @click="openChatSession(s)"
          >
            <span class="agent-chat-sess-title">{{ s.title || "未命名会话" }}</span>
            <span class="agent-chat-sess-meta">
              <span class="agent-chat-sess-count">{{ s.message_count ?? 0 }}</span>
              <span class="agent-chat-sess-time">{{ fmtTime(s.updated_time) }}</span>
            </span>
          </div>
          <div v-if="!chatSessions.length" class="agent-chat-sess-empty">暂无会话</div>
        </div>
      </div>
      <!-- 右：对话主区 -->
      <div class="agent-chat-main">
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
                <div class="agent-chat-tools-title">执行链</div>
                <div class="agent-chat-tools-flow">
                  <template v-for="(t, ti) in m.tools" :key="t">
                    <span
                      class="agent-chat-tool"
                      :class="{
                        'agent-chat-tool--running': m.loading && ti === m.tools.length - 1,
                      }"
                    >
                      <el-icon class="agent-chat-tool__icon">
                        <component :is="toolIcon(t)" />
                      </el-icon>
                      {{ t }}
                    </span>
                    <i v-if="ti < m.tools.length - 1" class="agent-chat-tool-arrow">→</i>
                  </template>
                </div>
              </div>
              <div v-if="m.content" class="agent-chat-text" v-html="renderMd(m.content)"></div>
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
                <span class="cia-trigger-initial">
                  {{ chatModelLabel.charAt(0).toUpperCase() }}
                </span>
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
                    v-for="m in chatModels"
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
      <!-- /agent-chat-main -->
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

    <!-- P3-⑥ Agent Studio 无代码编排画布 -->
    <el-drawer
      v-model="studioVisible"
      :title="`Agent Studio · ${studioAgent?.agent_name || ''}`"
      size="760px"
      append-to-body
    >
      <div class="studio">
        <!-- 顶部：Agent 元信息 -->
        <div class="studio-top">
          <div class="studio-top__agent">
            <div
              class="studio-top__avatar"
              :style="{ background: studioAgent?.color || 'var(--el-color-primary)' }"
            >
              <el-icon><User /></el-icon>
            </div>
            <div class="studio-top__meta">
              <div class="studio-top__name">{{ studioAgent?.agent_name }}</div>
              <div class="studio-top__role">{{ studioAgent?.agent_role || "未设置角色描述" }}</div>
            </div>
            <el-tag size="small" :type="studioAgent?.enabled ? 'success' : 'info'" effect="plain">
              {{ studioAgent?.enabled ? "运行中" : "已停用" }}
            </el-tag>
          </div>
          <div class="studio-top__actions">
            <span class="studio-top__label">驱动模型</span>
            <el-select
              v-model="studioAgent.model_id"
              style="width: 200px"
              @change="studioDirty = true"
            >
              <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
            <el-switch
              v-model="studioAgent.enabled"
              inline-prompt
              active-text="启"
              inactive-text="停"
              @change="studioDirty = true"
            />
          </div>
        </div>

        <!-- 能力装配卡片 -->
        <div class="studio-section">
          <div class="studio-section__head">
            <div>
              <div class="studio-section__title">能力装配</div>
              <div class="studio-section__sub">为 Agent 勾选要具备的能力（可叠加）</div>
            </div>
            <el-tag size="small" type="info" effect="plain">
              已启用 {{ capList.filter((c) => c.on).length }} 项
            </el-tag>
          </div>
          <div class="studio-cap-grid">
            <div
              v-for="cap in capList"
              :key="cap.key"
              class="cap-card"
              :class="{ 'cap-card--on': cap.on }"
            >
              <div class="cap-card__head">
                <el-icon class="cap-card__icon"><component :is="cap.icon" /></el-icon>
                <span class="cap-card__name">{{ cap.name }}</span>
                <el-switch :model-value="cap.on" size="small" @change="toggleCap(cap.key)" />
              </div>
              <div class="cap-card__desc">{{ cap.desc }}</div>
              <div v-if="cap.on" class="cap-card__config">
                <el-select
                  v-if="cap.key === 'query'"
                  v-model="studioAgent.query_datasource"
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option label="系统数据" value="system" />
                  <el-option
                    v-for="d in queryDatasources"
                    :key="d.id"
                    :label="d.name"
                    :value="String(d.id)"
                  />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'knowledge'"
                  v-model="studioAgent.knowledge_ids"
                  multiple
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option
                    v-for="k in knowledgeOptions"
                    :key="k.id"
                    :label="k.name"
                    :value="k.id"
                  />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'tool'"
                  v-model="studioAgent.tool_ids"
                  multiple
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option
                    v-for="t in toolOptions"
                    :key="t.name"
                    :label="t.name"
                    :value="t.name"
                  />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'skill'"
                  v-model="studioAgent.skill_ids"
                  multiple
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option v-for="s in skillOptions" :key="s.id" :label="s.name" :value="s.id" />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'model'"
                  v-model="studioAgent.model_id"
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'prompt'"
                  v-model="studioAgent.prompt_id"
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option v-for="p in promptOptions" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
                <el-select
                  v-else-if="cap.key === 'workflow'"
                  v-model="studioAgent.workflow_id"
                  size="small"
                  style="width: 100%"
                  @change="studioDirty = true"
                >
                  <el-option
                    v-for="w in workflowOptions"
                    :key="w.id"
                    :label="w.name"
                    :value="w.id"
                  />
                </el-select>
              </div>
            </div>
          </div>
        </div>

        <!-- 装配流预览 -->
        <div class="studio-section">
          <div class="studio-section__head">
            <div>
              <div class="studio-section__title">装配流（Agent 运行时链路）</div>
              <div class="studio-section__sub">启用的能力将按顺序进入 Agent 的推理链路</div>
            </div>
          </div>
          <div class="studio-flow">
            <div class="pipe-node pipe-node--start">输入</div>
            <template v-for="cap in capOnList" :key="cap.key">
              <i class="pipe-arrow">→</i>
              <div class="pipe-node pipe-node--cap">
                <el-icon class="pipe-node__icon"><component :is="cap.icon" /></el-icon>
                {{ cap.name }}
              </div>
            </template>
            <i class="pipe-arrow">→</i>
            <div class="pipe-node pipe-node--end">输出</div>
          </div>
          <div v-if="!capOnList.length" class="studio-flow-empty">
            勾选左侧能力后，这里会生成 Agent 的装配流
          </div>
        </div>

        <!-- 试跑 -->
        <div class="studio-run">
          <div class="studio-run__bar">
            <el-input
              v-model="studioRunInput"
              placeholder="输入问题试跑，回放工具链…"
              :disabled="studioRunning"
              clearable
              @keyup.enter="runStudio"
            />
            <el-button type="primary" :icon="VideoPlay" :loading="studioRunning" @click="runStudio">
              试跑
            </el-button>
          </div>
          <div v-if="studioRunSteps.length" class="studio-run__trace">
            <div class="studio-run__trace-title">工具链回放</div>
            <div class="studio-run__trace-steps">
              <el-tag
                v-for="(s, i) in studioRunSteps"
                :key="i"
                size="small"
                :type="s.type || 'primary'"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                {{ i + 1 }}. {{ s.name }}
              </el-tag>
            </div>
          </div>
          <div v-if="studioRunReasoning" class="studio-run__reasoning">
            <div class="studio-run__trace-title">思考</div>
            <div class="studio-run__text">{{ studioRunReasoning }}</div>
          </div>
          <div v-if="studioRunText" class="studio-run__answer">
            <div class="studio-run__trace-title">回答</div>
            <div class="studio-run__text">{{ studioRunText }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="studioVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!studioDirty" @click="saveStudio">保存装配</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from "vue";
import MarkdownIt from "markdown-it";
const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
function renderMd(t: string) {
  return md.render(t || "");
}
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
  MagicStick,
  SetUp,
  VideoPlay,
  Cpu,
  Collection,
  Operation,
  DataAnalysis,
  Document,
  User,
  Connection,
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
import { getAiSessionList, getAiSessionDetail } from "@/api/module_ai/session";

defineOptions({ name: "AiAgent" });

const loading = ref(false);
const agents = ref<any[]>([]);
const categories = ref<any[]>([]);
const keyword = ref("");
const currentCategory = ref<number | null>(null);

const modelOptions = ref<{ id: number; name: string }[]>([]);
// 对话模型选择：仅展示 chat 用途的模型
const chatModels = ref<{ id: number; name: string }[]>([]);
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
    chatModels.value = (mr.data?.data || [])
      .filter((m: any) => (m.usage || m.type) === "chat")
      .map((m: any) => ({ id: m.id, name: m.name }));
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

// ---- P3-⑥ Agent Studio 无代码编排 ----
const studioVisible = ref(false);
const studioAgent = ref<any>(null);
const studioDirty = ref(false);
function openStudio(a: any) {
  // 深拷贝，避免污染原列表
  studioAgent.value = JSON.parse(JSON.stringify(a));
  studioDirty.value = false;
  studioVisible.value = true;
}
// 能力装配：Palantir AIP 风格能力卡片
const capList = computed(() => {
  const a = studioAgent.value;
  if (!a) return [];
  return [
    {
      key: "query",
      name: "智能问数",
      desc: "让 Agent 查询你的业务数据",
      icon: DataAnalysis,
      on: !!a.query_enabled,
    },
    {
      key: "knowledge",
      name: "知识库 RAG",
      desc: "检索知识库增强回答",
      icon: Collection,
      on: !!(a.knowledge_ids || []).length,
    },
    {
      key: "tool",
      name: "工具调用",
      desc: "调用平台工具 / 函数",
      icon: Operation,
      on: !!(a.tool_ids || []).length,
    },
    {
      key: "skill",
      name: "技能",
      desc: "装配技能广场技能",
      icon: MagicStick,
      on: !!(a.skill_ids || []).length,
    },
    { key: "model", name: "智能模型", desc: "选择 LLM 驱动", icon: Cpu, on: !!a.model_id },
    { key: "prompt", name: "提示词", desc: "绑定提示词模板", icon: Document, on: !!a.prompt_id },
    { key: "workflow", name: "工作流", desc: "绑定可视化工作流", icon: SetUp, on: !!a.workflow_id },
  ];
});
const capOnList = computed(() => capList.value.filter((c) => c.on));
function toggleCap(key: string) {
  const a = studioAgent.value;
  if (!a) return;
  const cur = capList.value.find((c) => c.key === key)?.on;
  if (cur) {
    // 关闭
    if (key === "query") a.query_enabled = false;
    else if (key === "knowledge") a.knowledge_ids = [];
    else if (key === "tool") a.tool_ids = [];
    else if (key === "skill") a.skill_ids = [];
    else if (key === "model") a.model_id = null;
    else if (key === "prompt") a.prompt_id = null;
    else if (key === "workflow") a.workflow_id = null;
  } else {
    // 打开（默认装配第一个）
    if (key === "query") {
      a.query_enabled = true;
      a.query_datasource = a.query_datasource || "system";
    } else if (key === "knowledge") {
      a.knowledge_ids = a.knowledge_ids || [];
      if (!a.knowledge_ids.length && knowledgeOptions.value[0])
        a.knowledge_ids.push(knowledgeOptions.value[0].id);
    } else if (key === "tool") {
      a.tool_ids = a.tool_ids || [];
      if (!a.tool_ids.length && toolOptions.value[0]) a.tool_ids.push(toolOptions.value[0].name);
    } else if (key === "skill") {
      a.skill_ids = a.skill_ids || [];
      if (!a.skill_ids.length && skillOptions.value[0]) a.skill_ids.push(skillOptions.value[0].id);
    } else if (key === "model") a.model_id = a.model_id || modelOptions.value[0]?.id || null;
    else if (key === "prompt") a.prompt_id = a.prompt_id || promptOptions.value[0]?.id || null;
    else if (key === "workflow")
      a.workflow_id = a.workflow_id || workflowOptions.value[0]?.id || null;
  }
  studioDirty.value = true;
}
async function saveStudio() {
  const a = studioAgent.value;
  if (!a) return;
  savingAgent.value = true;
  try {
    await updateAiAgent(a.id, {
      agent_name: a.agent_name,
      agent_role: a.agent_role,
      category_id: a.category_id,
      workflow_id: a.workflow_id || null,
      model_id: a.model_id || null,
      prompt_id: a.prompt_id || null,
      tool_ids: a.tool_ids || [],
      skill_ids: a.skill_ids || [],
      knowledge_ids: a.knowledge_ids || [],
      query_enabled: !!a.query_enabled,
      query_datasource: a.query_datasource || "system",
      enabled: a.enabled,
    });
    ElMessage.success("编排已保存");
    studioVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    savingAgent.value = false;
  }
}
// 试跑 / 工具链回放
const studioRunInput = ref("");
const studioRunSteps = ref<
  { name: string; type: "primary" | "success" | "warning" | "info" | "danger" }[]
>([]);
const studioRunReasoning = ref("");
const studioRunText = ref("");
const studioRunning = ref(false);
async function runStudio() {
  const a = studioAgent.value;
  const q = (studioRunInput.value || "").trim();
  if (!a || !q || studioRunning.value) return;
  studioRunSteps.value = [];
  studioRunReasoning.value = "";
  studioRunText.value = "";
  studioRunning.value = true;
  const token = JSON.parse(localStorage.getItem("access_token") || '"")');
  const base = import.meta.env.VITE_APP_BASE_API || "";
  try {
    const resp = await fetch(`${base}/ai/agents/${a.id}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json;charset=utf-8",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: q }],
        variables: null,
        session_id: null,
      }),
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
            handleStudioEvent(JSON.parse(payload));
          } catch {
            /* 忽略 */
          }
        }
        idx = buf.indexOf("\n\n");
      }
    }
  } catch (e: any) {
    studioRunText.value = studioRunText.value || `（试跑出错：${e?.message || "未知错误"}）`;
  } finally {
    studioRunning.value = false;
  }
}
function handleStudioEvent(evt: any) {
  const t = evt.type || "";
  if (t === "reasoning-delta") studioRunReasoning.value += evt.delta || "";
  else if (t === "text-delta") studioRunText.value += evt.delta || "";
  else if (t === "tool-input-available") {
    const n = evt.toolName || "工具";
    if (!studioRunSteps.value.some((x) => x.name === n)) {
      studioRunSteps.value.push({ name: n, type: "warning" });
    }
  } else if (t === "data-finish") {
    if (evt.data?.reply) studioRunText.value = studioRunText.value || evt.data.reply;
  }
}

// ---- 智能体内嵌对话（点击卡片，页内展开） ----
const activeChatAgent = ref<any>(null);
const chatMsgs = ref<any[]>([]);
const chatInput = ref("");
const chatSending = ref(false);
const chatConv = ref<any[]>([]);
const chatBodyRef = ref<HTMLDivElement>();
// 会话历史（左侧栏）
const chatSessions = ref<any[]>([]);
const chatSessionId = ref<number | null>(null);
const chatLoadingSession = ref(false);
// 对话工具栏选项（CherryStudio 风格：模型触发器 + 思考 pills + 上传/语音图标）
const chatModelId = ref<number | null>(null);
const chatModelOpen = ref(false);
const chatThinkMode = ref<"quick" | "deep">("quick");
const chatEffort = ref<string>("medium");
const chatVoice = ref<"none" | "auto">("none");
const chatFiles = ref<File[]>([]);
const chatModelRoot = ref<HTMLDivElement>();

const chatModelLabel = computed(() => {
  const m = chatModels.value.find((x: any) => x.id === chatModelId.value);
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
  loadChatSessions();
}
async function loadChatSessions() {
  chatLoadingSession.value = true;
  try {
    const r = await getAiSessionList({ app_id: activeChatAgent.value?.id || undefined });
    chatSessions.value = r.data?.data || [];
  } catch {
    chatSessions.value = [];
  } finally {
    chatLoadingSession.value = false;
  }
}
async function openChatSession(s: any) {
  if (!s?.id) return;
  chatSessionId.value = s.id;
  chatLoadingSession.value = true;
  try {
    const r = await getAiSessionDetail(s.id);
    const msgs = r.data?.data?.messages || [];
    chatMsgs.value = msgs.map((m: any) => {
      const text = (m.parts || []).map((p: any) => p.text || "").join("");
      return { role: m.role, content: text, think: "", tools: [] };
    });
    chatConv.value = [];
  } catch {
    chatMsgs.value = [];
  } finally {
    chatLoadingSession.value = false;
    chatScroll();
  }
}
async function newChatSession() {
  chatSessionId.value = null;
  chatMsgs.value = [];
  chatConv.value = [];
  await loadChatSessions();
}
// 左侧「我的智能体」分组
const groupedAgentsChat = computed(() => {
  const map = new Map<number, any[]>();
  const catMap = new Map(categories.value.map((c: any) => [c.id, c]));
  for (const a of agents.value) {
    const key = a.category_id ?? -1;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(a);
  }
  return [...map.entries()].map(([cid, list]) => ({
    cat: cid === -1 ? null : catMap.get(cid) || null,
    items: list,
  }));
});
function switchChatAgent(ag: any) {
  openAgentChat(ag);
}
// 会话更新时间格式化（相对时间）
function fmtTime(t: string | null | undefined) {
  if (!t) return "";
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const day = Math.floor(h / 24);
  if (day < 30) return `${day} 天前`;
  return `${d.getMonth() + 1}-${d.getDate()}`;
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
      body: JSON.stringify({
        messages: [...chatConv.value],
        variables: null,
        session_id: chatSessionId.value,
      }),
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
    loadChatSessions();
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
// 工具名 → 图标（能力节点可视化）
function toolIcon(name: string) {
  const n = (name || "").toLowerCase();
  if (n.includes("query")) return DataAnalysis;
  if (n.includes("resolve")) return Connection;
  if (n.includes("search") || n.includes("rag") || n.includes("knowledge")) return Collection;
  return Operation;
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
/* P3-⑥ Agent Studio（能力装配，Palantir AIP 风格） */
.studio {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.studio-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.studio-top__agent {
  display: flex;
  align-items: center;
  gap: 10px;
}
.studio-top__avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
}
.studio-top__name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.studio-top__role {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.studio-top__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.studio-top__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.studio-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.studio-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.studio-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.studio-section__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.studio-cap-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.cap-card {
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  padding: 12px;
  background: var(--el-fill-color-blank);
  transition: all 0.2s;
}
.cap-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 4px 12px rgba(31, 45, 61, 0.06);
}
.cap-card--on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.cap-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cap-card__icon {
  font-size: 18px;
  color: var(--el-text-color-secondary);
}
.cap-card--on .cap-card__icon {
  color: var(--el-color-primary);
}
.cap-card__name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.cap-card__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
  min-height: 30px;
}
.cap-card__config {
  margin-top: 8px;
}
.studio-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.pipe-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
}
.pipe-node--start {
  border-color: var(--el-color-success);
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.pipe-node--end {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.pipe-node--cap {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.pipe-node__icon {
  font-size: 14px;
}
.pipe-arrow {
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}
.studio-flow-empty {
  padding: 20px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
}
.studio-run {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.studio-run__bar {
  display: flex;
  gap: 8px;
}
.studio-run__trace {
  margin-top: 12px;
}
.studio-run__trace-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.studio-run__trace-steps {
  display: flex;
  flex-wrap: wrap;
}
.studio-run__reasoning,
.studio-run__answer {
  margin-top: 10px;
}
.studio-run__text {
  font-size: 13px;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  line-height: 1.6;
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
  height: calc(100vh - 210px);
  min-height: 460px;
}
.agent-chat-sidebar {
  width: 220px;
  min-width: 200px;
  background: var(--el-fill-color-lighter);
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
}
.agent-chat-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.agent-chat-agents-wrap {
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.agent-chat-sidebar-title {
  padding: 12px 14px 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--el-text-color-secondary);
}
.agent-chat-agents {
  max-height: 200px;
  overflow: auto;
  padding: 4px 8px 10px;
}
.agent-chat-agent-group-name {
  padding: 8px 6px 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.agent-chat-agent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.agent-chat-agent-item:hover {
  background: var(--el-fill-color);
}
.agent-chat-agent-item--active {
  background: var(--el-color-primary-light-9);
}
.agent-chat-agent-item-avatar {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.agent-chat-agent-item-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-chat-agent {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.agent-chat-agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #667eea, #764ba2);
}
.agent-chat-agent-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.agent-chat-agent-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-chat-sessions {
  flex: 1;
  overflow: auto;
  padding: 8px;
}
.agent-chat-sess {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.agent-chat-sess:hover {
  background: var(--el-fill-color);
}
.agent-chat-sess--active {
  background: var(--el-color-primary-light-9);
}
.agent-chat-sess-title {
  flex: 1;
  font-size: 13px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-chat-sess-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.agent-chat-sess-count {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  padding: 0 6px;
  border-radius: 8px;
}
.agent-chat-sess-time {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.agent-chat-sess-empty {
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  padding: 20px 0;
}
.agent-chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
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
  margin: 6px 0 10px;
}
.agent-chat-tools-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
  font-weight: 600;
}
.agent-chat-tools-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.agent-chat-tool {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
}
.agent-chat-tool__icon {
  font-size: 13px;
}
.agent-chat-tool--running {
  animation: agent-tool-pulse 1.2s ease-in-out infinite;
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.agent-chat-tool-arrow {
  color: var(--el-text-color-placeholder);
  font-style: normal;
  font-size: 13px;
}
@keyframes agent-tool-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
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
  padding-right: 88px; /* 让出发送按钮，避开右下角悬浮 AI 气泡 */
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
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 100;
  width: 240px;
  max-height: 360px;
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
