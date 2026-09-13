import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page
    .locator(".el-tour")
    .waitFor({ state: "visible", timeout: 2500 })
    .catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("AI 控制台与运行台可打开", async ({ page }) => {
  await page.goto("/#/ai/overview", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".el-card").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("大模型控制台")).toBeVisible();

  await page.goto("/#/ai/playground", { waitUntil: "domcontentloaded" });
  await expect(page.locator("textarea").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();

  await dismissTour(page);
});
