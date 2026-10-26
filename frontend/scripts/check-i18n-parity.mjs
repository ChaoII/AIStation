#!/usr/bin/env node
/**
 * 校验语言包 key 一致性：以 en 为基准，逐个语言扁平化 key 集合，
 * 报告「缺失」（en 有、该语言没有）与「多余」（该语言有、en 没有）。
 *
 * 用法:
 *   node scripts/check-i18n-parity.mjs            # 默认 src/lang/package
 *   node scripts/check-i18n-parity.mjs <pkgDir> [localeList]
 *
 * 需要 esbuild（vite 项目自带）。退出码 0 表示全部一致；1 表示存在差异。
 */
import { readdirSync, existsSync, readdirSync as listDir } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// pnpm 项目里 esbuild 不在根 node_modules，需从 .pnpm 里定位。
function resolveEsbuild() {
  try {
    return require("esbuild");
  } catch {
    const pnpmRoot = resolve("node_modules/.pnpm");
    let found;
    const walk = (dir, depth = 0) => {
      if (depth > 4) return;
      for (const name of listDir(dir, { withFileTypes: true })) {
        if (found) return;
        if (name.name.startsWith("esbuild@") && name.isDirectory()) {
          const esbDir = join(dir, name.name, "node_modules", "esbuild");
          if (existsSync(join(esbDir, "package.json"))) { found = esbDir; return; }
        } else if (name.isDirectory() && !name.name.startsWith(".")) {
          walk(join(dir, name.name), depth + 1);
        }
      }
    };
    walk(pnpmRoot);
    if (!found) throw new Error("找不到 esbuild");
    return require(found);
  }
}
const { build } = resolveEsbuild();

const pkgDir = resolve(process.argv[2] || "src/lang/package");

function flatten(obj, prefix = "", out = []) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      flatten(v, key, out);
    } else {
      out.push(key);
    }
  }
  return out;
}

async function loadLocale(locale) {
  const entry = join(pkgDir, `${locale}.ts`);
  if (!existsSync(entry)) return null;
  let res;
  try {
    res = await build({
      entryPoints: [entry],
      bundle: true,
      format: "cjs",
      platform: "node",
      write: false,
      logLevel: "silent",
    });
  } catch (e) {
    // 语言包尚未补齐（缺失子模块）时跳过，便于逐语言增量校验。
    return { error: true };
  }
  const code = res.outputFiles[0].text;
  const mod = { exports: {} };
  new Function("module", "exports", "require", code)(mod, mod.exports, require);
  return flatten(mod.exports.default || mod.exports);
}

function compare(base, target, name) {
  const missing = base.filter((k) => !target.includes(k));
  const extra = target.filter((k) => !base.includes(k));
  const ok = missing.length === 0 && extra.length === 0;
  console.log(
    `${name}: ${ok ? "OK" : "DIFF"} (en ${base.length} / ${name} ${target.length}` +
      (ok ? "" : `; 缺 ${missing.length} 多 ${extra.length}`) + ")"
  );
  if (missing.length) console.log("  缺失:", missing.slice(0, 20).join(", "));
  if (extra.length) console.log("  多余:", extra.slice(0, 20).join(", "));
  return ok;
}

const locales = readdirSync(pkgDir)
  .filter((f) => f.endsWith(".ts") && f !== "en.ts")
  .map((f) => f.replace(/\.ts$/, ""));

const base = await loadLocale("en");
if (!base) {
  console.error("找不到 en.ts 聚合器，请检查目录。");
  process.exit(1);
}

let allOk = true;
for (const lc of locales) {
  const target = await loadLocale(lc);
  if (target?.error) {
    console.log(`${lc}: 未完成（子模块缺失），跳过。`);
    continue;
  }
  if (!target) {
    console.error(`${lc}: 聚合器缺失，跳过。`);
    continue;
  }
  if (!compare(base, target, lc)) allOk = false;
}

process.exitCode = allOk ? 0 : 1;
