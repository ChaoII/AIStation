import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("模型配置页可打开新增弹窗", async ({ page }) => {
  await page.goto("/#/ai/model", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  const btn = page.getByRole("button", { name: /新增/ }).first();
  await btn.waitFor({ state: "visible", timeout: 10_000 });
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-dialog")).toBeVisible();
  await expect(page.locator(".el-dialog").getByText("模型名")).toBeVisible();
  await page.keyboard.press("Escape");
});
