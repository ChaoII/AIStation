/**
 * 金路径冒烟（前端）：登录 → 问数 → 执行详情 → 配置面板 → 资产起草入口。
 * 用法：node scripts/golden_path.mjs   退出码非 0 即失败。
 */
import { chromium } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL || "http://127.0.0.1:5181/web";
const fails = [];
const ok = (name, cond, detail = "") => {
  console.log((cond ? "PASS " : "FAIL ") + name + (cond ? "" : `  [${detail}]`));
  if (!cond) fails.push(name);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

// 登录
await page.goto(`${BASE}/#/login`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1200);
await page.locator('input[type="text"]').first().fill("admin");
await page.locator('input[type="password"]').first().fill("123456");
await page.getByRole("button", { name: /登\s*录/ }).click();
await page.waitForFunction(() => !location.hash.includes("/login"), { timeout: 60000 });
await page.waitForTimeout(1500);

// 登录之后才开始收集接口错误
const bad = [];
page.on("response", (r) => {
  if (r.status() >= 400 && !r.url().includes("/monitor/server/info")) {
    bad.push(`${r.status()} ${r.url().replace(/^https?:\/\/[^/]+/, "")}`);
  }
});

// 1) 问数（快路径）
await page.goto(`${BASE}/#/ai/query?datasource=ds:4`, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".chat-shell", { timeout: 30000 });
await page.waitForTimeout(1000);
await page.locator("textarea").first().fill("煤场进煤记录有多少条？");
await page.getByRole("button", { name: /提\s*问/ }).first().click();
await page.waitForTimeout(20000);
const fb = await page.evaluate(() =>
  [...document.querySelectorAll(".q-msg__fb button")].map((b) => b.textContent?.trim())
);
ok("问数返回结果", fb.length > 0, JSON.stringify(fb));
ok("有执行详情入口", fb.includes("执行详情"), JSON.stringify(fb));

if (fb.includes("执行详情")) {
  await page.getByRole("button", { name: "执行详情" }).last().click();
  await page.waitForTimeout(800);
  const drawer = await page.evaluate(() => {
    const d = [...document.querySelectorAll(".el-drawer")].find((x) => x.offsetParent);
    return {
      text: d?.textContent || "",
      hasSql: !!d?.querySelector("pre, .code-block"),
    };
  });
  ok("执行详情含 SQL", drawer.hasSql, drawer.text.slice(0, 80));
  ok("执行详情含耗时", drawer.text.includes("ms"), drawer.text.slice(0, 80));
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
}

// 2) 配置面板
await page.getByRole("button", { name: /设置/ }).first().click();
await page.waitForTimeout(900);
const groups = await page.evaluate(() => document.querySelectorAll(".q-set__group-title").length);
ok("配置面板分组", groups >= 3, String(groups));
const firstRowVisible = await page.locator(".q-set__group .q-set__row").first().isVisible();
await page.locator(".q-set__group-title").first().click();
await page.waitForTimeout(300);
const collapsed = await page.locator(".q-set__group .q-set__row").first().isVisible();
ok("分组可折叠", firstRowVisible && !collapsed);
await page.locator(".q-set__group-title").first().click();
await page.keyboard.press("Escape");
await page.waitForTimeout(300);

// 3) 资产起草入口
await page.goto(`${BASE}/#/ai/integration`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(4000);
const labels = await page.evaluate(() =>
  [...document.querySelectorAll("button")].map((b) => b.textContent?.trim()).filter(Boolean)
);
ok("资产页有 AI 生成描述", labels.includes("AI 生成描述"), JSON.stringify(labels.slice(0, 12)));
ok("资产页有批量起草", labels.includes("批量起草"), JSON.stringify(labels.slice(0, 12)));
ok("接口无 4xx/5xx", bad.length === 0, bad.join(" | "));

// 4) 清理本次冒烟产生的会话：它走真实 UI 提问，会留一条会话；
//    不清理的话左侧「会话」列表会被同一句冒烟问题刷屏（实测曾积累 37 条）。
try {
  const api = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";
  const token = await page.evaluate(() => {
    const raw =
      localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || "";
    // Storage 里存的是 JSON 字符串（带引号），直接塞 Bearer 会被判无效认证
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  });
  if (token) {
    const r = await fetch(`${api}/ai/query/sessions/list`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const list = (await r.json())?.data || [];
    // 列表按 id 倒序，本次刚创建的在最前；标题一致才删，避免误删别的会话
    const mine = list.filter((s) => s.title === "煤场进煤记录有多少条？").slice(0, 1);
    for (const s of mine) {
      await fetch(`${api}/ai/query/sessions/${s.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
    }
    console.log(`清理冒烟会话 ${mine.length} 条`);
  }
} catch (e) {
  console.log("清理冒烟会话失败（忽略，不影响判定）: " + e.message);
}

await browser.close();
console.log(fails.length ? `\n失败 ${fails.length} 项` : "\n全部通过");
process.exit(fails.length ? 1 : 0);
