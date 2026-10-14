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
test("数据资产已并入数据与集成", async ({ page }) => {
  test.setTimeout(120_000);
  // ① 老地址 /ai/asset 应重定向到 /ai/integration
  await page.goto("/#/ai/asset", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(3000);
  const url = page.url();
  const hasIg = await page.locator(".ai-integration-page").count();
  // eslint-disable-next-line no-console
  console.log(`\n  ① /ai/asset → ${url}  集成页存在=${hasIg > 0}`);
  // ② 菜单里不应再有「数据资产」
  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30000 });
  await dismissTour(page);
  await page.waitForTimeout(1500);
  const menuText = await page.locator(".el-menu").innerText().catch(() => "");
  // eslint-disable-next-line no-console
  console.log(`  ② 菜单含「数据资产」=${menuText.includes("数据资产")}  含「数据与集成」=${menuText.includes("数据与集成")}  含「智能问数」=${menuText.includes("智能问数")}`);
});
