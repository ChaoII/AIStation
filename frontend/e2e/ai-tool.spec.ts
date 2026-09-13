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

test("工具中心可打开、切换标签页并启停内置工具", async ({ page }) => {
  await page.goto("/#/ai/tool", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const tabs = page.locator(".el-tabs");
  await expect(tabs).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("tab", { name: "内置工具" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "自定义 HTTP 工具" })).toBeVisible();

  // 内置工具表格与开关渲染
  const firstSwitch = page.locator(".el-switch").first();
  await expect(firstSwitch).toBeVisible({ timeout: 10_000 });

  // 切换内置工具开关并断言状态变化，随后还原
  const before = await firstSwitch.getAttribute("aria-checked");
  await firstSwitch.evaluate((el) => (el as HTMLElement).click());
  await expect(firstSwitch).not.toHaveAttribute("aria-checked", before ?? "false", {
    timeout: 10_000,
  });
  await firstSwitch.evaluate((el) => (el as HTMLElement).click());

  // 切换到自定义 HTTP 工具标签页，新增按钮可见
  await page.getByRole("tab", { name: "自定义 HTTP 工具" }).click();
  await expect(page.getByRole("button", { name: "新增工具" })).toBeVisible({ timeout: 10_000 });
});
