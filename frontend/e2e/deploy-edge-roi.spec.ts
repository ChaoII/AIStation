import { test, expect, type Page } from "@playwright/test";

/** 关闭可能遮挡点击的新手引导 Tour（el-tour），避免拦截交互。 */
async function dismissTour(page: Page) {
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) {
    await close.click({ force: true }).catch(() => {});
  }
  await page.keyboard.press("Escape").catch(() => {});
  await page.locator(".el-tour").waitFor({ state: "hidden", timeout: 3000 }).catch(() => {});
}

test("布控页可选择推理设备并打开 ROI 编辑器", async ({ page }) => {
  await page.goto("/#/video/deploy", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  await dismissTour(page);

  await page.getByRole("button", { name: /新增/ }).first().click({ force: true });
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();

  // 推理设备下拉存在且含「本机 / 纯云端」选项
  const deviceItem = dialog.locator(".el-form-item", { hasText: "推理设备" });
  await deviceItem.locator(".el-select").click();
  await expect(
    page.locator(".el-select-dropdown__item", { hasText: "本机 / 纯云端" }).first()
  ).toBeVisible();
  await page.keyboard.press("Escape");

  // ROI 编辑器区块存在
  await expect(dialog.getByText("检测区域（ROI）")).toBeVisible();
  await expect(dialog.locator(".roi-editor")).toBeVisible();

  await page.keyboard.press("Escape");
});
