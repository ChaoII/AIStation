import type { EntitySpan } from "../../../api/module_annotation/document";

/**
 * 文本区间（UTF-16 code unit 偏移，与 CodeMirror `state.selection` 一致）。
 * `from`/`to` 为区间两端，`[from, to)` 左闭右开。
 */
export interface SpanRange {
  from: number;
  to: number;
}

/**
 * 从文本内容与选中区间生成一个实体区间标注。
 * 文本切片与偏移均以 UTF-16 code unit 计（JS 字符串 `slice` 与 CodeMirror 偏移一致），
 * `text` 冗余存储选中原文，便于展示与导出。
 */
export function createEntitySpan(
  content: string,
  range: SpanRange,
  labelId: number,
  id?: string
): EntitySpan {
  const start = Math.max(0, Math.min(content.length, range.from));
  const end = Math.max(start, Math.min(content.length, range.to));
  return {
    id: id ?? crypto.randomUUID(),
    type: "EntitySpan",
    start,
    end,
    label_id: labelId,
    text: content.slice(start, end),
  };
}

/**
 * 判断新区间 `[from, to)` 是否与已有任意实体区间相交。
 * 相邻（`from === s.end` 或 `to === s.start`）不算重叠。
 */
export function hasOverlap(
  spans: readonly Pick<EntitySpan, "start" | "end">[],
  from: number,
  to: number
): boolean {
  return spans.some((s) => from < s.end && to > s.start);
}

/**
 * 返回与新区间 `[from, to)` 重叠的第一个实体（用于给用户提示冲突来源）。
 */
export function findOverlappingSpan(
  spans: readonly EntitySpan[],
  from: number,
  to: number
): EntitySpan | null {
  return spans.find((s) => from < s.end && to > s.start) ?? null;
}

/**
 * 找到覆盖指定 `offset`（左闭右开区间内）的实体，用于点击高亮定位/编辑。
 */
export function findSpanAt(spans: readonly EntitySpan[], offset: number): EntitySpan | null {
  return spans.find((s) => offset >= s.start && offset < s.end) ?? null;
}

/** 还原实体区间为 `{from, to}`（供外层工具/面板使用）。 */
export function spanToRange(span: Pick<EntitySpan, "start" | "end">): SpanRange {
  return { from: span.start, to: span.end };
}

/**
 * 按换行（`\n`）切分出每一行的起始偏移（含空行），用于「同一句」判断。
 * 首行起点恒为 0，之后每遇一个 `\n` 记录下一个行起点。
 */
export function buildSentenceLineStarts(content: string): number[] {
  const starts = [0];
  for (let i = 0; i < content.length; i++) {
    if (content.charCodeAt(i) === 10) starts.push(i + 1);
  }
  return starts;
}

/** 二分查找：给定偏移落到第几行（0 起）。偏移落在行首时归属该行。 */
export function lineIndexOf(lineStarts: readonly number[], offset: number): number {
  let lo = 0,
    hi = lineStarts.length - 1,
    ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (lineStarts[mid] <= offset) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

/** 判断两个实体是否位于同一句（同一行），按 `\n` 切分。 */
export function sameSentence(
  content: string,
  a: Pick<EntitySpan, "start">,
  b: Pick<EntitySpan, "start">
): boolean {
  const starts = buildSentenceLineStarts(content);
  return lineIndexOf(starts, a.start) === lineIndexOf(starts, b.start);
}
