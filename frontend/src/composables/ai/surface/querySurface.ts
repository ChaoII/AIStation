/**
 * 问数结果 → agent-surface 的 `SurfaceNode[]`。
 *
 * 为什么需要它：问数的「SQL / 结果表 / 快了慢了 / 指标命中」在 agent-surface 里
 * 没有默认承载物，不显式转成 surface 节点就会**丢信息**（只剩一句回答）。
 *
 * 纯函数：便于单测，也便于 Workflow / 其他入口复用。
 */
import type { SurfaceNode } from "agent-surface";

export interface QuerySurfaceInput {
  sql?: string;
  rows?: unknown[];
  columns?: string[];
  /** fast = 指标快路径；slow = 生成 SQL */
  path?: string;
  metric?: { name?: string };
  cached?: boolean;
  took_ms?: number;
  error?: string;
}

function toCells(row: unknown, columns: string[]): Record<string, string | number | null> {
  const out: Record<string, string | number | null> = {};
  // 行可能是对象（{列名: 值}）也可能是数组（[值, 值]）——后端两条路径都出现过
  const isArr = Array.isArray(row);
  const r = (row || {}) as Record<string, unknown>;
  columns.forEach((c, i) => {
    const v = isArr ? (row as unknown[])[i] : r[c];
    out[c] = v == null ? null : typeof v === "number" ? v : String(v);
  });
  return out;
}

/** 主函数：按「错误 → SQL → 结果表 → 标签 → 耗时」的固定顺序产出节点 */
export function buildQuerySurface(msg: QuerySurfaceInput): SurfaceNode[] {
  if (msg.error) {
    return [{ type: "callout", tone: "error", title: "查询失败", text: String(msg.error) }];
  }

  const nodes: SurfaceNode[] = [];

  if (msg.sql) {
    nodes.push({ type: "code", language: "sql", title: "生成的 SQL", code: msg.sql });
  }

  const rows = Array.isArray(msg.rows) ? msg.rows : [];
  const first = rows[0];
  const columns =
    msg.columns && msg.columns.length
      ? msg.columns
      : first && !Array.isArray(first)
        ? Object.keys(first as Record<string, unknown>)
        : (first as unknown[] | undefined)?.map((_, i) => `列${i + 1}`) || [];

  if (rows.length && columns.length) {
    nodes.push({
      type: "table",
      columns: columns.map((c) => ({ key: c, label: c })),
      rows: rows.map((r) => toCells(r, columns)),
      caption: `共 ${rows.length} 行`,
    });
  } else if (msg.sql) {
    // 有 SQL 没行：明确告诉用户「查到了但没数据」，别给空白
    nodes.push({
      type: "callout",
      tone: "info",
      title: "查询成功",
      text: "没有匹配的数据（0 行）",
    });
  }

  if (msg.path === "fast" && msg.metric?.name) {
    nodes.push({ type: "badge", label: `指标快路径：${msg.metric.name}`, tone: "success" });
  } else if (msg.path === "fast") {
    nodes.push({ type: "badge", label: "指标快路径", tone: "success" });
  } else if (msg.path === "slow") {
    nodes.push({ type: "badge", label: "生成 SQL", tone: "info" });
  }
  if (msg.cached) nodes.push({ type: "badge", label: "命中缓存", tone: "neutral" });

  if (typeof msg.took_ms === "number") {
    nodes.push({ type: "stat", label: "耗时", value: `${msg.took_ms} ms` });
  }

  return nodes;
}
