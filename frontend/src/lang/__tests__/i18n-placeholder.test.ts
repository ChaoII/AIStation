/**
 * i18n 文案守卫：语言包里不得出现裸 `{{xxx}}`。
 *
 * 背景（2026-11-09 实测）：vue-i18n 把 `{{ }}` 当**嵌套占位符**，消息编译直接抛
 * `Message compilation error: Not allowed nest placeholder`。渲染该文案的组件会整个挂掉，
 * 且只有「真的点开那个页面/弹窗」才会暴露——提示词新建弹窗因此完全打不开，
 * 知识库「数据源」页签报 `Cannot read properties of null (reading 'notify')`。
 *
 * 若确实要在文案里显示双花括号，必须用 vue-i18n 的字面量写法：`{'{{'}变量名{'}}'}`。
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const BASE = join(process.cwd(), "src", "lang", "package");
const RAW = /\{\{[^{}]*\}\}/;
const AT_ESC = "{'@'}";

function langFiles(): string[] {
  const out: string[] = [];
  for (const lang of readdirSync(BASE, { withFileTypes: true })) {
    if (!lang.isDirectory()) continue;
    const dir = join(BASE, lang.name);
    for (const f of readdirSync(dir)) {
      if (f.endsWith(".ts")) out.push(join(dir, f));
    }
  }
  return out;
}

describe("i18n 文案", () => {
  it("不得含裸 {{...}}（会编译失败，必须写成 {'{{'}x{'}}'}）", () => {
    const offenders: string[] = [];
    for (const file of langFiles()) {
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        if (line.trimStart().startsWith("//")) return;
        if (RAW.test(line)) offenders.push(`${file}:${i + 1}: ${line.trim().slice(0, 100)}`);
      });
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("不得含裸 @（会报 Invalid linked format，必须写成 {'@'}）", () => {
    const offenders: string[] = [];
    for (const file of langFiles()) {
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        if (line.trimStart().startsWith("//")) return;
        // 去掉已转义片段后再看是否还有裸 @（邮箱、DSN、npm 包名都踩过）
        if (line.split(AT_ESC).join("").includes("@")) {
          offenders.push(`${file}:${i + 1}: ${line.trim().slice(0, 100)}`);
        }
      });
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});
