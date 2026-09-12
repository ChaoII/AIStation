import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("数据集页可打开导出历史抽屉", async ({ page }) => {
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  // 固定列克隆层会拦截指针事件：直接派发原生 click 到绑定元素
  const btn = page.locator(".el-table__body-wrapper button:has-text('导出历史')").first();
  await btn.waitFor({ state: "visible", timeout: 15_000 });
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
});
