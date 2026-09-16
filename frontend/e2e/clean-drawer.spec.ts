import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("数据集页可打开数据清洗抽屉", async ({ page }) => {
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  const btn = page.locator(".el-table__body-wrapper button:has-text('数据清洗')").first();
  await btn.waitFor({ state: "visible", timeout: 15_000 });
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
  await expect(page.locator(".el-drawer:visible").getByText("健康检查")).toBeVisible();
});
