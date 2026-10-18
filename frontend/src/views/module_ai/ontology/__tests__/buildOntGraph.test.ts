import { describe, it, expect } from "vitest";
import { buildOntGraph } from "../graph";

const objs = [
  { code: "A", name: "客户", link_count: 2 },
  { code: "B", name: "订单", link_count: 1 },
  { code: "C", name: "孤儿", link_count: 0 },
];
const links = [{ source_object: "A", target_object: "B", name: "下单" }];

describe("buildOntGraph", () => {
  it("默认返回所有对象作为节点", () => {
    const g = buildOntGraph(objs, links);
    expect(g.nodes).toHaveLength(3);
    expect(g.nodes.map((n) => n.name)).toContain("客户");
  });
  it("边连接 source/target 的 name", () => {
    const g = buildOntGraph(objs, links);
    const e = g.edges[0];
    expect(e.source).toBe("客户");
    expect(e.target).toBe("订单");
    expect(e.rtype).toBe("下单");
  });
  it("只显示有关联时过滤 link_count===0 的孤立对象", () => {
    const g = buildOntGraph(objs, links, { onlyConnected: true });
    expect(g.nodes.map((n) => n.name)).not.toContain("孤儿");
  });
  it("自环/重复边不产生重复 edge", () => {
    const selfLink = { source_object: "A", target_object: "A", name: "自关联" };
    const g = buildOntGraph(objs, [...links, selfLink]);
    expect(g.edges.filter((e) => e.rtype === "自关联")).toHaveLength(1);
  });
  it("节点带所属本体 category（按本体上色的分组键）", () => {
    const domObjs = [
      { code: "A", name: "客户", link_count: 1, domain_code: "sales" },
      { code: "B", name: "订单", link_count: 1, domain_code: "sales" },
      { code: "C", name: "设备", link_count: 1, domain_code: "iot" },
      { code: "D", name: "未分组", link_count: 0, domain_code: "" },
    ];
    const g = buildOntGraph(domObjs, []);
    const byCode = (code: string) => g.nodes.find((n) => n.objectCode === code)!;
    expect(byCode("A").category).toBe("sales");
    expect(byCode("C").category).toBe("iot");
    expect(byCode("D").category).toBe("未分组");
  });
});
