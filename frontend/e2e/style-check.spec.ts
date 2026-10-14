import { test, type Page } from "@playwright/test";
async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
  for (let i = 0; i < 8; i++) {
    const tour = page.locator(".el-tour");
    if (!(await tour.count())) return;
    const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
    if (await skip.count()) await skip.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
    await page.waitForTimeout(400);
    if (!(await tour.isVisible().catch(() => false))) return;
  }
}
test("样式回归后视觉确认", async ({ page }) => {
  test.setTimeout(180_000);
  for (const [path, name] of [["/ai/overview", "控制台"], ["/ai/agent", "智能体"]] as const) {
    await page.goto(`/#${path}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2500);
    await dismissTour(page);
    await page.waitForTimeout(3500);
    await page.screenshot({ path: `e2e/style-${path.replace(/\//g, "_")}.png` });
    // 抽查次要文字的 computed 样式是否仍是 12px + 次要色
    const sub = page.locator(".ai-sub").first();
    const info = (await sub.count())
      ? await sub.evaluate((el) => {
          const cs = getComputedStyle(el as HTMLElement);
          return `${cs.fontSize} / ${cs.color}`;
        })
      : "(本页无 .ai-sub)";
    // eslint-disable-next-line no-console
    console.log(`  ${name}: .ai-sub 计算样式 = ${info}`);
  }
});
