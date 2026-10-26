import { describe, expect, it } from "vitest";
import {
  CAST_LIMIT,
  castGlyph,
  castHandoff,
  hasBad,
  makeCast,
  pushCast,
  type CastItem,
} from "../broadcast";

function at(h: number, m: number, s: number) {
  const d = new Date(2026, 9, 26, h, m, s);
  return d;
}

describe("office 播报流", () => {
  it("造条目：压空白、带时间、默认截断 120 字", () => {
    const it0 = makeCast("delegate", "  组长   派给  问数助手\n查数据集  ", { at: at(9, 5, 3) });
    expect(it0.text).toBe("组长 派给 问数助手 查数据集");
    expect(it0.t).toBe("09:05:03");
    expect(it0.kind).toBe("delegate");
    expect(it0.bad).toBeUndefined();

    const long = makeCast("reply", "字".repeat(200));
    expect(long.text.length).toBe(121); // 120 + 省略号
    expect(long.text.endsWith("…")).toBe(true);
  });

  it("bad 只在实际为真时出现（避免渲染出 undefined 属性）", () => {
    expect(makeCast("conn", "断线", { bad: true }).bad).toBe(true);
    expect("bad" in makeCast("conn", "正常")).toBe(false);
  });

  it("追加不修改原数组，超过上限只留最近 30 条", () => {
    let list: CastItem[] = [];
    const first = pushCast(list, makeCast("info", "0"));
    expect(list.length).toBe(0); // 原数组没被动
    list = first;
    for (let i = 1; i < CAST_LIMIT + 5; i++) {
      list = pushCast(list, makeCast("info", String(i)));
    }
    expect(list.length).toBe(CAST_LIMIT);
    expect(list[0].text).toBe("5"); // 前 5 条被挤掉
    expect(list[list.length - 1].text).toBe(String(CAST_LIMIT + 4));
    // id 单调递增，可做列表 key
    for (let i = 1; i < list.length; i++) expect(list[i].id).toBeGreaterThan(list[i - 1].id);
  });

  it("上限可调（页面里展开面板不改变数据，只有存储上限）", () => {
    let list: CastItem[] = [];
    for (let i = 0; i < 10; i++) list = pushCast(list, makeCast("info", String(i)), 3);
    expect(list.map((x) => x.text)).toEqual(["7", "8", "9"]);
  });

  it("glyph 覆盖每种类型，未知类型给兜底", () => {
    const kinds = ["delegate", "reply", "tool", "summary", "cron", "conn", "info"] as const;
    kinds.forEach((k) => expect(castGlyph(k).length).toBeGreaterThan(0));
    // @ts-expect-error 故意传未知类型，验证兜底
    expect(castGlyph("nope")).toBe("·");
  });

  it("hasBad 只看 bad 标记", () => {
    expect(hasBad([])).toBe(false);
    expect(hasBad([makeCast("info", "ok")])).toBe(false);
    expect(hasBad([makeCast("info", "ok"), makeCast("conn", "断线", { bad: true })])).toBe(true);
  });

  it("castHandoff 统一「A 派给 B：任务」的写法", () => {
    expect(castHandoff("全能分析助理", "问数助手", "查数据集")).toBe(
      "全能分析助理 派给 问数助手：查数据集"
    );
    expect(castHandoff("", "", "")).toBe("组长 派给 成员");
    expect(castHandoff("组长", "问数助手")).toBe("组长 派给 问数助手");
  });
});
