/**
 * 页面健康审计：把 AI 模块下每个页面真的打开一遍，抓出
 *   - 控制台 error / warning
 *   - 未捕获的页面异常（pageerror）
 *   - 失败的接口请求（4xx/5xx）
 *   - 页面主体是否渲染出内容（防止"白屏但无报错"）
 *
 * **刻意不做任何断言**：它的产出是一份体检报告，不是通过/失败。
 * 断言会让第一个错误就中断，看不到全貌。
 */
import { test, type Page } from "@playwright/test";

/** 要体检的页面（路径 + 中文名 + 一个"应该出现"的标志元素选择器） */
const PAGES: Array<{ path: string; name: string; marker: string }> = [
  { path: "/ai/query", name: "智能问数", marker: ".app-main .app-container" },
  { path: "/ai/ontology", name: "本体", marker: ".app-main .app-container" },
  { path: "/ai/integration", name: "数据与集成", marker: ".app-main .app-container" },
  { path: "/ai/asset", name: "数据资产(应重定向到集成)", marker: ".app-main .app-container" },
  { path: "/ai/governance", name: "治理驾驶舱", marker: ".app-main .app-container" },
  { path: "/ai/knowledge", name: "知识库", marker: ".app-main .app-container" },
  { path: "/ai/overview", name: "AI 控制台", marker: ".app-main .app-container" },
  { path: "/ai/model", name: "模型管理", marker: ".app-main .app-container" },
  { path: "/ai/provider", name: "提供商", marker: ".app-main .app-container" },
  { path: "/ai/agent", name: "智能体", marker: ".app-main .app-container" },
  { path: "/ai/app", name: "应用", marker: ".app-main .app-container" },
  { path: "/ai/logs", name: "调用日志", marker: ".app-main .app-container" },
];

/** 忽略这些噪声（与页面健康无关） */
const IGNORE = [
  /favicon/i,
  /ResizeObserver loop/i,
  /Download the Vue Devtools/i,
  /\[vite\]/i,
  /sourcemap/i,
];

function interesting(text: string): boolean {
  return !IGNORE.some((re) => re.test(text));
}

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 3_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
  const close = page.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 3_000 }).catch(() => {});
}

test("AI 模块页面健康审计", async ({ page }) => {
  // 12 个页面 × 每页约 4 秒，默认 60 秒不够
  test.setTimeout(600_000);
  const report: string[] = [];

  for (const p of PAGES) {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const badRequests: string[] = [];
    const failedReqs: string[] = [];

    const onConsole = (m: { type: () => string; text: () => string }) => {
      if (m.type() === "error" && interesting(m.text())) {
        consoleErrors.push(m.text().slice(0, 300));
      }
    };
    const onPageError = (e: Error) => {
      if (interesting(e.message)) pageErrors.push(e.message.slice(0, 300));
    };
    const onResponse = (r: { status: () => number; url: () => string }) => {
      const s = r.status();
      if (s >= 400 && interesting(r.url())) {
        badRequests.push(`${s} ${r.url().replace(/^https?:\/\/[^/]+/, "").slice(0, 120)}`);
      }
    };
    // **关键**：控制台只说 "ERR_NAME_NOT_RESOLVED"，不说连的是谁。这里抓完整 URL。
    const onReqFailed = (r: { url: () => string; failure: () => { errorText: string } | null }) => {
      const f = r.failure();
      const url = r.url();
      if (!f || !interesting(url)) return;
      failedReqs.push(`${f.errorText} → ${url.slice(0, 150)}`);
    };

    page.on("console", onConsole as never);
    page.on("pageerror", onPageError);
    page.on("response", onResponse as never);
    page.on("requestfailed", onReqFailed as never);

    let rendered = 0;
    let crashed = "";
    try {
      await page.goto(`/#${p.path}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
      await dismissTour(page);
      await page.waitForTimeout(3_500);
      rendered = await page.locator(p.marker).count();
      // 页面里是否出现了"明显的错误提示"（Element Plus 的 message / 空状态文案）
      const errBox = page.locator(".el-message--error, .el-alert--error");
      if (await errBox.count()) {
        crashed = (await errBox.first().innerText().catch(() => "")).slice(0, 120);
      }
    } catch (e) {
      crashed = `导航失败: ${(e as Error).message.slice(0, 120)}`;
    }

    page.off("console", onConsole as never);
    page.off("pageerror", onPageError);
    page.off("response", onResponse as never);
    page.off("requestfailed", onReqFailed as never);

    const lines: string[] = [];
    lines.push(`\n===== ${p.name}  ${p.path} =====`);
    lines.push(`  主体渲染: ${rendered > 0 ? "✅ 有" : "❌ 无（可能是白屏）"}`);
    if (crashed) lines.push(`  ⚠️ 页面错误提示: ${crashed}`);
    lines.push(`  控制台错误 ${consoleErrors.length} 条:`);
    for (const t of consoleErrors.slice(0, 6)) lines.push(`    - ${t}`);
    lines.push(`  未捕获异常 ${pageErrors.length} 条:`);
    for (const t of pageErrors.slice(0, 6)) lines.push(`    - ${t}`);
    lines.push(`  失败请求 ${badRequests.length} 条:`);
    for (const t of [...new Set(badRequests)].slice(0, 8)) lines.push(`    - ${t}`);
    lines.push(`  连接失败 ${failedReqs.length} 条:`);
    for (const t of [...new Set(failedReqs)].slice(0, 8)) lines.push(`    - ${t}`);

    await page.screenshot({
      path: `e2e/audit${p.path.replace(/\//g, "_")}.png`,
      fullPage: false,
    });

    report.push(lines.join("\n"));
  }

  // eslint-disable-next-line no-console
  console.log("\n\n########## 页面健康审计报告 ##########" + report.join("\n") + "\n########## 报告结束 ##########\n");
});
