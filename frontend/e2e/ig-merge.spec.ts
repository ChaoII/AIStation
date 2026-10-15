import { test, expect, type Page } from "@playwright/test";

// 关闭引导遮罩（Guide 组件无关闭按钮，仅底部「跳过」可退出）
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  for (let i = 0; i < 8; i++) {
    const skip = tour.getByRole("button", { name: "跳过" }).first();
    if (await skip.count()) {
      await skip.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
    }
    await page.waitForTimeout(400);
    if (!(await tour.count())) break;
  }
  await page
    .evaluate(() => {
      document.querySelectorAll(".el-tour").forEach((el) => el.remove());
    })
    .catch(() => {});
  await tour.waitFor({ state: "detached", timeout: 5_000 }).catch(() => {});
}

test("数据资产/数据与集成已并入智能问数工作台", async ({ page }) => {
  test.setTimeout(120_000);
  // ① 老地址 /ai/asset 与 /ai/integration 应重定向到工作台「数据与集成」页签
  for (const from of ["/#/ai/asset", "/#/ai/integration"]) {
    await page.goto(from, { waitUntil: "domcontentloaded", timeout: 30000 });
    await dismissTour(page);
    await expect(page.locator(".ai-integration-page")).toBeVisible({ timeout: 20_000 });
    expect(page.url()).toContain("tab=integration");
  }
  // ② 菜单里不应再有「数据资产」/「数据与集成」/「问数评测」，但「智能问数」仍在
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30000 });
  await dismissTour(page);
  await expect(page.locator(".ai-query-workspace")).toBeVisible({ timeout: 20_000 });
  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });
  const queryItem = aiSub.locator(".el-menu-item", { hasText: /智能问数/ });
  if (!(await queryItem.isVisible().catch(() => false))) {
    await aiSub.locator(".el-sub-menu__title").click();
  }
  await expect(aiSub.getByText("智能问数", { exact: true })).toBeVisible();
  for (const merged of ["数据资产", "数据与集成", "问数评测"]) {
    await expect(aiSub.getByText(merged, { exact: true })).toHaveCount(0);
  }
});
