import { test, type Page } from "@playwright/test";

/**
 * 截图核对（无头，不依赖可见桌面）：问数页 + 报表页。
 *
 * 复用 `auth.setup.ts` 保存的登录态（storageState），无需重复登录。
 * 产物：`frontend/e2e/shots/*.png`。
 */
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 4_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
  const close = page.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 4_000 }).catch(() => {});
}

test("截图：问数页（澄清/存为报表/反馈）", async ({ page }) => {
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".app-main .app-container", { timeout: 15_000 });
  await dismissTour(page);
  await page.waitForTimeout(1_500);
  await page.screenshot({ path: "e2e/shots/ai-query.png", fullPage: true });
});

test("截图：报表页（列表/运行/确认/删除）", async ({ page }) => {
  await page.goto("/#/ai/query/reports", { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".app-main .app-container", { timeout: 15_000 });
  await dismissTour(page);
  await page.waitForTimeout(1_500);
  await page.screenshot({ path: "e2e/shots/ai-query-reports.png", fullPage: true });
});
