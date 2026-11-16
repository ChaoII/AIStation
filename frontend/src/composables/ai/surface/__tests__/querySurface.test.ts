import { describe, expect, it } from "vitest";

import { buildQuerySurface } from "../querySurface";

describe("问数结果 surface", () => {
  it("正常：SQL → 表格 → 标签(含指标名) → 耗时", () => {
    const nodes = buildQuerySurface({
      sql: 'SELECT SUM("QTYIN") FROM t',
      rows: [{ 数值: 123 }],
      columns: ["数值"],
      path: "fast",
      metric: { name: "煤场进煤量合计" },
      took_ms: 781,
    });
    expect(nodes.map((n) => n.type)).toEqual(["code", "table", "badge", "stat"]);
    const badge = nodes[2] as any;
    expect(badge.label).toContain("煤场进煤量合计");
    expect((nodes[3] as any).value).toBe("781 ms");
  });

  it("有 SQL 但 0 行：给出明确空态，而不是空白", () => {
    const nodes = buildQuerySurface({ sql: "SELECT 1", rows: [], path: "slow" });
    expect(nodes.map((n) => n.type)).toEqual(["code", "callout", "badge"]);
    expect((nodes[1] as any).text).toContain("0 行");
  });

  it("错误：只出错误提示，不带 SQL/表格", () => {
    const nodes = buildQuerySurface({ error: "SQL 校验失败：未生成有效的查询语句", sql: "x" });
    expect(nodes).toHaveLength(1);
    expect(nodes[0].type).toBe("callout");
    expect((nodes[0] as any).tone).toBe("error");
    expect((nodes[0] as any).text).toContain("SQL 校验失败");
  });

  it("行数据里的数字保持数字，空值为 null", () => {
    const nodes = buildQuerySurface({
      rows: [{ a: 1, b: null }],
      columns: ["a", "b"],
    });
    const table: any = nodes.find((n) => n.type === "table");
    expect(table.rows[0]).toEqual({ a: 1, b: null });
  });
});
