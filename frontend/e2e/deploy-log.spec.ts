import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("部署页可打开详情抽屉并加载日志", async ({ page }) => {
  await page.goto("/#/train/deploy", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  const btn = page.locator(".el-table__body-wrapper button:has-text('详情')").first();
  if (await btn.count()) {
    await btn.evaluate((el) => (el as HTMLElement).click());
    await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
    await expect(page.locator(".el-drawer:visible").getByText("部署日志")).toBeVisible();
  } else {
    await expect(page.locator(".app-main .app-container").first()).toBeVisible();
  }
});
