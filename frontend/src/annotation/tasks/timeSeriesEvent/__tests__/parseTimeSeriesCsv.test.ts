import { describe, it, expect } from "vitest";
import { parseSeriesCsv } from "../parseTimeSeriesCsv";

const META = { time_column: "time", value_columns: ["v1", "v2"] };

describe("parseTimeSeriesCsv 时间序列 CSV 解析", () => {
  it("解析表头与数据行为 {time, value} 数组（默认取首数值列）", () => {
    const text = "time,v1,v2\n100,1.5,9\n200,2.5,8\n300,3.5,7\n";
    const r = parseSeriesCsv(text, META);
    expect(r.timeColumn).toBe("time");
    expect(r.valueColumn).toBe("v1");
    expect(r.points).toEqual([
      { time: 100, value: 1.5 },
      { time: 200, value: 2.5 },
      { time: 300, value: 3.5 },
    ]);
  });

  it("指定 valueColumn 时取对应数值列", () => {
    const text = "time,v1,v2\n100,1.5,9\n200,2.5,8\n";
    const r = parseSeriesCsv(text, META, "v2");
    expect(r.valueColumn).toBe("v2");
    expect(r.points).toEqual([
      { time: 100, value: 9 },
      { time: 200, value: 8 },
    ]);
  });

  it("跳过非数值/空行，不产生 NaN 点", () => {
    const text = "time,v1\n1,10\n,20\n3,abc\n4,\n";
    const r = parseSeriesCsv(text, { time_column: "time", value_columns: ["v1"] });
    expect(r.points).toEqual([{ time: 1, value: 10 }]);
  });

  it("兼容 \\r\\n 换行与前后空白", () => {
    const text = "time,v1\r\n1,10\r\n2,20\r\n";
    const r = parseSeriesCsv(text, { time_column: "time", value_columns: ["v1"] });
    expect(r.points).toEqual([
      { time: 1, value: 10 },
      { time: 2, value: 20 },
    ]);
  });

  it("解析制表符分隔的 .tsv（默认取首数值列）", () => {
    const text = "time\tv1\tv2\n100\t1.5\t9\n200\t2.5\t8\n300\t3.5\t7\n";
    const r = parseSeriesCsv(text, META);
    expect(r.timeColumn).toBe("time");
    expect(r.valueColumn).toBe("v1");
    expect(r.points).toEqual([
      { time: 100, value: 1.5 },
      { time: 200, value: 2.5 },
      { time: 300, value: 3.5 },
    ]);
  });

  it("时间列/数值列缺失时返回空 points", () => {
    const r = parseSeriesCsv("a,b\n1,2\n", { time_column: "time", value_columns: ["v1"] });
    expect(r.points).toEqual([]);
    const r2 = parseSeriesCsv("time,v1\n1,2\n", { time_column: "time", value_columns: [] });
    expect(r2.points).toEqual([]);
  });

  it("空文本返回空 points", () => {
    const r = parseSeriesCsv("", META);
    expect(r.points).toEqual([]);
  });
});
