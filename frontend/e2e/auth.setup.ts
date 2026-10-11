import { test as setup, expect } from "@playwright/test";

const authFile = "e2e/.auth/user.json";

setup("authenticate", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  // 显式填账号密码（不要依赖"登录页预填"——实测会失效导致登录失败）
  // 按钮文案为 i18n 的 "登 录"（中间含空格），用正则兼容
  const inputs = page.locator("input");
  await inputs.nth(0).fill("admin");
  await inputs.nth(1).fill("123456");
  await page.getByRole("button", { name: /登\s*录/ }).click();
  await page.waitForURL(/#\/(home|dashboard)/, { timeout: 30_000 });
  await expect(page.locator(".app-main, .el-main").first()).toBeVisible();
  await page.context().storageState({ path: authFile });
});
