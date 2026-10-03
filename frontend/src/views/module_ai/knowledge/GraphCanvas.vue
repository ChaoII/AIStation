<template>
  <div ref="container" class="graph-canvas" />
</template>

<script setup lang="ts">
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { onMounted, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  nodes: {
    id: number;
    name: string;
    etype?: string;
    weight?: number;
    chunk_count?: number;
    x?: number | null;
    y?: number | null;
  }[];
  edges: { source: string; target: string; rtype?: string; weight?: number }[];
  // preset=true 用记忆坐标；否则库可自由布局（但仍可让用户拖动）
  usePreset?: boolean;
  // 检索定位高亮节点名
  highlight?: string[];
}>();

const emit = defineEmits<{
  (e: "node-tap", name: string): void;
  (e: "node-ctx", name: string, x: number, y: number): void;
  (e: "edge-ctx", source: string, target: string, x: number, y: number): void;
  (e: "blank-ctx", x: number, y: number): void;
  (e: "layout", items: { id: number; x: number; y: number }[]): void;
}>();

const container = ref<HTMLDivElement>();
let cy: Core | null = null;

function colorFor(etype?: string, hasChunk = false) {
  if (hasChunk) return "#e6a23c";
  if (etype === "custom") return "#67c23a";
  if (etype === "annotation") return "#e6a23c";
  if (etype === "keyword" || !etype) return "#409eff";
  return "#909399";
}
function edgeColor(rtype?: string) {
  const map: Record<string, string> = {
    属于: "#67c23a",
    包含: "#409eff",
    依赖: "#e6a23c",
    相关: "#a0a6ad",
    引用: "#909399",
    位于: "#2f7ccc",
    用于: "#c0700f",
    关联: "#e6a23c",
  };
  return map[rtype || ""] || "#a0a6ad";
}

function buildElements(): ElementDefinition[] {
  const nodes = props.nodes.map((n) => ({
    data: {
      id: String(n.name),
      label: n.chunk_count ? `${n.name} (${n.chunk_count})` : n.name,
      name: n.name,
      etype: n.etype || "keyword",
      weight: n.weight || 1,
      chunk_count: n.chunk_count || 0,
    },
    position: n.x != null && n.y != null ? { x: n.x, y: n.y } : undefined,
  }));
  const edges = props.edges.map((e, i) => ({
    data: {
      id: `e_${i}`,
      source: String(e.source),
      target: String(e.target),
      label: e.rtype || "",
      rtype: e.rtype || "",
      weight: e.weight || 1,
    },
  }));
  return [...nodes, ...edges];
}

const graphStyle: any[] = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": 12,
      color: "#303133",
      "text-valign": "bottom",
      "text-margin-y": 4,
      width: 16,
      height: 16,
      "background-color": (ele: any) => colorFor(ele.data("etype"), ele.data("chunk_count") > 0),
      "border-width": 2,
      "border-color": "#fff",
    },
  },
  {
    selector: "edge",
    style: {
      width: 2,
      "line-color": (ele: any) => edgeColor(ele.data("rtype")),
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      "curve-style": "bezier",
      label: "data(label)",
      "font-size": 9,
      color: "#909399",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.8,
      "text-background-padding": 2,
    },
  },
  // 选中态 / 检索高亮
  {
    selector: "node:selected",
    style: { "border-width": 5, "border-color": "#67c23a" },
  },
  {
    selector: "node.highlight",
    style: { "border-width": 5, "border-color": "#f5b942", "background-color": "#f5b942" },
  },
];

function runLayout() {
  const c = cy;
  if (!c) return;
  const preset = props.usePreset && props.nodes.every((n) => n.x != null && n.y != null);
  c.layout({
    name: preset ? "preset" : "cose",
    animate: !preset,
    padding: 20,
    fit: true,
    // cose 碰撞避免/力导向（greedy 使节点尽量不重叠）
    ...(preset ? {} : { nodeRepulsion: 12000, idealEdgeLength: 80, gravity: 0.2, numIter: 1000 }),
  }).run();
}

function emitPositions() {
  const c = cy;
  if (!c) return;
  const items = c.nodes().map((n) => ({
    id: Number(n.data("name")),
    x: n.position("x"),
    y: n.position("y"),
  }));
  emit("layout", items as any);
}

function bind() {
  const c = cy;
  if (!c) return;
  c.on("tap", "node", (e) => {
    const name = e.target.data("name") as string;
    emit("node-tap", name);
  });
  c.on("cxttap", "node", (e) => {
    e.preventDefault();
    const rp = e.renderedPosition || e.position;
    emit("node-ctx", e.target.data("name") as string, rp.x, rp.y);
  });
  c.on("cxttap", "edge", (e) => {
    e.preventDefault();
    const d = e.target.data();
    const rp = e.renderedPosition || e.position;
    emit("edge-ctx", String(d.source), String(d.target), rp.x, rp.y);
  });
  c.on("cxttap", (e) => {
    if (e.target === c) {
      e.preventDefault();
      const rp = e.renderedPosition;
      emit("blank-ctx", rp.x, rp.y);
    }
  });
}

function applyElements() {
  const c = cy;
  if (!c) return;
  c.elements().remove();
  c.add(buildElements());
  runLayout();
}

onMounted(() => {
  cy = cytoscape({
    container: container.value,
    elements: buildElements(),
    style: graphStyle,
    layout: { name: "cose", animate: false, fit: true, padding: 20 },
  });
  bind();
  runLayout();
});

watch(
  () => [props.nodes, props.edges],
  () => applyElements(),
  { deep: true }
);
watch(
  () => props.highlight,
  (hl) => {
    const c = cy;
    if (!c) return;
    c.nodes().removeClass("highlight");
    (hl || []).forEach((n) => {
      const node = c.getElementById(String(n));
      if (node.length) node.addClass("highlight");
    });
  }
);

function png(): string {
  if (!cy) return "";
  return (cy.png as any)({ output: "dataurl", full: true, scale: 2 }) as string;
}

defineExpose({ emitPositions, png });

onBeforeUnmount(() => {
  cy?.destroy();
  cy = null;
});
</script>
