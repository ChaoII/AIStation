import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("数据集页可打开数据清洗抽屉", async ({ page }) => {
  await page.goto("/#/annotation/dataset", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  // 「数据清洗」已收入行内「更多」下拉：先点第一行的「更多」，再选「数据清洗」
  const moreBtn = page.locator(".el-table__body-wrapper tr").first().getByRole("button", { name: "更多" });
  await moreBtn.waitFor({ state: "visible", timeout: 15_000 });
  await moreBtn.evaluate((el) => (el as HTMLElement).click());
  const item = page.getByRole("menuitem", { name: "数据清洗", exact: true }).first();
  await item.waitFor({ state: "visible", timeout: 10_000 });
  await item.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-drawer:visible")).toHaveCount(1);
  await expect(page.locator(".el-drawer:visible").getByText("健康检查")).toBeVisible();
});
