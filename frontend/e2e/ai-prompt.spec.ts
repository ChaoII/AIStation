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

test("提示词工作台可打开并添加块", async ({ page }) => {
  await page.goto("/#/ai/prompt", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const addButton = page.getByRole("button", { name: "添加块" }).first();
  await expect(addButton).toBeVisible({ timeout: 10_000 });

  const before = await page.locator(".block-editor").count();
  // 引导 tour 遮罩可能拦截指针事件，直接派发 click（与 ai-model.spec.ts 一致）
  await addButton.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".block-editor")).toHaveCount(before + 1);

  await expect(page.getByRole("button", { name: "保存" })).toBeVisible();
});
