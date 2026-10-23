#!/usr/bin/env node
/**
 * 检测指定目录下 .vue/.ts/.js 中未接入 i18n 的中文字面量。
 *
 * 用法:
 *   node scripts/check-i18n-missing.mjs <dirPath>
 *   （默认扫描 src/views）
 *
 * 规则:
 *   - 跳过 src/lang（语言包本身）与 node_modules。
 *   - 已包在 vue-i18n 调用（t(...) / $t(...) / te(...)）内的中文视为已翻译，跳过。
 *   - 行内/块级注释、模板 <!----> 注释里的中文跳过。
 *   - 其余命中的中文，按「文件:行: 内容」输出。
 *
 * 退出码: 0（无遗漏或 --lenient）；1（有遗漏）。默认始终 0，便于 CI 只出报告不阻塞。
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, resolve } from "node:path";

const root = resolve(process.argv[2] || "src/views");
const lenient = process.argv.includes("--lenient");
const CJK = /[\u4e00-\u9fff]+/g;

const results = [];

function isInsideI18nCall(line, column) {
  // 从该列往回找最近的 '('，判断其前是否紧跟 $t / t / te
  const before = line.slice(0, column);
  const idx = before.lastIndexOf("(");
  if (idx < 0) return false;
  const fn = before.slice(Math.max(0, idx - 4), idx).trim();
  return /\$t$|(?:^|[^\w$])t$|te$/.test(fn) || fn === "$t";
}

function trimCommentPrefix(line) {
  // 去掉行首空白与注释标记，判断是否整行注释（之后仍逐列判断）
  return line.replace(/^\s*(?:\/\/|\*|\/\*|<!--)/, "");
}

function scan(file) {
  const text = readFileSync(file, "utf8");
  const lines = text.split(/\r?\n/);
  let inBlockComment = false;
  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = trimCommentPrefix(rawLine);
    if (inBlockComment) {
      if (rawLine.includes("*/")) inBlockComment = false;
      continue;
    }
    if (rawLine.includes("/*") && !rawLine.includes("*/")) inBlockComment = true;
    // 若整行是注释，直接跳过
    if (/^\s*(?:\/\/|\*|\/\*|<!--)/.test(rawLine)) continue;

    CJK.lastIndex = 0;
    let m;
    while ((m = CJK.exec(line)) !== null) {
      const col = m.index;
      // 行内注释：该列之前若有 // 且不在字符串内，视为注释
      const lineBefore = line.slice(0, col);
      const commentIdx = lineBefore.lastIndexOf("//");
      if (commentIdx >= 0 && !/['"`]/.test(lineBefore.slice(commentIdx + 2))) {
        // 有 // 且其后未出现引号，说明中文在注释里
        continue;
      }
      if (isInsideI18nCall(line, col)) continue;
      results.push(`${file.replace(resolve(), "")}:${i + 1}: ${m[0]}`);
    }
  }
}

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === "lang" || name === "node_modules") continue;
      walk(p);
    } else if (/\.(vue|ts|js)$/.test(name)) {
      scan(p);
    }
  }
}

walk(root);

if (results.length > 0) {
  console.log(`共发现 ${results.length} 处疑似未翻译中文：\n`);
  results.forEach((r) => console.log(r));
  process.exitCode = lenient ? 0 : 1;
} else {
  console.log("未发现未翻译中文。");
  process.exitCode = 0;
}
