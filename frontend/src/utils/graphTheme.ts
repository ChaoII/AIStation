/**
 * 全平台图谱统一主题（cytoscape/GraphCanvas 共享）。
 * 把散落在各调用点的配色/形状抽到一处，保证「数据血缘 / 知识库 / 本体」三类图谱
 * 的节点类型、边关系用同一套语义配色与形状。
 */

/** 节点类型 → 颜色 + 形状（覆盖全项目 etype 全集）。颜色语义化，便于一眼区分。 */
export const NODE_TYPE_STYLE: Record<string, { color: string; shape?: string }> = {
  // 数据血缘
  table: { color: "#4a86f7", shape: "round-rectangle" },
  field: { color: "#5ac66b" },
  metric: { color: "#9b59b6", shape: "diamond" },
  term: { color: "#f7a733" },
  domain: { color: "#7f8fa6", shape: "round-rectangle" },
  concept: { color: "#3f9ad6", shape: "round-rectangle" },
  // 本体
  object: { color: "#2f9e95", shape: "round-rectangle" },
  decision: { color: "#f56c6c", shape: "diamond" },
  evidence: { color: "#a66b2f" },
  // 知识库（GraphRAG 实体）
  keyword: { color: "#4a86f7" },
  annotation: { color: "#f7a733", shape: "round-rectangle" },
  custom: { color: "#5ac66b", shape: "diamond" },
  // 兜底
  other: { color: "#a0a6ad" },
};

/** 边关系 → 颜色（血缘 / 本体 / 知识库关系全集） */
export const EDGE_TYPE_STYLE: Record<string, string> = {
  // 知识库关系
  属于: "#5ac66b",
  包含: "#4a86f7",
  依赖: "#f7a733",
  相关: "#a8abb3",
  引用: "#7f8fa6",
  位于: "#3f9ad6",
  用于: "#e6b455",
  关联: "#f7a733",
  // 数据血缘关系
  has_field: "#4a86f7",
  uses_table: "#9b59b6",
  maps_to: "#f7a733",
  subconcept_of: "#3f9ad6",
  defined_as: "#e6b455",
  about: "#7f8fa6",
  in_domain: "#5ac66b",
  same_domain: "#a8abb3",
  related_to: "#a8abb3",
  // 兜底
  default: "#a8abb3",
};

/**
 * 三类图谱的预设样式（nodeStyle / edgeStyle），供各调用点统一引用。
 * colorMode='type'：节点按 etype 走 NODE_TYPE_STYLE，边按 rtype 走 EDGE_TYPE_STYLE。
 */
export const graphPresets = {
  /** 数据血缘：表/字段/指标/术语/域/概念 */
  lineage: {
    nodeStyle: {
      sizeMode: "fixed" as const,
      fixedSize: 36,
      shapeMode: "type" as const,
      colorMode: "type" as const,
      labelSize: 11,
    },
    edgeStyle: {
      colorMode: "type" as const,
      label: "show" as const,
      curve: "bezier" as const,
      arrow: "triangle" as const,
      widthMode: "fixed" as const,
      fixedWidth: 2,
      opacity: 0.8,
    },
  },
  /** 知识库图谱：实体-关系 */
  knowledge: {
    nodeStyle: {
      sizeMode: "weight" as const,
      shapeMode: "type" as const,
      colorMode: "type" as const,
      labelSize: 12,
    },
    edgeStyle: {
      colorMode: "type" as const,
      label: "nondefault" as const,
      curve: "bezier" as const,
      arrow: "triangle" as const,
      widthMode: "weight" as const,
      opacity: 0.8,
    },
  },
  /** 本体类型图：对象类型按所属本体域上色（category） */
  ontology: {
    nodeStyle: {
      sizeMode: "weight" as const,
      shapeMode: "uniform" as const,
      uniformShape: "round-rectangle" as const,
      colorMode: "category" as const,
      labelSize: 12,
    },
    edgeStyle: {
      colorMode: "category" as const,
      label: "show" as const,
      curve: "bezier" as const,
      arrow: "triangle" as const,
      widthMode: "weight" as const,
      opacity: 0.8,
    },
  },
};
