<!--
  本体图谱工作区（cytoscape）
  节点 = 对象类型（按所属本体上色），边 = 关系类型（按关系名上色、平滑曲线、线宽随量化）。
  工具条：搜索 / 布局 / 物理模式 / 主题 / 重排 / 缩放适配 / 导出图片 / 多选 / 最短路径，
  以及一排「维护面板」图标按钮（索引/提案/场景/决策/对象探索/对象类型组/值类型/共享属性/接口）。
  点节点 → node-tap 上抛父级弹对象详情抽屉。
-->
<template>
  <div class="ont-gw">
    <!-- 工具条 -->
    <div class="ont-gw__bar">
      <el-input
        v-model="search"
        size="small"
        placeholder="搜索对象类型"
        clearable
        :prefix-icon="Search"
        class="ont-gw__search"
        @input="doSearch"
      />
      <el-select v-model="layout" size="small" class="ont-gw__layout">
        <el-option label="力导向" value="cose" />
        <el-option label="同心布局" value="concentric" />
        <el-option label="树形布局" value="breadthfirst" />
        <el-option label="网格布局" value="grid" />
        <el-option label="环形布局" value="circle" />
      </el-select>
      <el-select v-model="theme" size="small" class="ont-gw__theme">
        <el-option v-for="t in THEME_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-checkbox v-model="onlyConnected" size="small" class="ont-gw__connected">
        只显示有关联
      </el-checkbox>
      <el-switch v-model="physicsMode" size="small" active-text="物理" />
      <el-switch
        v-model="shortestMode"
        size="small"
        active-text="最短路径"
        @change="onModeChange"
      />
      <el-switch v-model="multiSelect" size="small" active-text="多选" @change="onModeChange" />
      <el-button-group size="small">
        <el-button :icon="Refresh" title="重新布局" @click="relayout" />
        <el-button :icon="FullScreen" title="适合页面" @click="graphRef?.fit()" />
        <el-button :icon="Aim" title="居中" @click="graphRef?.center?.()" />
        <el-button :icon="ZoomIn" title="放大" @click="graphRef?.zoom(1.25)" />
        <el-button :icon="ZoomOut" title="缩小" @click="graphRef?.zoom(0.8)" />
        <el-button :icon="Download" title="导出图片" @click="exportImage" />
      </el-button-group>
      <el-button
        v-if="multiSelect && selectedNames.length"
        v-hasPerm="'module_ai:ontology:edit'"
        size="small"
        type="danger"
        plain
        @click="batchDelete"
      >
        批量删除{{ selectedNames.length ? ` (${selectedNames.length})` : "" }}
      </el-button>
      <el-button v-if="multiSelect && selectedNames.length" size="small" @click="clearSelection">
        清空选择
      </el-button>
      <el-tag size="small" type="info" effect="plain">
        {{ nodes.length }} 类型 / {{ edges.length }} 关系
      </el-tag>

      <!-- 维护面板图标按钮 -->
      <div class="ont-gw__maint">
        <el-tooltip v-for="m in MAINT_ITEMS" :key="m.panel" :content="m.label" placement="bottom">
          <el-button
            size="small"
            :icon="m.icon"
            class="ont-gw__maint-btn"
            @click="emit('maintain', m.panel)"
          />
        </el-tooltip>
      </div>
    </div>

    <!-- 图谱 -->
    <div class="ont-gw__canvas" @click="closeCtx" @contextmenu.prevent>
      <GraphCanvas
        v-if="nodes.length"
        :key="layout"
        ref="graphRef"
        :nodes="nodes"
        :edges="edges"
        height="100%"
        link-mode
        :layout-name="layout"
        :physics-mode="physicsMode"
        :shortest-mode="shortestMode"
        :theme="theme"
        :highlight="highlightNodes"
        :node-style="{
          sizeMode: 'weight',
          shapeMode: 'uniform',
          uniformShape: 'round-rectangle',
          labelSize: 12,
          colorMode: 'category',
        }"
        :edge-style="{
          label: 'show',
          colorMode: 'category',
          curve: 'bezier',
          arrow: 'triangle',
          widthMode: 'weight',
          opacity: 0.8,
        }"
        @node-tap="onNodeTap"
        @link-draw="onLinkDraw"
        @edge-ctx="onEdgeCtx"
        @node-ctx="onNodeCtx"
        @blank-ctx="onBlankCtx"
        @path-found="onPathFound"
      />
      <el-empty v-else :image-size="70" description="该本体暂无对象类型，右键点空白处新建" />

      <!-- 右键菜单（**全部是写操作**：编辑/物化/删除/新建 ⇒ 需 edit 权限；
           只读用户看不到这个菜单，也不会点到会 403 的入口） -->
      <div
        v-if="ctxMenu.visible"
        v-hasPerm="'module_ai:ontology:edit'"
        class="ont-gw__ctx"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
        @contextmenu.prevent
      >
        <template v-if="ctxMenu.kind === 'node'">
          <div class="ont-gw__ctx-item" @click="ctxEdit">编辑元数据</div>
          <div class="ont-gw__ctx-item" @click="ctxMaterialize">物化为表</div>
          <div class="ont-gw__ctx-item ont-gw__ctx-danger" @click="ctxDelete">删除对象类型</div>
        </template>
        <template v-else>
          <div class="ont-gw__ctx-item" @click="ctxCreate">新建对象类型</div>
        </template>
      </div>
    </div>

    <!-- 多选提示条 -->
    <div v-if="multiSelect && selectedNames.length" class="ont-gw__selbar">
      已选 {{ selectedNames.length }} 个对象类型（可批量删除 / 清空）
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import {
  Aim,
  Collection,
  DataLine,
  Download,
  Files,
  FolderOpened,
  FullScreen,
  Guide,
  Link,
  Operation,
  Refresh,
  Search,
  Share,
  Tickets,
  ZoomIn,
  ZoomOut,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import { useOntologyData } from "../composables/useOntologyData";
import { buildOntGraph } from "../graph";

const emit = defineEmits<{
  (e: "node-tap", objectCode: string): void;
  (e: "link-draw", sourceCode: string, targetCode: string): void;
  (e: "edge-ctx", sourceCode: string, targetCode: string): void;
  (e: "create-object"): void;
  (e: "edit-object", objectCode: string): void;
  (e: "delete-object", objectCode: string): void;
  (e: "materialize-object", objectCode: string): void;
  (e: "maintain", panel: string): void;
  (e: "batch-delete", objectCodes: string[]): void;
}>();

const { scopedObjects, scopedLinks } = useOntologyData();

const graphRef = ref<any>(null);
const layout = ref("cose");
const theme = ref("default");
const onlyConnected = ref(false);
const physicsMode = ref(false);
const shortestMode = ref(false);
const multiSelect = ref(false);
const search = ref("");

const THEME_OPTIONS = [
  { label: "默认", value: "default" },
  { label: "海洋", value: "ocean" },
  { label: "森林", value: "forest" },
  { label: "落日", value: "sunset" },
  { label: "单色", value: "mono" },
];

/** 维护面板入口：图标 + 面板键 + 标签 */
const MAINT_ITEMS = [
  { label: "索引", panel: "index", icon: Collection },
  { label: "提案", panel: "proposals", icon: Files },
  { label: "场景", panel: "scenarios", icon: Tickets },
  { label: "决策", panel: "decisions", icon: Operation },
  { label: "对象探索", panel: "explore", icon: Guide },
  { label: "对象类型组", panel: "groups", icon: FolderOpened },
  { label: "值类型", panel: "valueTypes", icon: DataLine },
  { label: "共享属性", panel: "shared", icon: Share },
  { label: "接口", panel: "interfaces", icon: Link },
];

const graph = computed(() =>
  buildOntGraph(scopedObjects.value, scopedLinks.value, { onlyConnected: onlyConnected.value })
);
const nodes = computed(() => graph.value.nodes);
const edges = computed(() => graph.value.edges);
/** 图谱节点显示名 → 对象编码 */
const codeByName = computed(() => {
  const m: Record<string, string> = {};
  graph.value.nodes.forEach((n) => {
    m[n.name] = n.objectCode;
  });
  return m;
});

/** 多选：选中节点名集合（高亮） */
const selectedNames = ref<string[]>([]);
const highlightNodes = computed(() => [...selectedNames.value]);

/** 右键菜单状态 */
const ctxMenu = reactive({
  visible: false,
  kind: "blank" as "blank" | "node",
  x: 0,
  y: 0,
  code: "",
});

function onModeChange() {
  // 多选与最短路径互斥：都开启会抢「点节点」语义
  if (shortestMode.value && multiSelect.value) multiSelect.value = false;
  if (multiSelect.value && shortestMode.value) shortestMode.value = false;
  clearSelection();
}

function onNodeTap(name: string) {
  if (multiSelect.value) {
    toggleSelect(name);
    return;
  }
  const code = codeByName.value[name];
  if (code) emit("node-tap", code);
}
function onPathFound(a: string, b: string, length: number) {
  if (length < 0) ElMessage.info(`「${a}」与「${b}」之间未找到路径`);
  else ElMessage.success(`最短路径：${a} → ${b}，${length} 跳`);
}
function onLinkDraw(sourceName: string, targetName: string) {
  const s = codeByName.value[sourceName];
  const t = codeByName.value[targetName];
  if (s && t) emit("link-draw", s, t);
}
function onEdgeCtx(sourceName: string, targetName: string) {
  const s = codeByName.value[sourceName];
  const t = codeByName.value[targetName];
  if (s && t) {
    ctxMenu.visible = false;
    emit("edge-ctx", s, t);
  }
}
function onNodeCtx(name: string, x: number, y: number) {
  ctxMenu.kind = "node";
  ctxMenu.code = codeByName.value[name] || "";
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function onBlankCtx(x: number, y: number) {
  ctxMenu.kind = "blank";
  ctxMenu.code = "";
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function closeCtx() {
  ctxMenu.visible = false;
}
function ctxEdit() {
  closeCtx();
  if (ctxMenu.code) emit("edit-object", ctxMenu.code);
}
function ctxDelete() {
  closeCtx();
  if (ctxMenu.code) emit("delete-object", ctxMenu.code);
}
function ctxMaterialize() {
  closeCtx();
  if (ctxMenu.code) emit("materialize-object", ctxMenu.code);
}
function ctxCreate() {
  closeCtx();
  emit("create-object");
}

function toggleSelect(name: string) {
  const idx = selectedNames.value.indexOf(name);
  if (idx >= 0) selectedNames.value.splice(idx, 1);
  else selectedNames.value.push(name);
}
function clearSelection() {
  selectedNames.value = [];
}
function batchDelete() {
  const codes = selectedNames.value.map((n) => codeByName.value[n]).filter((c): c is string => !!c);
  emit("batch-delete", codes);
}
function relayout() {
  // 换 key 触发重排（layout 相同也重新布局）
  graphRef.value?.setLayout?.(layout.value);
}
function exportImage() {
  const url = graphRef.value?.png?.();
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = `本体图谱.png`;
  a.click();
  ElMessage.success("已导出图片");
}

let searchTimer: any = null;
function doSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  const q = (search.value || "").trim();
  searchTimer = setTimeout(() => {
    graphRef.value?.search(q);
  }, 200);
}

defineExpose({ graphRef });
</script>

<style scoped lang="scss">
.ont-gw {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
}
.ont-gw__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ont-gw__search {
  width: 200px;
}
.ont-gw__layout {
  width: 120px;
}
.ont-gw__theme {
  width: 96px;
}
.ont-gw__maint {
  display: flex;
  gap: 4px;
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--el-border-color-light);
}
.ont-gw__maint-btn {
  padding: 4px 7px;
}
.ont-gw__canvas {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  position: relative;
}
.ont-gw__ctx {
  position: absolute;
  z-index: 20;
  min-width: 150px;
  padding: 4px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
  box-shadow: var(--el-box-shadow-light);
}
.ont-gw__ctx-item {
  padding: 6px 12px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  border-radius: var(--el-border-radius-base);
  cursor: pointer;
  user-select: none;
}
.ont-gw__ctx-item:hover {
  background: var(--el-fill-color-light);
}
.ont-gw__ctx-danger {
  color: var(--el-color-danger);
}
.ont-gw__ctx-danger:hover {
  background: var(--el-color-danger-light-9);
}
.ont-gw__selbar {
  margin-top: 6px;
  padding: 4px 10px;
  font-size: var(--el-font-size-base);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: var(--el-border-radius-base);
}
</style>
