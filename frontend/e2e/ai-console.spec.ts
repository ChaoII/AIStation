import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("AI 控制台与运行台可打开", async ({ page }) => {
  await page.goto("/#/ai/overview", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-console")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".ai-console h1")).toHaveText("大模型控制台");

  await page.goto("/#/ai/playground", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-console")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".ai-console h1")).toHaveText("运行台");
  await expect(page.locator(".ai-compose")).toBeVisible();
});
