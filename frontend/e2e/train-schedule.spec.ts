import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("训练页定时训练 Tab 可打开新建弹窗", async ({ page }) => {
  await page.goto("/#/train/task", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await page
    .locator(".el-tabs__item:has-text('定时训练')")
    .first()
    .evaluate((el) => (el as HTMLElement).click());
  const btn = page.getByRole("button", { name: "新建定时计划" });
  await btn.waitFor({ state: "visible", timeout: 10_000 });
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-dialog")).toBeVisible();
  await expect(page.locator(".el-dialog").getByText("cron 表达式")).toBeVisible();
  await page.keyboard.press("Escape");
});
