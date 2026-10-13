/**
 * 本体图谱数据构建（纯函数，可单测）
 *
 * 把当前作用域的对象类型(对象)与关系类型(链接)转换成 GraphCanvas(cytoscape) 的
 * nodes/edges，供 OntGraphWorkspace 渲染。节点=对象类型，边=关系类型。
 */

export interface OntNode {
  /** GraphCanvas 用数字节点 id；这里统一置 0（不作为身份标识） */
  id: number;
  /** 节点显示名（对象显示名，遇重名附 code 后缀保证唯一） */
  name: string;
  /** 节点类型，固定 "object" */
  etype: string;
  /** 权重，默认 1 */
  weight: number;
  /** 对象编码 */
  objectCode: string;
}

export interface OntEdge {
  /** 源节点 name */
  source: string;
  /** 目标节点 name */
  target: string;
  /** 关系名 */
  rtype: string;
}

export interface BuildOntGraphOptions {
  /** 只显示有关联的对象（过滤 link_count === 0 的孤立对象） */
  onlyConnected?: boolean;
}

export function buildOntGraph(
  objects: any[],
  links: any[],
  opts: BuildOntGraphOptions = {}
): { nodes: OntNode[]; edges: OntEdge[] } {
  const onlyConnected = !!opts.onlyConnected;
  const nodes: OntNode[] = [];
  const nameToCode: Record<string, string> = {};
  const usedNames = new Set<string>();

  objects.forEach((o) => {
    if (onlyConnected && (o.link_count || 0) === 0) return;
    let label = o.name || o.code;
    if (usedNames.has(label)) label = `${label}（${o.code}）`;
    usedNames.add(label);
    nameToCode[label] = o.code;
    nodes.push({
      id: 0,
      name: label,
      etype: "object",
      weight: Math.max(1, (o.link_count || 0) + 1),
      objectCode: o.code,
    });
  });

  const edges: OntEdge[] = [];
  const edgeKeys = new Set<string>();
  links.forEach((l) => {
    const sName = nodeNameByCode(l.source_object, nameToCode);
    const tName = nodeNameByCode(l.target_object, nameToCode);
    if (!sName || !tName) return;
    // 自环/重复边去重
    const key = `${sName}::${tName}::${l.name}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    edges.push({ source: sName, target: tName, rtype: l.name || "relation" });
  });

  return { nodes, edges };
}

function nodeNameByCode(code: string, nameToCode: Record<string, string>): string | null {
  for (const [name, c] of Object.entries(nameToCode)) {
    if (c === code) return name;
  }
  return null;
}
