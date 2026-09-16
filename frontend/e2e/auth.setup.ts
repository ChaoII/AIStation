import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  // 登录页已预填 admin/123456（dev 关闭验证码）
  // 按钮文案为 i18n 的 "登 录"（中间含空格），用正则兼容
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await page.waitForURL(/#\/(home|dashboard)/, { timeout: 30_000 });
  await expect(page.locator(".app-main, .el-main").first()).toBeVisible();
  await page.context().storageState({ path: authFile });
});
