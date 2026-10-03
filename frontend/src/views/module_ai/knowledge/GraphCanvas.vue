<template>
  <div class="graph-canvas-wrap" :style="{ height: heightStyle }">
    <div ref="container" class="graph-canvas" />
    <div
      v-if="tooltip.show"
      class="graph-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
      v-html="tooltip.html"
    />
  </div>
</template>

<script setup lang="ts">
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";

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
  usePreset?: boolean;
  highlight?: string[];
  height?: string;
  layoutName?: string;
  linkMode?: boolean;
}>();

const emit = defineEmits<{
  (e: "node-tap", name: string): void;
  (e: "node-dbltap", name: string): void;
  (e: "node-ctx", name: string, x: number, y: number): void;
  (e: "edge-ctx", source: string, target: string, x: number, y: number): void;
  (e: "blank-ctx", x: number, y: number): void;
  (e: "layout", items: { id: number; x: number; y: number }[]): void;
  (e: "link-draw", source: string, target: string): void;
}>();

const container = ref<HTMLDivElement>();
const heightStyle = computed(() => props.height || "480px");
const tooltip = ref({ show: false, x: 0, y: 0, html: "" });
let cy: Core | null = null;
// 拖拽建边状态
let dragSource: any = null;
let dragTarget: any = null;
const dragTmpId = "tmp_target";
const dragEdgeId = "tmp_edge";

function colorFor(etype?: string, hasChunk = false) {
  if (hasChunk) return "#f7a733";
  if (etype === "custom") return "#5ac66b";
  if (etype === "annotation") return "#f7a733";
  if (etype === "keyword" || !etype) return "#4a86f7";
  return "#a0a6ad";
}
function edgeColor(rtype?: string) {
  const map: Record<string, string> = {
    属于: "#5ac66b",
    包含: "#4a86f7",
    依赖: "#f7a733",
    相关: "#a8abb3",
    引用: "#7f8fa6",
    位于: "#3f9ad6",
    用于: "#e6b455",
    关联: "#f7a733",
  };
  return map[rtype || ""] || "#a8abb3";
}
function nodeSize(weight?: number) {
  return 14 + Math.min(weight || 1, 20) * 1.2;
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
      color: "#2f3542",
      "text-valign": "bottom",
      "text-margin-y": 5,
      "text-wrap": "wrap",
      "text-max-width": 120,
      width: (ele: any) => nodeSize(ele.data("weight")),
      height: (ele: any) => nodeSize(ele.data("weight")),
      shape: (ele: any) => {
        const t = ele.data("etype");
        if (t === "annotation") return "round-rectangle";
        if (t === "custom") return "diamond";
        return "ellipse";
      },
      "background-color": (ele: any) => colorFor(ele.data("etype"), ele.data("chunk_count") > 0),
      "border-width": 2,
      "border-color": "#ffffff",
      "shadow-blur": 8,
      "shadow-color": "rgba(31,45,61,0.16)",
      "shadow-offset-x": 0,
      "shadow-offset-y": 2,
      "min-zoomed-font-size": 6,
    },
  },
  {
    selector: "edge",
    style: {
      width: (ele: any) => 1.5 + Math.min(ele.data("weight") || 1, 5) * 0.6,
      "line-color": (ele: any) => edgeColor(ele.data("rtype")),
      "curve-style": "bezier",
      "target-arrow-shape": "triangle",
      "target-arrow-color": (ele: any) => edgeColor(ele.data("rtype")),
      "arrow-scale": 0.9,
      label: (ele: any) => ((ele.data("rtype") || "") === "related" ? "" : ele.data("label")),
      "font-size": 9,
      color: "#7f8fa6",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.9,
      "text-background-padding": 3,
      "text-rotation": "autorotate",
      opacity: 0.75,
    },
  },
  // 悬停节点放大 + 高亮描边
  {
    selector: "node.hovered",
    style: {
      "border-width": 3,
      "border-color": "#4a86f7",
    },
  },
  {
    selector: "node.dim",
    style: { opacity: 0.25 },
  },
  {
    selector: "edge.dim",
    style: { opacity: 0.05 },
  },
  {
    selector: "edge.hovered",
    style: { opacity: 1, width: 3, "line-color": "#409eff" },
  },
  {
    selector: "node:selected",
    style: { "border-width": 5, "border-color": "#67c23a" },
  },
  {
    selector: "node.highlight",
    style: { "border-width": 5, "border-color": "#f5b942", "background-color": "#f5b942" },
  },
  {
    selector: "node.dragging",
    style: { "border-width": 4, "border-color": "#f56c6c" },
  },
  {
    selector: "node.tmp-node",
    style: { opacity: 0.6, width: 10, height: 10, "background-color": "#f56c6c" },
  },
  {
    selector: "edge.tmp-edge",
    style: { width: 2, "line-color": "#f56c6c", "target-arrow-shape": "none", opacity: 0.7 },
  },
];

function runLayout() {
  const c = cy;
  if (!c) return;
  const preset = props.usePreset && props.nodes.every((n) => n.x != null && n.y != null);
  const name = (props.layoutName || "cose") as string;
  const base = { animate: true, animationDuration: 500, fit: true, padding: 30 };
  const opts: any = { ...base };
  if (preset && name === "cose") opts.name = "preset";
  else opts.name = name;
  if (name === "cose") {
    opts.nodeRepulsion = 40000;
    opts.idealEdgeLength = 110;
    opts.gravity = 0.35;
    opts.numIter = 2500;
    opts.nodeOverlap = 20;
    opts.spacingFactor = 1.2;
  }
  if (name === "concentric") opts.minNodeSpacing = 26;
  if (name === "breadthfirst") opts.spacingFactor = 1.2;
  if (name === "grid") opts.avoidOverlap = true;
  c.layout(opts).run();
}
function setLayout(name: string) {
  const c = cy;
  if (!c) return;
  c.layout({
    name,
    animate: true,
    animationDuration: 400,
    fit: true,
    padding: 30,
  } as any).run();
}
function fit() {
  cy?.fit(undefined, 30);
}
function center() {
  cy?.center();
}
function zoom(level: number) {
  if (!cy) return;
  cy.zoom(cy.zoom() * level);
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

function resetDim() {
  const c = cy;
  if (!c) return;
  c.elements().removeClass("dim");
}
function showTooltip(html: string, x: number, y: number) {
  tooltip.value = { show: true, x, y, html };
}
function hideTooltip() {
  tooltip.value = { show: false, x: 0, y: 0, html: "" };
}

function bind() {
  const c = cy;
  if (!c) return;
  // 悬停节点：放大 + 邻接高亮 + tooltip
  c.on("mouseover", "node", (e) => {
    const node = e.target;
    node.addClass("hovered");
    const nb = node.neighborhood();
    // 非邻接变暗
    const others = c.nodes().difference(nb.union(node));
    others.addClass("dim");
    const edges = c.edges().difference(nb.edges());
    edges.addClass("dim");
    const pos = node.renderedPosition();
    showTooltip(
      `<b>${node.data("name")}</b><br/>类型：${node.data("etype") || "keyword"}<br/>权重：${node.data("weight")}<br/>绑定分块：${node.data("chunk_count") || 0}`,
      pos.x + 10,
      pos.y - 12
    );
  });
  c.on("mouseout", "node", (e) => {
    e.target.removeClass("hovered");
    resetDim();
    hideTooltip();
  });
  // 悬停边：显示关系
  c.on("mouseover", "edge", (e) => {
    e.target.addClass("hovered");
    const pos = e.target.midpoint();
    showTooltip(
      `${e.target.data("source")} → ${e.target.data("target")}<br/>关系：${e.target.data("rtype") || "related"}<br/>权重：${e.target.data("weight")}`,
      pos.x + 10,
      pos.y - 12
    );
  });
  c.on("mouseout", "edge", () => {
    hideTooltip();
  });
  // 单击节点
  c.on("tap", "node", (e) => {
    emit("node-tap", e.target.data("name") as string);
  });
  // 双击节点：打开详情
  c.on("dbltap", "node", (e) => {
    emit("node-dbltap", e.target.data("name") as string);
  });
  // 右键
  c.on("cxttap", "node", (e) => {
    e.preventDefault();
    const rp = e.renderedPosition;
    emit("node-ctx", e.target.data("name") as string, rp.x, rp.y);
  });
  c.on("cxttap", "edge", (e) => {
    e.preventDefault();
    const d = e.target.data();
    const rp = e.renderedPosition;
    emit("edge-ctx", String(d.source), String(d.target), rp.x, rp.y);
  });
  c.on("cxttap", (e) => {
    if (e.target === c) {
      e.preventDefault();
      const rp = e.renderedPosition;
      emit("blank-ctx", rp.x, rp.y);
    }
  });
  initLinkDraw(c);
  // 浏览器默认右键屏蔽（在容器上）
  container.value?.addEventListener("contextmenu", (e) => e.preventDefault());
}

function initLinkDraw(c: Core) {
  const cleanupTmp = () => {
    const tn = c.getElementById(dragTmpId);
    if (tn.length) tn.remove();
    const te = c.getElementById(dragEdgeId);
    if (te.length) te.remove();
  };
  c.on("grab", "node", (e) => {
    if (!props.linkMode) return;
    dragSource = e.target;
    dragTarget = null;
    // 临时目标节点跟随鼠标
    if (!c.getElementById(dragTmpId).length) {
      c.add({
        group: "nodes",
        data: { id: dragTmpId },
        classes: "tmp-node",
        position: { x: 0, y: 0 },
      });
    }
    if (!c.getElementById(dragEdgeId).length) {
      c.add({
        group: "edges",
        data: { id: dragEdgeId, source: dragSource.id(), target: dragTmpId },
        classes: "tmp-edge",
      });
    }
    dragSource.addClass("dragging");
  });
  c.on("mousemove", (e) => {
    const tn = c.getElementById(dragTmpId);
    if (dragSource && tn.length) tn.position({ x: e.position.x, y: e.position.y });
  });
  c.on("mouseover", "node", (e) => {
    if (dragSource && e.target.id() !== dragSource.id() && e.target.id() !== dragTmpId) {
      dragTarget = e.target;
    }
  });
  c.on("free", "node", (e) => {
    if (!dragSource || e.target.id() !== dragSource.id()) return;
    const sName = dragSource.data("name");
    const tName = dragTarget ? String(dragTarget.data("name")) : "";
    dragSource.removeClass("dragging");
    cleanupTmp();
    dragSource = null;
    dragTarget = null;
    if (sName && tName && sName !== tName) emit("link-draw", sName, tName);
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
    layout: { name: "cose", animate: false, fit: true, padding: 30 },
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

defineExpose({ emitPositions, png, setLayout, fit, center, zoom });

onBeforeUnmount(() => {
  cy?.destroy();
  cy = null;
});
</script>

<style scoped>
.graph-canvas-wrap {
  position: relative;
  width: 100%;
}
.graph-canvas {
  width: 100%;
  height: 100%;
  background: #fafbfc;
  background-image: radial-gradient(#e3e7ec 1px, transparent 1px);
  background-size: 20px 20px;
  border-radius: 8px;
  border: 1px solid #eef1f5;
}
.graph-tooltip {
  position: fixed;
  z-index: 4000;
  pointer-events: none;
  background: rgba(45, 55, 72, 0.92);
  color: #fff;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  max-width: 260px;
}
</style>
