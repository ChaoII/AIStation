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

test("数据资产并入数据与集成；智能问数为独立目录含 4 个子菜单", async ({ page }) => {
  test.setTimeout(120_000);
  // ① /ai/asset 应重定向到数据与集成页；/ai/integration 直接可访问
  for (const [from, urlPart] of [
    ["/#/ai/asset", "/ai/integration"],
    ["/#/ai/integration", "/ai/integration"],
  ] as Array<[string, string]>) {
    await page.goto(from, { waitUntil: "domcontentloaded", timeout: 30000 });
    await dismissTour(page);
    await expect(page.locator(".ai-integration-page")).toBeVisible({ timeout: 20_000 });
    expect(page.url()).toContain(urlPart);
  }

  // ② 菜单：智能问数为独立目录，展开含 4 个子菜单；数据资产不在菜单
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30000 });
  await dismissTour(page);
  await expect(page.locator(".ai-query-page")).toBeVisible({ timeout: 20_000 });
  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });
  const group = aiSub.locator(".el-sub-menu", { hasText: /智能问数/ }).first();
  if (!(await group.isVisible().catch(() => false))) {
    await aiSub.locator(":scope > .el-sub-menu__title").first().click();
    await page.waitForTimeout(400);
  }
  await group.locator(":scope > .el-sub-menu__title").click();
  await page.waitForTimeout(500);
  for (const item of ["数据与集成", "智能问数", "问数评测", "自定义报表"]) {
    await expect(group.locator(".el-menu-item", { hasText: item }).first()).toBeVisible();
  }
  await expect(aiSub.getByText("数据资产", { exact: true })).toHaveCount(0);
});
