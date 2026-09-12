import { test, expect, type Page } from "@playwright/test";

/** 关闭可能遮挡点击的新手引导 Tour（不用 Escape，避免误关自动打开的弹窗）。 */
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("带 autoCreate 进入评估页会自动打开创建弹窗", async ({ page }) => {
  await page.goto("/#/train/eval?model_repo_id=5&autoCreate=1", {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".el-dialog")).toBeVisible({ timeout: 10_000 });
  await dismissTour(page);
  await page.keyboard.press("Escape");
});
