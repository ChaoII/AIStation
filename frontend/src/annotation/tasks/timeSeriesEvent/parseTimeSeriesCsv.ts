import type { TimeSeriesMeta } from "../../../api/module_annotation/timeSeries";

/** 序列数据点：time 为时间列原始值（time_unit 决定的单位），value 为数值列值。 */
export interface SeriesPoint {
  time: number;
  value: number;
}

/** CSV 解析结果：points 为可渲染数据点，另附时间/数值列信息。 */
export interface ParsedSeries {
  points: SeriesPoint[];
  timeColumn: string;
  valueColumn: string;
  valueColumns: string[];
}

/**
 * 将时间序列 CSV 原文解析为 `{time, value}[]`。
 * 默认取 `value_columns` 首列数值；可传入指定数值列。跳过非数值/空行。
 */
export function parseSeriesCsv(
  text: string,
  meta: Pick<TimeSeriesMeta, "time_column" | "value_columns">,
  valueColumn?: string
): ParsedSeries {
  const lines = String(text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n");
  const valueColumns = meta.value_columns?.length ? [...meta.value_columns] : [];
  const timeColumn = meta.time_column ?? "";
  const vc = valueColumn && valueColumns.includes(valueColumn) ? valueColumn : (valueColumns[0] ?? "");
  let headerIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() !== "") {
      headerIdx = i;
      break;
    }
  }
  const points: SeriesPoint[] = [];
  if (headerIdx < 0) return { points, timeColumn, valueColumn: vc, valueColumns };
  const header = lines[headerIdx].split(",").map((s) => s.trim());
  const timeIdx = header.indexOf(timeColumn);
  const valueIdx = vc ? header.indexOf(vc) : -1;
  if (timeIdx >= 0 && valueIdx >= 0) {
    for (let i = headerIdx + 1; i < lines.length; i++) {
      const row = lines[i];
      if (row.trim() === "") continue;
      const cells = row.split(",").map((s) => s.trim());
      const timeCell = cells[timeIdx];
      const valueCell = cells[valueIdx];
      const time = Number(timeCell);
      const value = Number(valueCell);
      if (
        timeCell !== "" &&
        valueCell !== "" &&
        Number.isFinite(time) &&
        Number.isFinite(value)
      )
        points.push({ time, value });
    }
  }
  return { points, timeColumn, valueColumn: vc, valueColumns };
}
