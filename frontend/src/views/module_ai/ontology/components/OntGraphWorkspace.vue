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
    <div class="ont-gw__canvas">
      <GraphCanvas
        v-if="nodes.length"
        :key="layout"
        ref="graphRef"
        :nodes="nodes"
        :edges="edges"
        height="100%"
        :layout-name="layout"
        :node-style="{ sizeMode: 'weight', shapeMode: 'uniform', uniformShape: 'round-rectangle', labelSize: 12 }"
        :edge-style="{ label: 'show', colorMode: 'type', arrow: 'triangle', opacity: 0.75 }"
        @node-tap="onNodeTap"
      />
      <el-empty
        v-else
        :image-size="70"
        description="该本体暂无对象类型，右键点空白处新建"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { FullScreen, Search, ZoomIn, ZoomOut } from "@element-plus/icons-vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import { useOntologyData } from "../composables/useOntologyData";
import { buildOntGraph } from "../graph";

const emit = defineEmits<{
  (e: "node-tap", objectCode: string): void;
  (e: "link-draw", sourceCode: string, targetCode: string): void;
}>();

const { scopedObjects, scopedLinks } = useOntologyData();

const graphRef = ref<any>(null);
const layout = ref("cose");
const onlyConnected = ref(false);
const search = ref("");

const nodes = computed(() => buildOntGraph(scopedObjects.value, scopedLinks.value, { onlyConnected: onlyConnected.value }).nodes);
const edges = computed(() => buildOntGraph(scopedObjects.value, scopedLinks.value, { onlyConnected: onlyConnected.value }).edges);

function onNodeTap(name: string) {
  const hit = scopedObjects.value.find((o: any) => o.name === name || String(name).startsWith(o.name));
  if (hit) emit("node-tap", hit.code);
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
}
</style>
