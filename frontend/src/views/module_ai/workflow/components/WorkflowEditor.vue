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
              </el-form>
            </div>
            <el-divider style="margin: 4px 0" />
            <div class="panel-section">
              <div class="section-title">节点</div>
              <div class="palette-tip">点击或拖拽节点到画布</div>
              <el-space direction="vertical" :size="8" fill style="width: 100%">
                <div
                  v-for="def in NODE_DEFS"
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

    <!-- 运行调试弹窗 -->
    <el-dialog
      v-model="runVisible"
      title="运行调试"
      width="560px"
      append-to-body
      class="ai-run-dialog"
    >
      <el-form label-position="top" size="small">
        <el-form-item label="测试输入（用户消息）">
          <el-input v-model="runInput" type="textarea" :rows="2" placeholder="输入一条测试消息" />
        </el-form-item>
        <el-form-item label="变量（JSON，可选）">
          <el-input
            v-model="runVariables"
            type="textarea"
            :rows="3"
            placeholder='如 {"query":"你好"}'
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="runApproval"
        type="warning"
        :closable="false"
        title="需要工具调用审批"
        class="run-approval"
      >
        <div class="run-approval__list">
          <div v-for="t in runApproval.toolCalls" :key="t.toolCallId" class="run-approval__item">
            <div class="run-approval__name">
              <el-icon><Tools /></el-icon>
              <span>{{ t.toolName }}</span>
            </div>
            <pre class="run-approval__args">{{ JSON.stringify(t.arguments, null, 2) }}</pre>
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
        <div class="run-approval__hint">审批会话约 30 分钟内有效，超时后需重新运行工作流。</div>
      </el-alert>
      <div v-if="runSources.length" class="run-sources">
        <div class="run-sources__title">引用来源</div>
        <div class="run-sources__list">
          <el-card v-for="(s, i) in runSources" :key="i" class="run-source-card" shadow="never">
            <div class="run-source-card__head">
              <el-icon><Document /></el-icon>
              <span class="run-source-card__title">{{ s.title }}</span>
              <el-tag v-if="s.score != null" size="small" type="info">相似度 {{ s.score }}</el-tag>
            </div>
            <div class="run-source-card__content">{{ s.content }}</div>
          </el-card>
        </div>
      </div>
      <div v-if="runOutput" class="run-output">
        <div class="run-output__title">输出</div>
        <div class="run-output__body">{{ runOutput }}</div>
      </div>
      <template #footer>
        <el-button @click="runVisible = false">关闭</el-button>
        <el-button type="primary" :loading="running" @click="handleRun">开始运行</el-button>
      </template>
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
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="doPublish(row)">发布</el-button>
            <el-button link type="warning" size="small" @click="doRollback(row)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
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
  CircleCheckFilled,
} from "@element-plus/icons-vue";
import dagre from "dagre";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

import WorkflowNode from "./WorkflowNode.vue";
import NodeConfigPanel from "./NodeConfigPanel.vue";
import { NODE_DEFS, nodeDefOf, type WorkflowNodeType } from "../nodes";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiToolList } from "@/api/module_ai/tool";
import {
  createAiWorkflow,
  updateAiWorkflow,
  saveAiWorkflowVersion,
  listAiWorkflowVersions,
  rollbackAiWorkflowVersion,
  publishAiWorkflowVersion,
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
onConnect((conn) => {
  pushHistory();
  addEdges({ ...conn, type: defaultEdgeOptions.type, animated: true });
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
const runOutput = ref("");
const runSources = ref<any[]>([]);
const runApproval = ref<{ run_id: string; toolCalls: any[] } | null>(null);
const approving = ref(false);
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
    case "end":
      return { output_template: "" };
    default:
      return {};
  }
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
  runOutput.value = "";
  runSources.value = [];
  runApproval.value = null;
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

async function handleRun() {
  if (!workflowId.value) {
    // 未保存：先保存再运行
    await handleSave();
    if (!workflowId.value) return;
  }
  running.value = true;
  runApproval.value = null;
  runOutput.value = "运行中...";
  try {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    let variables = {};
    try {
      variables = runVariables.value ? JSON.parse(runVariables.value) : {};
    } catch {
      variables = {};
    }
    const body = {
      messages: [{ role: "user", parts: [{ type: "text", text: runInput.value || "你好" }] }],
      variables,
    };
    const resp = await fetch(`${base}/ai/workflows/${workflowId.value}/run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${Auth.getAccessToken() || ""}`,
      },
      body: JSON.stringify(body),
    });
    if (!resp.ok || !resp.body) {
      runOutput.value = `请求失败：${resp.status}`;
      return;
    }
    let out = "";
    await readUiStream(resp, (obj) => {
      if (obj.type === "text-delta") out += obj.text;
      else if (obj.type === "sources") runSources.value = obj.sources || [];
      else if (obj.type === "data-finish") {
        if (obj.awaiting_approval && obj.run_id) {
          runApproval.value = { run_id: obj.run_id, toolCalls: obj.pending_tool_calls || [] };
        }
        out = obj.reply || out;
      }
    });
    runOutput.value = out || "(无输出)";
  } catch (e: any) {
    runOutput.value = `运行失败：${e?.message || e}`;
  } finally {
    running.value = false;
  }
}

async function handleApprove(decision: "approve" | "reject") {
  if (!runApproval.value || !workflowId.value) return;
  const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
  const runId = runApproval.value.run_id;
  approving.value = true;
  const prior =
    runOutput.value === "运行中..." || runOutput.value === "(无输出)" ? "" : runOutput.value;
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
      runOutput.value = `审批请求失败：${resp.status}`;
      return;
    }
    let out = prior;
    let errMsg = "";
    await readUiStream(resp, (obj) => {
      if (obj.type === "text-delta") out += obj.text;
      else if (obj.type === "data-finish") out = obj.reply || out;
      else if (obj.type === "error") errMsg = obj.errorText || obj.msg || obj.message || "";
    });
    if (errMsg) {
      runOutput.value = `审批失败：${errMsg}`;
      return;
    }
    runOutput.value = out || "(无输出)";
  } catch (e: any) {
    runOutput.value = `审批续跑失败：${e?.message || e}`;
  } finally {
    approving.value = false;
    runApproval.value = null;
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
