<template>
  <div class="graph-canvas-wrap" :style="{ height: heightStyle }">
    <div ref="container" class="graph-canvas" :style="bgStyle" />
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
// @ts-ignore 无类型声明
import cytoscapeD3Force from "cytoscape-d3-force";
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";

cytoscape.use(cytoscapeD3Force);

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
  shortestMode?: boolean;
  physicsMode?: boolean;
  edgeStyle?: {
    lineStyle?: "solid" | "dashed" | "dotted";
    curve?: "bezier" | "straight" | "taxi";
    arrow?: "triangle" | "vee" | "circle" | "none";
    widthMode?: "weight" | "fixed";
    fixedWidth?: number;
    colorMode?: "type" | "single";
    singleColor?: string;
    label?: "show" | "nondefault" | "hover" | "none";
    opacity?: number;
  };
  theme?: string;
  nodeStyle?: {
    sizeMode?: "weight" | "fixed";
    fixedSize?: number;
    shapeMode?: "type" | "uniform";
    uniformShape?: "ellipse" | "round-rectangle" | "diamond" | "circle";
    colorMode?: "type" | "single";
    singleColor?: string;
    labelSize?: number;
  };
}>();

const emit = defineEmits<{
  (e: "node-tap", name: string): void;
  (e: "node-dbltap", name: string): void;
  (e: "node-ctx", name: string, x: number, y: number): void;
  (e: "edge-ctx", source: string, target: string, x: number, y: number): void;
  (e: "blank-ctx", x: number, y: number): void;
  (e: "layout", items: { id: number; x: number; y: number }[]): void;
  (e: "link-draw", source: string, target: string): void;
  (e: "path-found", a: string, b: string, length: number): void;
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

const THEMES: Record<string, any> = {
  default: {
    label: "默认",
    node: { keyword: "#4a86f7", annotation: "#f7a733", custom: "#5ac66b", other: "#a0a6ad" },
    edge: {
      属于: "#5ac66b",
      包含: "#4a86f7",
      依赖: "#f7a733",
      相关: "#a8abb3",
      引用: "#7f8fa6",
      位于: "#3f9ad6",
      用于: "#e6b455",
      关联: "#f7a733",
      default: "#a8abb3",
    },
    bg: "#fafbfc",
    grid: "#e3e7ec",
  },
  ocean: {
    label: "海洋",
    node: { keyword: "#2f7bc4", annotation: "#30a6c9", custom: "#4dbf9c", other: "#7d9bb3" },
    edge: {
      属于: "#4dbf9c",
      包含: "#2f7bc4",
      依赖: "#30a6c9",
      相关: "#8fa9c0",
      引用: "#6b8aa6",
      位于: "#1f6c9e",
      用于: "#57b7d8",
      关联: "#30a6c9",
      default: "#8fa9c0",
    },
    bg: "#f2f8fc",
    grid: "#dbe9f3",
  },
  forest: {
    label: "森林",
    node: { keyword: "#3f9d63", annotation: "#8fbf4d", custom: "#5f9e8f", other: "#8aa88f" },
    edge: {
      属于: "#5f9e8f",
      包含: "#3f9d63",
      依赖: "#8fbf4d",
      相关: "#9bb6a4",
      引用: "#6f9481",
      位于: "#2f7d54",
      用于: "#a9c96f",
      关联: "#8fbf4d",
      default: "#9bb6a4",
    },
    bg: "#f4f9f4",
    grid: "#ddeae0",
  },
  sunset: {
    label: "落日",
    node: { keyword: "#e07a4f", annotation: "#f4b14e", custom: "#c86a8a", other: "#b98e8e" },
    edge: {
      属于: "#c86a8a",
      包含: "#e07a4f",
      依赖: "#f4b14e",
      相关: "#c9a8a0",
      引用: "#a9796e",
      位于: "#d95f3b",
      用于: "#e8a35c",
      关联: "#f4b14e",
      default: "#c9a8a0",
    },
    bg: "#fdf8f3",
    grid: "#f0e2d6",
  },
  mono: {
    label: "单色",
    node: { keyword: "#6b7480", annotation: "#9aa3ad", custom: "#4d5560", other: "#b6bdc5" },
    edge: {
      属于: "#7d8791",
      包含: "#6b7480",
      依赖: "#9aa3ad",
      相关: "#aab1b9",
      引用: "#8b939d",
      位于: "#5a636e",
      用于: "#9aa3ad",
      关联: "#9aa3ad",
      default: "#aab1b9",
    },
    bg: "#f5f6f7",
    grid: "#e2e4e7",
  },
};
const NS = computed(() => ({
  sizeMode: props.nodeStyle?.sizeMode || "weight",
  fixedSize: props.nodeStyle?.fixedSize || 22,
  shapeMode: props.nodeStyle?.shapeMode || "type",
  uniformShape: props.nodeStyle?.uniformShape || "ellipse",
  colorMode: props.nodeStyle?.colorMode || "type",
  singleColor: props.nodeStyle?.singleColor || "#4a86f7",
  labelSize: props.nodeStyle?.labelSize || 12,
}));
function palette() {
  return THEMES[props.theme || "default"] || THEMES.default;
}
function nodeColorFor(etype?: string, hasChunk = false) {
  const p = palette();
  if (NS.value.colorMode === "single") return NS.value.singleColor;
  if (hasChunk || etype === "annotation") return p.node.annotation;
  if (etype === "custom") return p.node.custom;
  if (etype === "keyword" || !etype) return p.node.keyword;
  return p.node.other;
}
function edgeColor(rtype?: string) {
  const p = palette();
  if (p.edge[rtype || ""]) return p.edge[rtype || ""];
  return p.edge.default || "#a8abb3";
}
function nodeSize(weight?: number) {
  return NS.value.sizeMode === "fixed" ? NS.value.fixedSize : 14 + Math.min(weight || 1, 20) * 1.2;
}
function nodeShape(etype?: string) {
  if (NS.value.shapeMode === "uniform") return NS.value.uniformShape;
  const t = etype;
  if (t === "annotation") return "round-rectangle";
  if (t === "custom") return "diamond";
  return "ellipse";
}
const bgStyle = computed(() => {
  const p = palette();
  return {
    background: p.bg,
    backgroundImage: `radial-gradient(${p.grid} 1px, transparent 1px)`,
  };
});
const ES = computed(() => ({
  lineStyle: props.edgeStyle?.lineStyle || "solid",
  curve: props.edgeStyle?.curve || "bezier",
  arrow: props.edgeStyle?.arrow || "triangle",
  widthMode: props.edgeStyle?.widthMode || "weight",
  fixedWidth: props.edgeStyle?.fixedWidth || 2,
  colorMode: props.edgeStyle?.colorMode || "type",
  singleColor: props.edgeStyle?.singleColor || "#409eff",
  label: props.edgeStyle?.label || "show",
  opacity: props.edgeStyle?.opacity ?? 0.75,
}));

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
      "font-size": NS.value.labelSize,
      color: "#2f3542",
      "text-valign": "bottom",
      "text-margin-y": 5,
      "text-wrap": "wrap",
      "text-max-width": NS.value.labelSize * 10,
      width: (ele: any) => nodeSize(ele.data("weight")),
      height: (ele: any) => nodeSize(ele.data("weight")),
      shape: (ele: any) => nodeShape(ele.data("etype")),
      "background-color": (ele: any) =>
        nodeColorFor(ele.data("etype"), ele.data("chunk_count") > 0),
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
      width: (ele: any) =>
        ES.value.widthMode === "fixed"
          ? ES.value.fixedWidth
          : 1.5 + Math.min(ele.data("weight") || 1, 5) * 0.6,
      "line-color": (ele: any) =>
        ES.value.colorMode === "single" ? ES.value.singleColor : edgeColor(ele.data("rtype")),
      "line-style": ES.value.lineStyle,
      "curve-style": ES.value.curve,
      "target-arrow-shape": ES.value.arrow,
      "target-arrow-color": (ele: any) =>
        ES.value.colorMode === "single" ? ES.value.singleColor : edgeColor(ele.data("rtype")),
      "arrow-scale": 0.9,
      label: (ele: any) => {
        const mode = ES.value.label;
        if (mode === "show") return ele.data("label") || "";
        if (mode === "nondefault")
          return (ele.data("rtype") || "") === "related" ? "" : ele.data("label");
        return "";
      },
      "font-size": 9,
      color: "#7f8fa6",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.9,
      "text-background-padding": 3,
      "text-rotation": "autorotate",
      opacity: ES.value.opacity,
    },
  },
  {
    selector: "edge.hovered",
    style: {
      opacity: 1,
      width: 4,
      "line-color": "#409eff",
      "target-arrow-color": "#409eff",
      label: "data(label)",
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
  {
    selector: "node.path",
    style: { "border-width": 5, "border-color": "#f56c6c", "background-color": "#ffd8cc" },
  },
  {
    selector: "edge.path",
    style: { width: 4, "line-color": "#f56c6c", opacity: 1 },
  },
  {
    selector: "node.spA",
    style: { "border-width": 5, "border-color": "#67c23a" },
  },
];

function runLayout() {
  const c = cy;
  if (!c) return;
  const preset = props.usePreset && props.nodes.every((n) => n.x != null && n.y != null);
  const name = (props.layoutName || "cose") as string;
  const opts: any = {};
  if (preset && name === "cose") {
    opts.name = "preset";
    opts.fit = true;
    opts.padding = 30;
  } else if (name === "cose") {
    if (props.physicsMode) {
      // d3-force 物理引擎：节点持续弹跳/碰撞，拖动推挤
      opts.name = "d3-force";
      opts.animate = true;
      opts.fit = false;
      opts.linkDistance = 72;
      opts.charge = -420;
      opts.gravity = 0.12;
      opts.collideRadius = 24;
      opts.alphaMin = 0.0005;
      opts.randomize = true;
      opts.stiffness = 0.7;
    } else {
      // 稳定力导向（cose，碰撞避免）
      opts.name = "cose";
      opts.animate = true;
      opts.animationDuration = 500;
      opts.fit = true;
      opts.padding = 30;
      opts.nodeRepulsion = 40000;
      opts.idealEdgeLength = 110;
      opts.gravity = 0.35;
      opts.numIter = 2500;
      opts.nodeOverlap = 20;
      opts.spacingFactor = 1.2;
    }
  } else {
    opts.name = name;
    opts.animate = true;
    opts.animationDuration = 400;
    opts.fit = true;
    opts.padding = 30;
    if (name === "concentric") opts.minNodeSpacing = 26;
    if (name === "breadthfirst") opts.spacingFactor = 1.2;
    if (name === "grid") opts.avoidOverlap = true;
  }
  c.layout(opts).run();
  if (opts.name === "d3-force") {
    setTimeout(() => {
      if (cy) cy.fit(undefined, 30);
    }, 150);
  }
}
function setLayout(name: string) {
  const c = cy;
  if (!c) return;
  if (name === "cose") {
    if (props.physicsMode) {
      c.layout({
        name: "d3-force",
        animate: true,
        fit: false,
        linkDistance: 72,
        charge: -420,
        gravity: 0.12,
        collideRadius: 24,
        alphaMin: 0.0005,
        randomize: true,
        stiffness: 0.7,
      } as any).run();
    } else {
      c.layout({
        name: "cose",
        animate: true,
        animationDuration: 500,
        fit: true,
        padding: 30,
        nodeRepulsion: 40000,
        idealEdgeLength: 110,
        gravity: 0.35,
        numIter: 2500,
        nodeOverlap: 20,
        spacingFactor: 1.2,
      } as any).run();
    }
    return;
  }
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
    if (props.shortestMode) {
      handleSP(e.target);
      return;
    }
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

function findShortestPath(c: Core, aName: string, bName: string) {
  const adj: Record<string, Set<string>> = {};
  c.nodes().forEach((n) => {
    adj[n.id()] = new Set();
  });
  c.edges().forEach((ed) => {
    const s = ed.source().id();
    const t = ed.target().id();
    adj[s] = adj[s] || new Set();
    adj[t] = adj[t] || new Set();
    adj[s].add(t);
    adj[t].add(s);
  });
  const start = aName;
  const goal = bName;
  const prev: Record<string, string> = {};
  const queue = [start];
  const visited = new Set([start]);
  while (queue.length) {
    const cur = queue.shift() as string;
    if (cur === goal) break;
    (adj[cur] || []).forEach((nei) => {
      if (!visited.has(nei)) {
        visited.add(nei);
        prev[nei] = cur;
        queue.push(nei);
      }
    });
  }
  if (!visited.has(goal)) return null;
  const nodes: string[] = [goal];
  let cur = goal;
  while (cur !== start) {
    cur = prev[cur];
    nodes.push(cur);
  }
  nodes.reverse();
  const edges: string[] = [];
  c.edges().forEach((ed) => {
    const s = ed.source().id();
    const t = ed.target().id();
    const si = nodes.indexOf(s);
    if (si >= 0 && (nodes[si - 1] === t || nodes[si + 1] === t)) {
      edges.push(ed.id());
    }
  });
  return { nodes, edges };
}
function clearPath(c: Core) {
  c.elements().removeClass("path");
}
let spA: any = null;
function handleSP(node: any) {
  const c = cy;
  if (!c) return;
  if (!spA) {
    c.elements().removeClass("spA");
    spA = node;
    node.addClass("spA");
    return;
  }
  const aName = spA.data("name");
  const bName = node.data("name");
  clearPath(c);
  const path = findShortestPath(c, aName, bName);
  if (path) {
    path.nodes.forEach((id) => {
      const el = c.getElementById(id);
      if (el.length) el.addClass("path");
    });
    path.edges.forEach((id) => {
      const el = c.getElementById(id);
      if (el.length) el.addClass("path");
    });
    emit("path-found", aName, bName, path.nodes.length - 1);
  } else {
    emit("path-found", aName, bName, -1);
  }
  node.removeClass("spA");
  spA = null;
}
function search(name: string) {
  const c = cy;
  if (!c || !name) return;
  const el = c.getElementById(String(name));
  if (el.length) {
    clearPath(c);
    c.fit(el, 60);
    c.elements().removeClass("selected");
    el.select();
  } else {
    let best: any = null;
    c.nodes().forEach((n) => {
      if ((n.data("name") as string).includes(name)) {
        if (!best) best = n;
      }
    });
    if (best) {
      clearPath(c);
      c.fit(best, 60);
      c.elements().removeClass("selected");
      best.select();
    }
  }
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
    layout: { name: "preset", fit: true, padding: 30 },
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
watch(
  () => props.edgeStyle,
  () => {
    if (!cy) return;
    (cy.style(graphStyle) as any).update?.();
  },
  { deep: true }
);
watch(
  () => [props.theme, props.nodeStyle],
  () => {
    if (!cy) return;
    (cy.style(graphStyle) as any).update?.();
  },
  { deep: true }
);

function png(): string {
  if (!cy) return "";
  return (cy.png as any)({ output: "dataurl", full: true, scale: 2 }) as string;
}

defineExpose({ emitPositions, png, setLayout, fit, center, zoom, search });

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
