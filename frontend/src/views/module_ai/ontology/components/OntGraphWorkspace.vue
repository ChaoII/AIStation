<!--
  本体图谱工作区（cytoscape）
  节点 = 对象类型，边 = 关系类型；工具条含布局/搜索/筛选/缩放适配。
  点节点 → 上抛 node-tap 给父级弹对象详情抽屉。
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
      <el-checkbox v-model="onlyConnected" size="small" class="ont-gw__connected">
        只显示有关联
      </el-checkbox>
      <el-button-group size="small">
        <el-button :icon="ZoomIn" title="放大" @click="graphRef?.zoom(1.25)" />
        <el-button :icon="ZoomOut" title="缩小" @click="graphRef?.zoom(0.8)" />
        <el-button :icon="FullScreen" title="适配画布" @click="graphRef?.fit()" />
      </el-button-group>
      <el-tag size="small" type="info" effect="plain">
        {{ nodes.length }} 类型 / {{ edges.length }} 关系
      </el-tag>
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
        :node-style="{ sizeMode: 'weight', shapeMode: 'uniform', uniformShape: 'round-rectangle', labelSize: 12 }"
        :edge-style="{ label: 'show', colorMode: 'type', arrow: 'triangle', opacity: 0.75 }"
        @node-tap="onNodeTap"
        @link-draw="onLinkDraw"
        @edge-ctx="onEdgeCtx"
        @node-ctx="onNodeCtx"
        @blank-ctx="onBlankCtx"
      />
      <el-empty
        v-else
        :image-size="70"
        description="该本体暂无对象类型，右键点空白处新建"
      />

      <!-- 右键菜单 -->
      <div
        v-if="ctxMenu.visible"
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
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { FullScreen, Search, ZoomIn, ZoomOut } from "@element-plus/icons-vue";
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
}>();

const { scopedObjects, scopedLinks } = useOntologyData();

const graphRef = ref<any>(null);
const layout = ref("cose");
const onlyConnected = ref(false);
const search = ref("");

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

/** 右键菜单状态 */
const ctxMenu = reactive({ visible: false, kind: "blank" as "blank" | "node", x: 0, y: 0, code: "" });

function onNodeTap(name: string) {
  const code = codeByName.value[name];
  if (code) emit("node-tap", code);
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
  margin-bottom: 8px;
}
.ont-gw__search {
  width: 220px;
}
.ont-gw__layout {
  width: 130px;
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
</style>
