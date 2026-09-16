import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("模型仓库页可打开版本抽屉", async ({ page }) => {
  await page.goto("/#/train/repo", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await expect(page.locator("th", { hasText: "版本数" }).first()).toBeVisible();
  const btn = page.locator(".el-table__body-wrapper button:has-text('版本')").first();
  if (await btn.count()) {
    await btn.evaluate((el) => (el as HTMLElement).click());
    await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
  }
});
