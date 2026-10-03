<!-- 工作流 DAG 拓扑只读总览 -->
<template>
  <div class="topo-view">
    <VueFlow
      :nodes="topoNodes"
      :edges="topoEdges"
      :nodes-draggable="false"
      :nodes-connectable="false"
      :elements-selectable="false"
      :min-zoom="0.2"
      :max-zoom="2"
      :default-viewport="{ zoom: 1 }"
    >
      <Background pattern-color="#aaa" :gap="16" />
      <MiniMap pannable zoomable />
      <Controls />
      <Panel position="top-right" class="topo-info">
        {{ topoNodes.length }} 节点 · {{ topoEdges.length }} 连线
      </Panel>
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { VueFlow, Panel, type Node, type Edge } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { MiniMap } from "@vue-flow/minimap";
import { Controls } from "@vue-flow/controls";
import { nodeDefOf } from "../nodes";

const props = defineProps<{ nodes?: Node[]; edges?: Edge[] }>();

const topoNodes = computed<any[]>(() =>
  (props.nodes || []).map((n) => ({
    id: n.id,
    type: "default",
    position: n.parentNode
      ? {
          x: (n.position?.x ?? 0) + (topoNodeX(n.parentNode) ?? 0),
          y: (n.position?.y ?? 0) + (topoNodeY(n.parentNode) ?? 0),
        }
      : { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
    data: { label: nodeDefOf(n.type || "llm").label + (n.data?.title ? ` · ${n.data.title}` : "") },
    ...(!n.parentNode ? {} : {}),
  }))
);
const topoEdges = computed<any[]>(() =>
  (props.edges || []).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: true,
  }))
);
function topoNodeX(id: string): number | undefined {
  return (props.nodes || []).find((n) => n.id === id)?.position?.x;
}
function topoNodeY(id: string): number | undefined {
  return (props.nodes || []).find((n) => n.id === id)?.position?.y;
}
</script>

<style scoped lang="scss">
.topo-view {
  width: 100%;
  height: 100%;
  background: #fff;
}
.topo-info {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
