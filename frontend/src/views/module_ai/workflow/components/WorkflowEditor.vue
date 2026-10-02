<!-- AI 工作流编排编辑器：左节点面板 / 中画布 / 右属性面板，支持运行调试 -->
<template>
  <el-drawer
    v-model="dialogVisible"
    :title="workflow ? '编辑工作流' : '新建工作流'"
    size="88%"
    class="ai-workflow-editor"
    destroy-on-close
  >
    <div class="wf-editor">
      <el-splitter direction="horizontal" style="height: 100%">
        <!-- 左侧：基础信息 + 节点面板 -->
        <el-splitter-panel size="240px" :min="200" :max="340">
          <el-scrollbar style="height: 100%">
            <div class="panel-section">
              <div class="section-title">基础信息</div>
              <el-form :model="formData" label-position="top" size="small">
                <el-form-item label="名称" required>
                  <el-input v-model="formData.name" placeholder="工作流名称" />
                </el-form-item>
                <el-form-item label="描述">
                  <el-input
                    v-model="formData.description"
                    type="textarea"
                    :rows="2"
                    placeholder="描述"
                  />
                </el-form-item>
                <el-form-item label="快速模板">
                  <el-dropdown trigger="click" style="width: 100%" @command="applyTemplateByKey">
                    <el-button size="small" :icon="MagicStick" style="width: 100%">
                      一键生成工作流
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item
                          v-for="tpl in WF_TEMPLATES"
                          :key="tpl.key"
                          :command="tpl.key"
                        >
                          <div class="tpl-menu">
                            <span>{{ tpl.name }}</span>
                            <span class="tpl-menu__desc">{{ tpl.desc }}</span>
                          </div>
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </el-form-item>
              </el-form>
            </div>
            <el-divider style="margin: 4px 0" />
            <div class="panel-section">
              <div class="section-title">节点</div>
              <div class="palette-tip">点击或拖拽节点到画布</div>
              <el-input
                v-model="paletteQuery"
                size="small"
                placeholder="搜索节点"
                clearable
                :prefix-icon="Search"
                class="palette-search"
              />
              <div v-for="cat in NODE_CATEGORIES" :key="cat.key" class="palette-group">
                <div class="palette-group__title">{{ cat.label }}</div>
                <el-space direction="vertical" :size="8" fill style="width: 100%">
                  <div
                    v-for="def in filteredPalette(cat.key)"
                    :key="def.type"
                    class="palette-item"
                    draggable="true"
                    @dragstart="onDragStart($event, def.type)"
                    @click="onPaletteClick(def.type)"
                  >
                    <el-icon :color="def.color"><component :is="iconOf(def.type)" /></el-icon>
                    <span>{{ def.label }}</span>
                    <span class="palette-item__desc">{{ def.desc }}</span>
                  </div>
                </el-space>
              </div>
            </div>
          </el-scrollbar>
        </el-splitter-panel>

        <!-- 中间：画布 -->
        <el-splitter-panel>
          <div class="canvas-main">
            <div class="canvas-container" @click="handleCanvasClick">
              <VueFlow
                v-model:nodes="nodes"
                v-model:edges="edges"
                :node-types="nodeTypes"
                :default-viewport="{ zoom: 1.2 }"
                :min-zoom="0.2"
                :max-zoom="4"
                :snap-to-grid="true"
                :snap-grid="[16, 16]"
                :default-edge-options="defaultEdgeOptions"
                @node-click="onNodeClick"
                @drop="onDrop"
                @dragover="onDragOver"
                @node-drag-start="onNodeDragStart"
                @node-drag-stop="onNodeDragStop"
              >
                <Controls />
                <Background pattern-color="#aaa" :gap="16" />
                <MiniMap pannable zoomable />
                <Panel position="top-right" class="wf-toolbar">
                  <el-button size="small" :icon="RefreshLeft" :disabled="!canUndo" @click="undo">
                    撤销
                  </el-button>
                  <el-button size="small" :icon="RefreshRight" :disabled="!canRedo" @click="redo">
                    重做
                  </el-button>
                  <el-button size="small" :icon="FullScreen" @click="fitView()">适配视图</el-button>
                  <el-button size="small" :icon="Promotion" @click="autoLayout">自动布局</el-button>
                  <el-button
                    size="small"
                    :icon="Clock"
                    :disabled="!workflowId"
                    @click="openVersions"
                  >
                    版本
                  </el-button>
                  <el-button
                    size="small"
                    :icon="Tickets"
                    :disabled="!workflowId"
                    @click="openRunHistory"
                  >
                    历史
                  </el-button>
                  <el-button size="small" :icon="Download" @click="handleExport">导出</el-button>
                  <el-button size="small" :icon="Upload" @click="triggerImport">导入</el-button>
                  <el-button size="small" :icon="VideoPlay" type="success" @click="openRun">
                    运行
                  </el-button>
                </Panel>
                <Panel position="bottom-center" class="wf-hint">
                  操作：左侧点选/拖拽添加节点 → 点击节点在右侧编辑 → 拖动节点圆点连线 →
                  <el-button link type="primary" size="small" @click="fitView()">
                    适配视图
                  </el-button>
                </Panel>
              </VueFlow>
            </div>
          </div>
        </el-splitter-panel>

        <!-- 右侧：节点属性 -->
        <el-splitter-panel v-if="selectedNode" size="320px" :min="280" :max="420">
          <el-scrollbar style="height: 100%">
            <div class="panel-section">
              <div class="section-title">
                节点：{{ nodeDefOf(selectedNode.type || "llm").label }}
                <el-button
                  link
                  type="primary"
                  size="small"
                  style="float: right; margin-right: 8px"
                  @click="openNodeDebug"
                >
                  调试此节点
                </el-button>
                <el-button
                  link
                  type="primary"
                  size="small"
                  style="float: right; margin-right: 8px"
                  @click="copySelectedNode"
                >
                  复制
                </el-button>
                <el-button
                  link
                  type="danger"
                  size="small"
                  style="float: right"
                  @click="handleDeleteNode"
                >
                  删除
                </el-button>
              </div>
              <NodeConfigPanel
                :node="selectedNode"
                :available-vars="availableVars"
                :var-sources="varSources"
                :node-chain="nodeChain"
                @change="onNodeConfigChange"
              />
            </div>
          </el-scrollbar>
        </el-splitter-panel>
      </el-splitter>
    </div>

    <template #footer>
      <div class="wf-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存工作流</el-button>
      </div>
    </template>

    <!-- 运行调试抽屉（对话式 + 节点执行详情） -->
    <el-drawer
      v-model="runVisible"
      title="工作流运行"
      size="520px"
      class="ai-run-drawer"
      append-to-body
      destroy-on-close
    >
      <div class="chat-panel">
        <div ref="runListRef" class="chat-list">
          <div v-if="!chatMessages.length" class="chat-empty">
            输入消息开始测试工作流；每次运行都会展示每个节点的执行结果，点击可查看输入/输出/报错详情。
          </div>
          <div v-for="m in chatMessages" :key="m.id" class="chat-msg" :class="`is-${m.role}`">
            <div class="chat-msg__bubble">
              <div v-if="m.role === 'user'" class="chat-msg__user">{{ m.content }}</div>
              <template v-else>
                <div v-if="m.running" class="chat-msg__load">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  执行中…
                </div>
                <div v-else-if="m.error" class="chat-msg__err">{{ m.error }}</div>
                <div v-else class="chat-msg__ai">{{ m.content || "(无输出)" }}</div>

                <div v-if="m.sources?.length" class="chat-sources">
                  <div class="chat-sub-title">引用来源</div>
                  <el-card
                    v-for="(s, si) in m.sources"
                    :key="si"
                    class="run-source-card"
                    shadow="never"
                  >
                    <div class="run-source-card__head">
                      <el-icon><Document /></el-icon>
                      <span class="run-source-card__title">{{ s.title }}</span>
                      <el-tag v-if="s.score != null" size="small" type="info">
                        相似度 {{ s.score }}
                      </el-tag>
                    </div>
                    <div class="run-source-card__content">{{ s.content }}</div>
                  </el-card>
                </div>

                <!-- HITL 工具审批 -->
                <div v-if="m.approval" class="run-approval">
                  <div class="run-approval__list">
                    <div
                      v-for="t in m.approval.toolCalls"
                      :key="t.toolCallId"
                      class="run-approval__item"
                    >
                      <div class="run-approval__name">
                        <el-icon><Tools /></el-icon>
                        <span>{{ t.toolName }}</span>
                      </div>
                      <pre class="run-approval__args">{{
                        JSON.stringify(t.arguments, null, 2)
                      }}</pre>
                    </div>
                  </div>
                  <div class="run-approval__actions">
                    <el-button
                      type="success"
                      size="small"
                      :loading="approving"
                      @click="handleApprove('approve')"
                    >
                      允许执行
                    </el-button>
                    <el-button
                      type="danger"
                      size="small"
                      :loading="approving"
                      @click="handleApprove('reject')"
                    >
                      拒绝执行
                    </el-button>
                  </div>
                  <div class="run-approval__hint">
                    审批会话约 30 分钟内有效，超时后需重新运行工作流。
                  </div>
                </div>

                <!-- 节点执行过程 -->
                <div v-if="m.trace?.length" class="chat-trace">
                  <div class="chat-sub-title">节点执行过程（点击查看详情）</div>
                  <div
                    v-for="(t, i) in m.trace"
                    :key="i"
                    class="trace-item"
                    :class="`is-${t.status}`"
                  >
                    <div class="trace-item__head" @click="toggleTraceOpen(m.id + '_' + i)">
                      <span class="trace-item__chev">
                        {{ traceOpen[m.id + "_" + i] ? "▾" : "▸" }}
                      </span>
                      <span class="trace-item__dot" />
                      <span class="trace-item__label">{{ t.label }}</span>
                      <span class="trace-item__status">{{ statusText(t.status) }}</span>
                      <span v-if="t.error" class="trace-item__err">{{ t.error }}</span>
                    </div>
                    <div v-if="traceOpen[m.id + '_' + i]" class="trace-item__detail">
                      <div v-if="t.input && Object.keys(t.input).length" class="trace-item__kv">
                        <div class="kv-t">
                          输入
                          <el-button
                            link
                            size="small"
                            class="kv-copy"
                            @click.stop="copyText(formatJson(t.input))"
                          >
                            复制
                          </el-button>
                        </div>
                        <pre class="kv-b">{{ formatJson(t.input) }}</pre>
                      </div>
                      <div v-if="t.output != null" class="trace-item__kv">
                        <div class="kv-t">
                          输出
                          <el-button
                            link
                            size="small"
                            class="kv-copy"
                            @click.stop="copyText(formatJson(t.output))"
                          >
                            复制
                          </el-button>
                        </div>
                        <pre class="kv-b">{{ formatJson(t.output) }}</pre>
                      </div>
                      <div v-if="t.error" class="trace-item__kv">
                        <div class="kv-t">
                          错误
                          <el-button
                            link
                            size="small"
                            class="kv-copy"
                            @click.stop="copyText(t.error)"
                          >
                            复制
                          </el-button>
                        </div>
                        <pre class="kv-b is-err">{{ t.error }}</pre>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>

        <div class="chat-input">
          <el-collapse v-model="chatVarsOpen" class="chat-vars">
            <el-collapse-item title="输入变量（JSON，可选）" name="vars">
              <el-input
                v-model="runVariables"
                type="textarea"
                :rows="3"
                placeholder='如 {"query":"你好", "items":[1,2,3]}'
              />
            </el-collapse-item>
          </el-collapse>
          <div class="chat-input__row">
            <el-input
              v-model="runInput"
              type="textarea"
              :rows="2"
              placeholder="输入消息，回车或点发送……"
              @keydown.enter.exact.prevent="sendChat"
            />
            <el-button type="primary" :loading="running" :icon="Promotion" @click="sendChat">
              发送
            </el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 单节点调试抽屉 -->
    <el-drawer v-model="debugVisible" title="单节点调试" size="480px" append-to-body>
      <el-form label-position="top" size="small">
        <el-form-item label="调试节点">
          <div class="debug-node-title">
            <el-icon :color="iconColor(debugNodeType)">
              <component :is="iconOf(debugNodeType)" />
            </el-icon>
            <span>{{ nodeDefOf(debugNodeType).label }}</span>
          </div>
        </el-form-item>
        <el-form-item label="输入变量（JSON，可留空）">
          <el-input
            v-model="debugVariables"
            type="textarea"
            :rows="3"
            placeholder='如 {"query": "你好", "items": [1,2,3]}'
          />
        </el-form-item>
        <el-button type="primary" :loading="debugRunning" style="width: 100%" @click="runNodeDebug">
          运行节点
        </el-button>
      </el-form>
      <div v-if="debugError" class="debug-result">
        <div class="debug-result__title is-err">错误</div>
        <pre class="debug-result__body is-err">{{ debugError }}</pre>
      </div>
      <div v-if="debugInput" class="debug-result">
        <div class="debug-result__title">输入</div>
        <pre class="debug-result__body">{{ debugInput }}</pre>
      </div>
      <div v-if="debugOutput != null" class="debug-result">
        <div class="debug-result__title">输出</div>
        <pre class="debug-result__body">{{ debugOutput }}</pre>
      </div>
    </el-drawer>

    <!-- 隐藏文件选择：工作流导入 -->
    <input
      ref="importFileRef"
      type="file"
      accept=".json,application/json"
      style="display: none"
      @change="onImportFileChange"
    />

    <!-- 运行历史弹窗 -->
    <el-dialog v-model="historyVisible" title="运行历史" width="760px" append-to-body>
      <div class="history-stats">
        <el-statistic title="总运行" :value="runHistoryList.length" />
        <el-statistic title="成功" :value="historyStats.success" />
        <el-statistic title="失败" :value="historyStats.fail" />
        <el-statistic title="平均耗时(ms)" :value="historyStats.avgMs" />
      </div>
      <el-table
        v-loading="historyLoading"
        :data="runHistoryList"
        size="small"
        border
        max-height="420"
      >
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="
                row.status === 'success' ? 'success' : row.status === 'error' ? 'danger' : 'warning'
              "
            >
              {{ row.status === "success" ? "成功" : row.status === "error" ? "失败" : "审批中" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90" prop="duration_ms" />
        <el-table-column label="输出预览">
          <template #default="{ row }">
            <span class="history-preview">{{ previewText(row.run_output) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="70">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRunDetail(row.id)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="runDetail" class="history-detail">
        <div class="history-detail__title">节点执行过程</div>
        <div v-for="(tr, i) in runDetail.node_trace || []" :key="i" class="history-detail__item">
          <div class="hd-head">
            <span class="hd-label">{{ tr.label }}</span>
            <el-tag
              size="small"
              :type="
                tr.status === 'success' ? 'success' : tr.status === 'error' ? 'danger' : 'primary'
              "
            >
              {{ tr.status === "success" ? "完成" : tr.status === "error" ? "失败" : "执行中" }}
            </el-tag>
          </div>
          <div v-if="tr.error" class="hd-err">{{ tr.error }}</div>
          <div v-if="tr.input && Object.keys(tr.input).length" class="hd-kv">
            <span class="hd-kv-t">输入</span>
            <pre class="hd-pre">{{ formatJson(tr.input) }}</pre>
          </div>
          <div v-if="tr.output != null" class="hd-kv">
            <span class="hd-kv-t">输出</span>
            <pre class="hd-pre">{{ formatJson(tr.output) }}</pre>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 版本管理弹窗 -->
    <el-dialog v-model="versionsVisible" title="版本管理" width="680px" append-to-body>
      <div class="version-save-row">
        <el-input
          v-model="versionRemark"
          placeholder="填写本次版本说明（可选）"
          style="flex: 1"
          size="small"
        />
        <el-button type="primary" size="small" :loading="savingVersion" @click="saveVersion">
          保存当前版本
        </el-button>
      </div>
      <el-table v-loading="versionLoading" :data="versions" size="small" border>
        <el-table-column label="版本" width="80">
          <template #default="{ row }">v{{ row.version_no }}</template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.published" type="success" size="small">已发布</el-tag>
            <el-tag v-else type="info" size="small">草稿</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="保存时间" width="180" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="success" size="small" @click="openCompare(row)">对比</el-button>
            <el-button link type="primary" size="small" @click="doPublish(row)">发布</el-button>
            <el-button link type="warning" size="small" @click="doRollback(row)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 版本对比弹窗 -->
    <el-dialog v-model="compareVisible" :title="compareTitle" width="520px" append-to-body>
      <div v-if="!diffItems.length" class="compare-empty">该版本与当前画布内容一致。</div>
      <div v-for="(d, i) in diffItems" :key="i" class="compare-item">
        <el-tag
          size="small"
          :type="d.status === '新增' ? 'success' : d.status === '删除' ? 'danger' : 'warning'"
        >
          {{ d.status }}
        </el-tag>
        <span class="compare-label">{{ d.label }}</span>
        <span class="compare-detail">{{ d.detail }}</span>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, markRaw, onMounted, onUnmounted, type Component } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Panel, VueFlow, useVueFlow } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { MiniMap } from "@vue-flow/minimap";
import { Controls } from "@vue-flow/controls";
import type { Node, Edge, DefaultEdgeOptions, MarkerType } from "@vue-flow/core";
import {
  Promotion,
  VideoPlay,
  Cpu,
  Document,
  DocumentCopy,
  Tools,
  Loading,
  Download,
  Upload,
  Operation,
  SwitchFilled,
  DataLine,
  Connection,
  Refresh,
  Filter,
  Tickets,
  FullScreen,
  RefreshLeft,
  RefreshRight,
  Clock,
  MagicStick,
  Collection,
  ChatDotRound,
  Share,
  User,
  Sort,
  Grid,
  Search,
  Coin,
  CircleCheckFilled,
} from "@element-plus/icons-vue";
import dagre from "dagre";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

import WorkflowNode from "./WorkflowNode.vue";
import NodeConfigPanel from "./NodeConfigPanel.vue";
import { NODE_DEFS, NODE_CATEGORIES, nodeDefOf, categoryOf, type WorkflowNodeType } from "../nodes";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiToolList } from "@/api/module_ai/tool";
import {
  createAiWorkflow,
  updateAiWorkflow,
  saveAiWorkflowVersion,
  listAiWorkflowVersions,
  rollbackAiWorkflowVersion,
  publishAiWorkflowVersion,
  listAiWorkflowRunLogs,
  getAiWorkflowRunLog,
} from "@/api/module_ai/workflow";
import { Auth } from "@/utils/auth";

defineOptions({ name: "AiWorkflowEditor", inheritAttrs: false });

const props = defineProps<{ visible: boolean; workflow?: any }>();
const emit = defineEmits(["update:visible", "refresh"]);

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit("update:visible", v),
});

const nodeTypes = markRaw<Record<string, Component>>(
  Object.fromEntries([
    ...NODE_DEFS.map((d) => [d.type, WorkflowNode]),
    ["__default", WorkflowNode],
  ] as [string, Component][])
);

const {
  onInit,
  onConnect,
  addEdges,
  setNodes,
  setEdges,
  screenToFlowCoordinate,
  addNodes,
  fitView,
} = useVueFlow();

const defaultEdgeOptions: DefaultEdgeOptions = {
  type: "smoothstep",
  animated: true,
  markerEnd: "arrowclosed" as MarkerType,
};

// 连接事件：由 useVueFlow 注册处理器
// 连线自动填充：连上后让下游「输出类/模板」节点自动引用上游输出变量
const AUTO_OUTPUT_VAR: Record<string, string> = {
  llm: "llm_output",
  code: "code_output",
  tool: "tool_output",
  http: "http_output",
  knowledge: "kb_context",
  template: "template_output",
  variable_aggregator: "aggregated",
  sub_workflow: "workflow_output",
  agent: "agent_output",
  loop: "loop_output",
  parallel: "parallel_output",
  doc_extractor: "doc_output",
  web_search: "web_output",
  database: "db_rows",
  condition: "condition_result",
  classifier: "classifier_result",
  extractor: "extractor_result",
  answer: "answer_output",
};
const AUTO_PRIMARY_FIELD: Record<string, string> = {
  end: "output_template",
  answer: "output_template",
  template: "template",
  llm: "prompt",
};

function ensureOutputVar(s: Node): string | null {
  const base = AUTO_OUTPUT_VAR[s.type as string];
  if (!base) return null;
  if (s.data?.output_variable) return s.data.output_variable;
  let name = base;
  let i = 2;
  const used = new Set(
    nodes.value.map((n) => n.data?.output_variable).filter((v): v is string => !!v)
  );
  while (used.has(name)) name = `${base}_${i++}`;
  s.data = { ...(s.data || {}), output_variable: name };
  return name;
}

function autoFillOnConnect(conn: { source: string; target: string }) {
  const s = nodes.value.find((n) => n.id === conn.source);
  const t = nodes.value.find((n) => n.id === conn.target);
  if (!s || !t) return;
  const field = AUTO_PRIMARY_FIELD[t.type as string];
  if (!field) return;
  const varName = ensureOutputVar(s);
  if (!varName) return;
  const cur = t.data?.[field];
  if (cur && String(cur).trim()) return; // 已有内容不覆盖
  t.data = { ...(t.data || {}), [field]: `{{${varName}}}` };
}

onConnect((conn) => {
  pushHistory();
  addEdges({ ...conn, type: defaultEdgeOptions.type, animated: true });
  autoFillOnConnect(conn);
});

const formData = reactive<{ name: string; description: string }>({ name: "", description: "" });
const workflowId = ref<number>();
const saving = ref(false);
const nodes = ref<Node[]>([]);
const edges = ref<Edge[]>([]);
const selectedNode = ref<Node>();
const runVisible = ref(false);
const running = ref(false);
const runInput = ref("");
const runVariables = ref("{}");
const approving = ref(false);
const runListRef = ref<HTMLElement>();

// 对话式运行：消息列表（含每轮的节点执行轨迹）
interface TraceItem {
  nodeId: string;
  status: string;
  label: string;
  input?: any;
  output?: any;
  error?: string;
}
interface ChatMsg {
  id: number;
  role: "user" | "assistant";
  content: string;
  trace?: TraceItem[];
  sources?: any[];
  approval?: { run_id: string; toolCalls: any[] };
  running?: boolean;
  error?: string;
}
const chatMessages = ref<ChatMsg[]>([]);
const activeMsg = ref<ChatMsg | null>(null);
let chatSeq = 0;
const chatVarsOpen = ref<string[]>([]);
const traceOpen = ref<Record<string, boolean>>({});
function toggleTraceOpen(key: string) {
  traceOpen.value[key] = !traceOpen.value[key];
}
function scrollRunBottom() {
  window.setTimeout(() => {
    runListRef.value?.scrollTo({ top: runListRef.value.scrollHeight, behavior: "smooth" });
  }, 30);
}

// 调试执行追踪：高亮画布节点
const nodeRunStates = ref<Record<string, string>>({});
function resetRunTrace() {
  nodeRunStates.value = {};
  nodes.value.forEach((n) => {
    n.data = {
      ...(n.data || {}),
      __runStatus: "",
      __runInput: undefined,
      __runOutput: undefined,
      __runError: undefined,
    };
  });
}

function onNodeStatus(ns: any) {
  const status = ns.status || "success";
  nodeRunStates.value[ns.nodeId] = status;
  const n = nodes.value.find((x) => x.id === ns.nodeId);
  if (n) {
    n.data = {
      ...(n.data || {}),
      __runStatus: status,
      __runInput: ns.input,
      __runOutput: ns.output,
      __runError: ns.error,
    };
  }
}

function statusText(s: string) {
  return s === "running" ? "执行中" : s === "error" ? "失败" : s === "skipped" ? "已跳过" : "完成";
}

function formatJson(v: any): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
function copyText(text: string) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success("已复制"),
    () => ElMessage.error("复制失败")
  );
}

// ---------- 单节点调试 ----------
const debugVisible = ref(false);
const debugNodeId = ref<string>("");
const debugNodeType = ref<string>("llm");
const debugVariables = ref("{}");
const debugRunning = ref(false);
const debugInput = ref<any>(null);
const debugOutput = ref<any>(null);
const debugError = ref("");
function iconColor(t: string): string {
  return nodeDefOf(t).color;
}
function openNodeDebug() {
  if (!selectedNode.value) return;
  debugNodeId.value = selectedNode.value.id;
  debugNodeType.value = selectedNode.value.type || "llm";
  debugVariables.value = "{}";
  debugInput.value = null;
  debugOutput.value = null;
  debugError.value = "";
  debugVisible.value = true;
}
async function runNodeDebug() {
  if (!workflowId.value) {
    await handleSave();
    if (!workflowId.value) return;
  }
  if (!debugNodeId.value) return;
  debugRunning.value = true;
  debugInput.value = null;
  debugOutput.value = null;
  debugError.value = "";
  try {
    let variables = {};
    try {
      variables = debugVariables.value ? JSON.parse(debugVariables.value) : {};
    } catch {
      variables = {};
    }
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const resp = await fetch(`${base}/ai/workflows/${workflowId.value}/debug-node/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
      },
      body: JSON.stringify({ node_id: debugNodeId.value, variables }),
    });
    if (!resp.ok || !resp.body) {
      debugError.value = `请求失败：${resp.status}`;
      return;
    }
    await readUiStream(resp, (obj) => {
      if (obj.type === "node-status") {
        debugInput.value = obj.input ?? debugInput.value;
        debugOutput.value = obj.output ?? debugOutput.value;
        if (obj.error) debugError.value = obj.error;
        if (obj.status === "error" && !obj.error) debugError.value = "节点执行失败";
      } else if (obj.type === "error") {
        debugError.value = obj.errorText || obj.message || "节点执行失败";
      }
    });
  } catch (e: any) {
    debugError.value = `调试失败：${e?.message || e}`;
  } finally {
    debugRunning.value = false;
  }
}

// ---------- 运行历史 ----------
const historyVisible = ref(false);
const historyLoading = ref(false);
const runHistoryList = ref<any[]>([]);
const runDetail = ref<any>(null);
const historyStats = computed(() => {
  const list = runHistoryList.value;
  const success = list.filter((r) => r.status === "success").length;
  const fail = list.filter((r) => r.status === "error").length;
  const ms = list.length
    ? Math.round(list.reduce((acc, r) => acc + (r.duration_ms || 0), 0) / list.length)
    : 0;
  return { success, fail, avgMs: ms };
});
async function openRunHistory() {
  if (!workflowId.value) return;
  historyVisible.value = true;
  historyLoading.value = true;
  runDetail.value = null;
  try {
    const res = await listAiWorkflowRunLogs(workflowId.value);
    runHistoryList.value = res.data?.data || [];
  } catch {
    runHistoryList.value = [];
  } finally {
    historyLoading.value = false;
  }
}
async function openRunDetail(id: number) {
  const res = await getAiWorkflowRunLog(id);
  runDetail.value = res.data?.data || null;
}
function previewText(out: any): string {
  if (!out) return "";
  const reply = out.reply ?? out;
  const s = typeof reply === "string" ? reply : JSON.stringify(reply);
  return s.length > 80 ? s.slice(0, 80) + "…" : s;
}
function formatTime(t: any): string {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}
const modelOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string; enabled: boolean }[]>([]);

// 供属性面板「插入变量」使用：内置变量 + 输入变量 + 各节点输出变量
const availableVars = computed(() => {
  const map = new Map<string, string>();
  map.set("query", "用户输入 query");
  map.set("assistant_text", "助手回复 assistant_text");
  nodes.value.forEach((n) => {
    if (n.type === "start") {
      (n.data.variables || []).forEach((v: any) => {
        if (v.name) map.set(v.name, `输入变量 ${v.name}`);
      });
    }
    if (n.data?.output_variable) {
      map.set(n.data.output_variable, `节点输出 ${n.data.output_variable}`);
    }
  });
  return Array.from(map, ([name, label]) => ({ name, label }));
});

// 变量来源映射：变量名 → 产出该变量的节点类型（供属性面板展示来源）
const varSources = computed(() => {
  const m: Record<string, string> = {};
  nodes.value.forEach((n) => {
    const ov = n.data?.output_variable;
    if (ov) m[ov] = nodeDefOf(n.type || "llm").label;
  });
  return m;
});

// 选中节点的上游调用链（从 start 到该节点的路径节点标签序列）
function findPath(from: string, to: string, visited: Set<string>): string[] | null {
  if (from === to) return [from];
  if (visited.has(from)) return null;
  visited.add(from);
  for (const e of edges.value.filter((x) => x.source === from)) {
    const p = findPath(e.target, to, visited);
    if (p) return [from, ...p];
  }
  return null;
}
const nodeChain = computed(() => {
  if (!selectedNode.value) return [];
  const starts = nodes.value.filter((n) => n.type === "start").map((n) => n.id);
  for (const s of starts) {
    const path = findPath(s, selectedNode.value.id, new Set());
    if (path) {
      return path.map((id) => {
        const n = nodes.value.find((x) => x.id === id);
        return nodeDefOf(n?.type || "llm").label;
      });
    }
  }
  return [];
});

// ---------- 撤销 / 重做 ----------
type GraphSnapshot = { nodes: any[]; edges: any[] };
const undoStack = ref<GraphSnapshot[]>([]);
const redoStack = ref<GraphSnapshot[]>([]);
const canUndo = computed(() => undoStack.value.length > 0);
const canRedo = computed(() => redoStack.value.length > 0);
let configHistoryTimer = 0;

function graphSnapshot(): GraphSnapshot {
  return {
    nodes: JSON.parse(JSON.stringify(nodes.value)),
    edges: JSON.parse(JSON.stringify(edges.value)),
  };
}

function pushHistory() {
  const snap = graphSnapshot();
  const top = undoStack.value[undoStack.value.length - 1];
  if (top && JSON.stringify(snap) === JSON.stringify(top)) return; // 与上一条相同则跳过
  undoStack.value.push(snap);
  if (undoStack.value.length > 50) undoStack.value.shift();
  redoStack.value = [];
}

function applySnapshot(snap: GraphSnapshot) {
  setNodes(snap.nodes);
  setEdges(snap.edges);
  const selId = selectedNode.value?.id;
  selectedNode.value = snap.nodes.find((n) => n.id === selId) || undefined;
}

function undo() {
  if (!undoStack.value.length) return;
  redoStack.value.push(graphSnapshot());
  const prev = undoStack.value.pop()!;
  applySnapshot(prev);
}

function redo() {
  if (!redoStack.value.length) return;
  undoStack.value.push(graphSnapshot());
  const next = redoStack.value.pop()!;
  applySnapshot(next);
}

// 编辑节点属性时，仅在首个变更记录一次「编辑前」快照（500ms 窗口去抖）
function scheduleHistory() {
  if (configHistoryTimer) return;
  pushHistory();
  configHistoryTimer = window.setTimeout(() => {
    configHistoryTimer = 0;
  }, 500);
}

function onNodeDragStart() {
  pushHistory();
}
function onNodeDragStop() {
  /* 拖动结束由 drag-start 已记录一次，这里无需重复 */
}

function onKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  const key = e.key.toLowerCase();
  if (key === "z" && e.shiftKey) {
    e.preventDefault();
    redo();
  } else if (key === "z") {
    e.preventDefault();
    undo();
  } else if (key === "y") {
    e.preventDefault();
    redo();
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));

// ---------- 版本管理 ----------
const versionsVisible = ref(false);
const versions = ref<any[]>([]);
const versionLoading = ref(false);
const savingVersion = ref(false);
const versionRemark = ref("");
const compareVisible = ref(false);
const compareTitle = ref("");
const diffItems = ref<{ label: string; status: string; detail: string }[]>([]);

function openCompare(row: any) {
  const vNodes: any[] = (row.graph?.nodes || []) as any[];
  const curNodes: any[] = nodes.value || [];
  const vMap = new Map(vNodes.map((n: any) => [n.id, n]));
  const cMap = new Map(curNodes.map((n: any) => [n.id, n]));
  const items: { label: string; status: string; detail: string }[] = [];
  cMap.forEach((n, id) => {
    const v = vMap.get(id);
    if (!v) {
      items.push({
        label: nodeDefOf(n.type || "llm").label,
        status: "新增",
        detail: "当前画布新增节点",
      });
    } else if (JSON.stringify(n.data || {}) !== JSON.stringify(v.data || {})) {
      items.push({
        label: nodeDefOf(n.type || "llm").label,
        status: "修改",
        detail: "节点参数已变化",
      });
    }
  });
  vMap.forEach((v, id) => {
    if (!cMap.has(id)) {
      items.push({
        label: nodeDefOf(v.type || "llm").label,
        status: "删除",
        detail: "该版本有、当前画布无",
      });
    }
  });
  diffItems.value = items;
  compareTitle.value = `版本 v${row.version_no} vs 当前画布`;
  compareVisible.value = true;
}

async function openVersions() {
  versionsVisible.value = true;
  versionRemark.value = "";
  await loadVersions();
}

async function loadVersions() {
  if (!workflowId.value) return;
  versionLoading.value = true;
  try {
    const res = await listAiWorkflowVersions(workflowId.value);
    versions.value = res.data?.data || [];
  } catch {
    versions.value = [];
  } finally {
    versionLoading.value = false;
  }
}

async function saveVersion() {
  if (!workflowId.value) return;
  savingVersion.value = true;
  try {
    await saveAiWorkflowVersion(workflowId.value, {
      remark: versionRemark.value,
      graph: buildGraph(),
    });
    ElMessage.success("版本已保存");
    versionRemark.value = "";
    await loadVersions();
  } catch {
    ElMessage.error("保存版本失败");
  } finally {
    savingVersion.value = false;
  }
}

async function doPublish(v: any) {
  if (!workflowId.value) return;
  await ElMessageBox.confirm(
    `确认发布版本 v${v.version_no} 为线上版本吗？将用该版本的 DAG 覆盖当前工作流。`,
    "发布确认",
    { confirmButtonText: "发布", cancelButtonText: "取消", type: "warning" }
  );
  try {
    await publishAiWorkflowVersion(workflowId.value, v.id);
    ElMessage.success("发布成功");
    await loadVersions();
  } catch {
    ElMessage.error("发布失败");
  }
}

async function doRollback(v: any) {
  if (!workflowId.value) return;
  await ElMessageBox.confirm(
    `确认回滚到版本 v${v.version_no} 吗？当前画布内容将被该版本的 DAG 覆盖，且不可恢复。`,
    "回滚确认",
    { confirmButtonText: "回滚", cancelButtonText: "取消", type: "warning" }
  );
  try {
    const res = await rollbackAiWorkflowVersion(workflowId.value, v.id);
    ElMessage.success("回滚成功");
    const g = res.data?.data?.graph;
    if (g) {
      nodes.value = g.nodes.map((n: any) => ({
        id: n.id,
        type: n.type,
        position: { x: n.x ?? 0, y: n.y ?? 0 },
        data: { ...(n.data || {}) },
      }));
      edges.value = g.edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || undefined,
        type: defaultEdgeOptions.type,
        animated: true,
      }));
    }
    await loadVersions();
  } catch {
    ElMessage.error("回滚失败");
  }
}

function iconOf(type: string) {
  const m: Record<WorkflowNodeType, any> = {
    start: Promotion,
    llm: Cpu,
    knowledge: DocumentCopy,
    tool: Tools,
    code: Operation,
    condition: SwitchFilled,
    variable: DataLine,
    http: Connection,
    iteration: Refresh,
    classifier: Filter,
    extractor: Tickets,
    template: MagicStick,
    variable_aggregator: Collection,
    answer: ChatDotRound,
    sub_workflow: Share,
    agent: User,
    loop: Sort,
    parallel: Grid,
    doc_extractor: Document,
    web_search: Search,
    database: Coin,
    end: CircleCheckFilled,
  };
  return m[type as WorkflowNodeType] || Cpu;
}

// 载入模型 / 工具选项供 LLM / 工具节点使用
const loadOptions = async () => {
  try {
    const [mr, tr] = await Promise.all([getAiModelList({}), getAiToolList({})]);
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
  } catch {
    /* ignore */
  }
};

onInit((instance) => {
  instance.fitView();
  loadOptions();
  if (props.workflow) {
    workflowId.value = props.workflow.id;
    formData.name = props.workflow.name || "";
    formData.description = props.workflow.description || "";
    const g = props.workflow.graph || { nodes: [], edges: [] };
    nodes.value = g.nodes.map((n: any) => ({
      id: n.id,
      type: n.type,
      position: { x: n.x ?? 0, y: n.y ?? 0 },
      data: { ...(n.data || {}) },
    }));
    edges.value = g.edges.map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || undefined,
      type: defaultEdgeOptions.type,
      animated: true,
    }));
  }
  // 载入后重置撤销/重做历史
  undoStack.value = [];
  redoStack.value = [];
});

function onNodeClick(event: any) {
  event.event.stopPropagation();
  selectedNode.value = event.node;
}

function handleCanvasClick(event: MouseEvent) {
  if (
    event.target instanceof HTMLElement &&
    (event.target.classList.contains("vue-flow__node") || event.target.closest(".vue-flow__node"))
  ) {
    return;
  }
  selectedNode.value = undefined;
}

function onDragStart(event: DragEvent, type: string) {
  if (event.dataTransfer) {
    event.dataTransfer.setData("application/aiworkflow", type);
    event.dataTransfer.effectAllowed = "move";
  }
}

// 调色板检索与分组
const paletteQuery = ref("");
function filteredPalette(catKey: string): typeof NODE_DEFS {
  const q = paletteQuery.value.trim().toLowerCase();
  const inCat = NODE_DEFS.filter((d) => categoryOf(d.type) === catKey);
  if (!q) return inCat;
  return inCat.filter(
    (d) =>
      d.label.toLowerCase().includes(q) || d.desc.toLowerCase().includes(q) || d.type.includes(q)
  );
}

function onPaletteClick(type: string) {
  const position = screenToFlowCoordinate({
    x: window.innerWidth / 2,
    y: window.innerHeight / 2,
  });
  const id = `node_${Date.now()}`;
  const node = { id, type, position, data: defaultData(type) } as Node;
  pushHistory();
  addNodes([node]);
  selectedNode.value = node;
  ElMessage.success(`已添加「${nodeDefOf(type).label}」节点，请在右侧编辑`);
}

function onDragOver(event: DragEvent) {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
}

function onDrop(event: DragEvent) {
  const type = event.dataTransfer?.getData("application/aiworkflow");
  if (!type) return;
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY });
  const id = `node_${Date.now()}`;
  pushHistory();
  addNodes([
    {
      id,
      type,
      position,
      data: defaultData(type),
    } as Node,
  ]);
}

function defaultData(type: string): Record<string, any> {
  switch (type) {
    case "start":
      return { variables: [] };
    case "llm":
      return { prompt: "", temperature: 0.7, tools: [], output_variable: "" };
    case "knowledge":
      return { knowledge_ids: [], query: "", top_k: 3, output_variable: "" };
    case "tool":
      return { tool_name: "", args: {}, output_variable: "" };
    case "code":
      return { code: "", inputs: {}, output_variable: "" };
    case "condition":
      return { expression: "" };
    case "variable":
      return { name: "", value: "" };
    case "http":
      return { method: "GET", url: "", headers: {}, body: {}, output_variable: "" };
    case "iteration":
      return { items: [], tool_name: "", args: {}, output_variable: "", max_iterations: 20 };
    case "classifier":
      return { categories: [], query: "", output_variable: "" };
    case "extractor":
      return { schema: [], query: "", output_variable: "" };
    case "template":
      return { template: "", output_variable: "" };
    case "variable_aggregator":
      return { fields: [], output_variable: "" };
    case "answer":
      return { output_template: "" };
    case "sub_workflow":
      return { workflow_id: null, output_variable: "" };
    case "agent":
      return { agent_id: null, query: "", output_variable: "" };
    case "loop":
      return { items: [], body_workflow_id: null, max_iterations: 20, output_variable: "" };
    case "parallel":
      return { branches: [], output_variable: "" };
    case "doc_extractor":
      return { url: "", source: "", output_variable: "" };
    case "web_search":
      return { query: "", endpoint: "", api_key: "", output_variable: "" };
    case "database":
      return { dsn: "", sql: "", output_variable: "" };
    case "end":
      return { output_template: "" };
    default:
      return {};
  }
}

// ---------------- 快速模板 ----------------
interface WfTemplate {
  key: string;
  name: string;
  desc: string;
  build: () => { nodes: Node[]; edges: Edge[] };
}

const WF_TEMPLATES: WfTemplate[] = [
  {
    key: "qa",
    name: "客服问答",
    desc: "start → LLM → 结束",
    build: () => {
      const t = Date.now();
      const nodes: Node[] = [
        {
          id: `t1_${t}`,
          type: "start",
          position: { x: 40, y: 120 },
          data: {
            ...defaultData("start"),
            variables: [{ name: "query", type: "string", required: true }],
          },
        },
        {
          id: `t2_${t}`,
          type: "llm",
          position: { x: 320, y: 120 },
          data: {
            ...defaultData("llm"),
            prompt: "你是客服助手，请回答用户问题：{{query}}",
            output_variable: "llm_output",
          },
        },
        {
          id: `t3_${t}`,
          type: "end",
          position: { x: 600, y: 120 },
          data: { ...defaultData("end"), output_template: "{{llm_output}}" },
        },
      ];
      const edges: Edge[] = [
        { id: `te1_${t}`, source: nodes[0].id, target: nodes[1].id },
        { id: `te2_${t}`, source: nodes[1].id, target: nodes[2].id },
      ];
      return { nodes, edges };
    },
  },
  {
    key: "rag",
    name: "知识库检索问答",
    desc: "start → 知识检索 → LLM → 结束",
    build: () => {
      const t = Date.now();
      const nodes: Node[] = [
        {
          id: `t1_${t}`,
          type: "start",
          position: { x: 40, y: 120 },
          data: {
            ...defaultData("start"),
            variables: [{ name: "query", type: "string", required: true }],
          },
        },
        {
          id: `t2_${t}`,
          type: "knowledge",
          position: { x: 320, y: 60 },
          data: { ...defaultData("knowledge"), query: "{{query}}", output_variable: "kb_context" },
        },
        {
          id: `t3_${t}`,
          type: "llm",
          position: { x: 320, y: 220 },
          data: {
            ...defaultData("llm"),
            prompt: "结合知识库回答：\n{{kb_context}}\n问题：{{query}}",
            output_variable: "llm_output",
          },
        },
        {
          id: `t4_${t}`,
          type: "end",
          position: { x: 620, y: 150 },
          data: { ...defaultData("end"), output_template: "{{llm_output}}" },
        },
      ];
      const edges: Edge[] = [
        { id: `te1_${t}`, source: nodes[0].id, target: nodes[1].id },
        { id: `te1b_${t}`, source: nodes[0].id, target: nodes[2].id },
        { id: `te2_${t}`, source: nodes[1].id, target: nodes[2].id },
        { id: `te3_${t}`, source: nodes[2].id, target: nodes[3].id },
      ];
      return { nodes, edges };
    },
  },
  {
    key: "condition",
    name: "条件分派",
    desc: "start → LLM → 条件分支",
    build: () => {
      const t = Date.now();
      const nodes: Node[] = [
        {
          id: `t1_${t}`,
          type: "start",
          position: { x: 40, y: 150 },
          data: {
            ...defaultData("start"),
            variables: [{ name: "query", type: "string", required: true }],
          },
        },
        {
          id: `t2_${t}`,
          type: "llm",
          position: { x: 320, y: 150 },
          data: {
            ...defaultData("llm"),
            prompt: "请简洁回答：{{query}}",
            output_variable: "llm_output",
          },
        },
        {
          id: `t3_${t}`,
          type: "condition",
          position: { x: 600, y: 150 },
          data: { ...defaultData("condition"), expression: 'llm_output != ""' },
        },
        {
          id: `t4_${t}`,
          type: "answer",
          position: { x: 880, y: 60 },
          data: { ...defaultData("answer"), output_template: "{{llm_output}}" },
        },
        {
          id: `t5_${t}`,
          type: "end",
          position: { x: 880, y: 240 },
          data: { ...defaultData("end"), output_template: "无结果" },
        },
      ];
      const edges: Edge[] = [
        { id: `te1_${t}`, source: nodes[0].id, target: nodes[1].id },
        { id: `te2_${t}`, source: nodes[1].id, target: nodes[2].id },
        { id: `te3_${t}`, source: nodes[2].id, target: nodes[3].id, sourceHandle: "true" },
        { id: `te4_${t}`, source: nodes[2].id, target: nodes[4].id, sourceHandle: "false" },
      ];
      return { nodes, edges };
    },
  },
  {
    key: "batch",
    name: "批量处理",
    desc: "start → 迭代(工具) → 结束",
    build: () => {
      const t = Date.now();
      const nodes: Node[] = [
        {
          id: `t1_${t}`,
          type: "start",
          position: { x: 40, y: 150 },
          data: {
            ...defaultData("start"),
            variables: [{ name: "items", type: "array", required: true }],
          },
        },
        {
          id: `t2_${t}`,
          type: "iteration",
          position: { x: 320, y: 150 },
          data: {
            ...defaultData("iteration"),
            items: "{{items}}",
            tool_name: "",
            output_variable: "results",
          },
        },
        {
          id: `t3_${t}`,
          type: "end",
          position: { x: 600, y: 150 },
          data: { ...defaultData("end"), output_template: "{{results}}" },
        },
      ];
      const edges: Edge[] = [
        { id: `te1_${t}`, source: nodes[0].id, target: nodes[1].id },
        { id: `te2_${t}`, source: nodes[1].id, target: nodes[2].id },
      ];
      return { nodes, edges };
    },
  },
];

async function applyTemplateByKey(key: string) {
  const tpl = WF_TEMPLATES.find((x) => x.key === key);
  if (!tpl) return;
  if (nodes.value.length) {
    await ElMessageBox.confirm(
      "应用模板将替换当前画布内容，此操作不可恢复。是否继续？",
      "应用模板",
      { confirmButtonText: "应用", cancelButtonText: "取消", type: "warning" }
    );
  }
  const { nodes: tn, edges: te } = tpl.build();
  pushHistory();
  nodes.value = tn;
  edges.value = te as Edge[];
  if (!formData.name.trim()) formData.name = tpl.name;
  selectedNode.value = undefined;
  ElMessage.success(`已应用模板「${tpl.name}」`);
}

function onNodeConfigChange(data: Record<string, any>) {
  if (!selectedNode.value) return;
  scheduleHistory();
  selectedNode.value.data = { ...selectedNode.value.data, ...data };
}

function handleDeleteNode() {
  if (!selectedNode.value) return;
  const id = selectedNode.value.id;
  ElMessageBox.confirm("确定删除该节点吗？", "提示", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  }).then(() => {
    pushHistory();
    nodes.value = nodes.value.filter((n) => n.id !== id);
    edges.value = edges.value.filter((e) => e.source !== id && e.target !== id);
    selectedNode.value = undefined;
    ElMessage.success("节点已删除");
  });
}

function copySelectedNode() {
  if (!selectedNode.value) return;
  const src = selectedNode.value;
  const id = `node_${Date.now()}`;
  const data = JSON.parse(JSON.stringify(src.data || {}));
  delete data.__runStatus;
  delete data.__runOutput;
  delete data.__runError;
  delete data.__runInput;
  const node = {
    id,
    type: src.type,
    position: { x: src.position.x + 60, y: src.position.y + 60 },
    data,
  } as Node;
  pushHistory();
  addNodes([node]);
  selectedNode.value = node;
  ElMessage.success("已复制节点，可修改其配置");
}

function autoLayout() {
  if (nodes.value.length === 0) {
    ElMessage.warning("画布中没有节点");
    return;
  }
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  const nodeWidth = 200;
  const nodeHeight = 60;
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120, marginx: 40, marginy: 40 });
  nodes.value.forEach((n) => g.setNode(n.id, { width: nodeWidth, height: nodeHeight }));
  edges.value.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  pushHistory();
  setNodes(
    nodes.value.map((n) => {
      const p = g.node(n.id);
      return { ...n, position: { x: p.x - nodeWidth / 2, y: p.y - nodeHeight / 2 } };
    })
  );
}

function buildGraph() {
  return {
    nodes: nodes.value.map((n) => ({
      id: n.id,
      type: n.type,
      x: n.position?.x ?? 0,
      y: n.position?.y ?? 0,
      data: n.data || {},
    })),
    edges: edges.value.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle || undefined,
    })),
  };
}

// ---------- 导入 / 导出 ----------
const importFileRef = ref<HTMLInputElement>();
function handleExport() {
  const data = {
    name: formData.name || "未命名工作流",
    description: formData.description,
    graph: buildGraph(),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(formData.name || "workflow").replace(/[\\/:*?"<>|]/g, "_")}.json`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success("已导出工作流 JSON");
}
function triggerImport() {
  importFileRef.value?.click();
}
async function onImportFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  let parsed: any;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    ElMessage.error("文件不是有效的 JSON");
    return;
  }
  const graph = parsed?.graph || parsed;
  const inodes = (graph?.nodes || []) as any[];
  const iedges = (graph?.edges || []) as any[];
  if (!Array.isArray(inodes)) {
    ElMessage.error("JSON 中缺少 nodes 数组");
    return;
  }
  await ElMessageBox.confirm(
    `将导入 ${inodes.length} 个节点、${iedges.length} 条连线，并替换当前画布内容，此操作不可恢复。是否继续？`,
    "导入工作流",
    { confirmButtonText: "导入", cancelButtonText: "取消", type: "warning" }
  );
  pushHistory();
  const t = Date.now();
  nodes.value = inodes.map((n: any, i: number) => ({
    id: n.id || `imp_${t}_${i}`,
    type: n.type || "llm",
    position: { x: n.x ?? 40, y: n.y ?? 40 * (i + 1) },
    data: { ...(n.data || {}) },
  })) as Node[];
  edges.value = iedges.map((e: any) => ({
    id: e.id || `imp_${t}_e${Math.random().toString(36).slice(2)}`,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle || undefined,
  })) as Edge[];
  if (parsed?.name && !formData.name.trim()) formData.name = parsed.name;
  if (parsed?.description && !formData.description.trim())
    formData.description = parsed.description;
  selectedNode.value = undefined;
  ElMessage.success(`已导入工作流，共 ${inodes.length} 个节点`);
}

async function handleSave() {
  if (!formData.name) {
    ElMessage.warning("请填写工作流名称");
    return;
  }
  const hasStart = nodes.value.some((n) => n.type === "start");
  const hasEnd = nodes.value.some((n) => n.type === "end");
  if (!hasStart || !hasEnd) {
    ElMessage.warning("工作流需包含「开始」与「结束」节点");
    return;
  }
  saving.value = true;
  try {
    const graph = buildGraph();
    if (workflowId.value) {
      await updateAiWorkflow(workflowId.value, {
        name: formData.name,
        description: formData.description,
        graph,
      });
    } else {
      const res = await createAiWorkflow({
        name: formData.name,
        description: formData.description,
        graph,
        enabled: true,
      });
      workflowId.value = res.data?.data?.id;
    }
    ElMessage.success("保存成功");
    emit("refresh");
    dialogVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

function openRun() {
  runInput.value = "";
  runVariables.value = "{}";
  chatMessages.value = [];
  activeMsg.value = null;
  runVisible.value = true;
}

/** 读取 AI SDK UI Message Stream（SSE）并逐帧回调，供运行/审批复用。 */
async function readUiStream(resp: Response, onFrame: (obj: any) => void) {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const raw = t.slice(5).trim();
      if (raw === "[DONE]") continue;
      let obj: any;
      try {
        obj = JSON.parse(raw);
      } catch {
        continue;
      }
      onFrame(obj);
    }
  }
}

async function sendChat() {
  const text = runInput.value.trim();
  if (!text) {
    ElMessage.warning("请输入消息");
    return;
  }
  if (!workflowId.value) {
    // 未保存：先保存再运行
    await handleSave();
    if (!workflowId.value) return;
  }
  const userMsg: ChatMsg = { id: ++chatSeq, role: "user", content: text };
  chatMessages.value.push(userMsg);
  runInput.value = "";
  const msg: ChatMsg = { id: ++chatSeq, role: "assistant", content: "", trace: [], running: true };
  chatMessages.value.push(msg);
  activeMsg.value = msg;
  running.value = true;
  resetRunTrace();
  scrollRunBottom();
  try {
    let variables = {};
    try {
      variables = runVariables.value ? JSON.parse(runVariables.value) : {};
    } catch {
      variables = {};
    }
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const resp = await fetch(`${base}/ai/workflows/${workflowId.value}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
      },
      body: JSON.stringify({
        messages: [{ role: "user", parts: [{ type: "text", text }] }],
        variables,
      }),
    });
    if (!resp.ok || !resp.body) {
      msg.error = `请求失败：${resp.status}`;
      return;
    }
    await readUiStream(resp, (obj) => {
      if (obj.type === "text-delta") msg.content += obj.text;
      else if (obj.type === "sources") msg.sources = obj.sources || [];
      else if (obj.type === "node-status") {
        onNodeStatus(obj);
        msg.trace?.push({
          nodeId: obj.nodeId,
          status: obj.status || "success",
          label: obj.label || obj.nodeId,
          input: obj.input,
          output: obj.output,
          error: obj.error,
        });
        scrollRunBottom();
      } else if (obj.type === "data-finish") {
        if (obj.awaiting_approval && obj.run_id) {
          msg.approval = { run_id: obj.run_id, toolCalls: obj.pending_tool_calls || [] };
        }
        if (obj.reply != null) msg.content = obj.reply || msg.content;
      }
    });
  } catch (e: any) {
    msg.error = `运行失败：${e?.message || e}`;
  } finally {
    msg.running = false;
    running.value = false;
    scrollRunBottom();
  }
}

async function handleApprove(decision: "approve" | "reject") {
  const am = activeMsg.value;
  if (!am?.approval || !workflowId.value) return;
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const runId = am.approval.run_id;
  approving.value = true;
  am.approval = undefined;
  am.running = true;
  running.value = true;
  try {
    const resp = await fetch(`${base}/ai/workflows/${workflowId.value}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
      },
      body: JSON.stringify({ run_id: runId, decision }),
    });
    if (!resp.ok || !resp.body) {
      am.error = `审批请求失败：${resp.status}`;
      return;
    }
    await readUiStream(resp, (obj) => {
      if (obj.type === "text-delta") am.content += obj.text;
      else if (obj.type === "node-status") {
        onNodeStatus(obj);
        am.trace?.push({
          nodeId: obj.nodeId,
          status: obj.status || "success",
          label: obj.label || obj.nodeId,
          input: obj.input,
          output: obj.output,
          error: obj.error,
        });
      } else if (obj.type === "data-finish") am.content = obj.reply || am.content;
      else if (obj.type === "error")
        am.error = obj.errorText || obj.msg || obj.message || "审批失败";
    });
  } catch (e: any) {
    am.error = `审批续跑失败：${e?.message || e}`;
  } finally {
    am.running = false;
    running.value = false;
    approving.value = false;
    am.approval = undefined;
  }
}
</script>

<style scoped lang="scss">
.wf-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.wf-editor :deep(.el-splitter) {
  flex: 1;
}

.wf-editor :deep(.el-splitter-panel) {
  overflow: hidden;
}

.panel-section {
  padding: 12px;

  .section-title {
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 600;
  }
}

.palette-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  font-size: 13px;
  cursor: move;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  user-select: none;

  &:hover {
    border-color: var(--el-color-primary);
  }

  .palette-item__desc {
    margin-left: auto;
    font-size: 11px;
    color: var(--el-text-color-placeholder);
  }
}

.palette-tip {
  margin: -4px 0 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.palette-search {
  margin-bottom: 8px;
}

.palette-group {
  margin-bottom: 10px;

  .palette-group__title {
    margin-bottom: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-secondary);
  }
}

.tpl-menu {
  display: flex;
  flex-direction: column;
  line-height: 1.3;

  .tpl-menu__desc {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.canvas-main {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.canvas-container {
  flex: 1;
  overflow: hidden;
}

.wf-toolbar {
  display: flex;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-light);
}

.wf-hint {
  padding: 4px 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
}

.wf-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.version-save-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.run-output {
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;

  .run-output__title {
    margin-bottom: 8px;
    font-weight: 600;
  }

  .run-output__body {
    max-height: 220px;
    overflow: auto;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

/* ---------- 运行抽屉（对话式） ---------- */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-list {
  flex: 1;
  overflow: auto;
  padding: 4px 4px 12px;
}

.chat-empty {
  padding: 32px 20px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.chat-msg {
  display: flex;
  margin-bottom: 12px;

  &.is-user {
    justify-content: flex-end;
  }

  .chat-msg__bubble {
    max-width: 92%;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.6;
  }

  &.is-user .chat-msg__bubble {
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-7);
  }

  &.is-assistant .chat-msg__bubble {
    width: 100%;
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-light);
  }

  .chat-msg__user {
    white-space: pre-wrap;
    word-break: break-word;
  }

  .chat-msg__ai {
    white-space: pre-wrap;
    word-break: break-word;
  }

  .chat-msg__load {
    display: flex;
    gap: 6px;
    align-items: center;
    color: var(--el-text-color-secondary);
  }

  .chat-msg__err {
    color: var(--el-color-danger);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .chat-sub-title {
    margin: 10px 0 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-secondary);
  }

  .chat-sources {
    margin-top: 10px;

    .run-source-card {
      margin-bottom: 6px;
    }
  }

  .chat-trace {
    margin-top: 10px;
    border-top: 1px dashed var(--el-border-color-lighter);
    padding-top: 6px;
  }

  .trace-item {
    margin-bottom: 4px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 6px;
    background: #fff;

    .trace-item__head {
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 6px 8px;
      cursor: pointer;
      font-size: 12px;
    }

    .trace-item__chev {
      color: var(--el-text-color-secondary);
      font-size: 11px;
    }

    .trace-item__dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--el-color-info);
    }

    &.is-running .trace-item__dot {
      background: var(--el-color-primary);
    }
    &.is-success .trace-item__dot {
      background: var(--el-color-success);
    }
    &.is-error .trace-item__dot {
      background: var(--el-color-danger);
    }
    &.is-skipped .trace-item__dot {
      background: var(--el-color-info);
    }

    .trace-item__label {
      font-weight: 600;
    }

    .trace-item__status {
      margin-left: auto;
      color: var(--el-text-color-secondary);
    }

    .trace-item__err {
      color: var(--el-color-danger);
      font-size: 12px;
    }

    .trace-item__detail {
      padding: 6px 10px 10px;
      border-top: 1px dashed var(--el-border-color-lighter);

      .trace-item__kv {
        margin-top: 6px;

        .kv-t {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }

        .kv-b {
          margin: 4px 0 0;
          max-height: 150px;
          overflow: auto;
          font-size: 12px;
          white-space: pre-wrap;
          word-break: break-word;

          &.is-err {
            color: var(--el-color-danger);
          }
        }
      }
    }
  }
}

.chat-input {
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-light);

  .chat-vars {
    margin-bottom: 8px;
  }

  .chat-input__row {
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }
}

.debug-node-title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: 600;
}

.debug-result {
  margin-top: 12px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  .debug-result__title {
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-secondary);

    &.is-err {
      color: var(--el-color-danger);
    }
  }

  .debug-result__body {
    margin: 6px 0 0;
    max-height: 180px;
    overflow: auto;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-word;

    &.is-err {
      color: var(--el-color-danger);
    }
  }
}

.history-preview {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.history-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}

.compare-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.compare-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);

  .compare-label {
    font-weight: 600;
  }

  .compare-detail {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.history-detail {
  margin-top: 16px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;

  .history-detail__title {
    margin-bottom: 10px;
    font-weight: 600;
  }

  .history-detail__item {
    padding: 8px 0;
    border-top: 1px dashed var(--el-border-color-lighter);

    .hd-head {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .hd-label {
      font-weight: 600;
    }

    .hd-err {
      margin: 4px 0 0;
      color: var(--el-color-danger);
      font-size: 12px;
    }

    .hd-kv {
      margin-top: 4px;

      .hd-kv-t {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }

      .hd-pre {
        margin: 4px 0 0;
        max-height: 140px;
        overflow: auto;
        font-size: 12px;
        white-space: pre-wrap;
        word-break: break-word;
      }
    }
  }
}

.run-trace {
  margin-bottom: 12px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;

  .run-trace__title {
    margin-bottom: 8px;
    font-weight: 600;
  }

  .run-trace__list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .run-trace__item {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 6px 8px;
    font-size: 13px;
    background: #fff;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 6px;

    .run-trace__dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--el-color-info);
    }

    &.is-running .run-trace__dot {
      background: var(--el-color-primary);
      animation: wf-pulse 1s ease-in-out infinite;
    }
    &.is-success .run-trace__dot {
      background: var(--el-color-success);
    }
    &.is-error .run-trace__dot {
      background: var(--el-color-danger);
    }

    .run-trace__status {
      margin-left: auto;
      color: var(--el-text-color-secondary);
    }
    .run-trace__err {
      color: var(--el-color-danger);
      font-size: 12px;
    }
  }

  .run-trace__item {
    cursor: pointer;
    user-select: none;

    .run-trace__chev {
      color: var(--el-text-color-secondary);
      font-size: 11px;
    }
  }

  .run-trace__detail {
    margin: 4px 0 8px 20px;
    padding: 8px 10px;
    background: #fff;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 6px;

    .run-trace__kv {
      + .run-trace__kv {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px dashed var(--el-border-color-lighter);
      }

      .kv-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 12px;
        font-weight: 600;
        color: var(--el-text-color-secondary);

        .kv-copy {
          font-size: 12px;
        }
      }

      .kv-body {
        margin: 4px 0 0;
        max-height: 160px;
        overflow: auto;
        font-size: 12px;
        white-space: pre-wrap;
        word-break: break-word;

        &.is-err {
          color: var(--el-color-danger);
        }
      }
    }
  }
}

@keyframes wf-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.run-approval {
  margin-top: 12px;
  .run-approval__list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .run-approval__item {
    padding: 8px 10px;
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-light);
    border-radius: 6px;
  }

  .run-approval__name {
    display: flex;
    gap: 6px;
    align-items: center;
    font-weight: 600;
  }

  .run-approval__args {
    margin: 6px 0 0;
    font-size: 12px;
    color: var(--el-text-color-regular);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .run-approval__actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }

  .run-approval__hint {
    margin-top: 8px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.run-sources {
  margin-top: 12px;

  .run-sources__title {
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 600;
  }

  .run-sources__list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 220px;
    overflow: auto;
  }
}

.run-source-card {
  border-radius: 8px;

  :deep(.el-card__body) {
    padding: 10px 12px;
  }

  .run-source-card__head {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
    font-size: 13px;
  }

  .run-source-card__title {
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .run-source-card__content {
    font-size: var(--el-font-size-base);
    line-height: 1.5;
    color: var(--el-text-color-regular);
  }
}
</style>

<style lang="scss">
/* 非 scoped：修复 Vue Flow 画布光标消失，并让节点可交互表达更清晰 */
.ai-workflow-editor {
  .vue-flow__pane {
    cursor: default;
  }

  .vue-flow__pane.dragging {
    cursor: grabbing;
  }

  .vue-flow__node {
    cursor: pointer;
  }

  .vue-flow__edge-path {
    cursor: pointer;
  }
}
</style>
