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

test("边缘设备页可加载并打开新增弹窗", async ({ page }) => {
  await page.goto("/#/video/edge", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".tags-item.active .tag-text").first()).toHaveText("边缘设备");
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  await dismissTour(page);

  // 打开新增弹窗并校验必填项
  await page
    .getByRole("button", { name: /新增|添加|Add/i })
    .first()
    .click({ force: true });
  await expect(page.locator(".el-dialog")).toBeVisible();
  await expect(page.locator(".el-dialog").getByLabel("设备名称")).toBeVisible();
  await page.keyboard.press("Escape");
});
