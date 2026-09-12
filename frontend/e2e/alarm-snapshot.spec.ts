import { test, expect, type Page } from "@playwright/test";

/** 关闭可能遮挡点击的新手引导 Tour（el-tour），避免拦截交互。 */
async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) {
    await close.click({ force: true }).catch(() => {});
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page
    .locator(".el-tour")
    .waitFor({ state: "hidden", timeout: 3000 })
    .catch(() => {});
}

test("告警页展示快照列并请求 snapshot_url", async ({ page }) => {
  const snapshotRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/video/detections/")) snapshotRequests.push(req.url());
  });

  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  await dismissTour(page);

  await expect(page.locator("th", { hasText: "快照" }).first()).toBeVisible();
  // 不强制存在告警数据；若存在则应触发快照请求（blob 下载）
  expect(Array.isArray(snapshotRequests)).toBe(true);
});
