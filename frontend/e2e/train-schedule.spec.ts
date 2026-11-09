import { test, expect, type Page } from "@playwright/test";

async function dismissTour(page: Page) {
  await page.locator(".el-tour").waitFor({ state: "visible", timeout: 2500 }).catch(() => {});
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

test("训练页定时任务 Tab 可打开新建弹窗", async ({ page }) => {
  await page.goto("/#/train/task", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  // 页签已从「定时训练」改名为「定时任务」；面板是惰挂载，点完必须等按钮出现。
  // 实测偶发首次点击没生效（探针定位到 30s 也没等到按钮）→ 用真实 click + 最多重试 3 次。
  const tab = page.locator(".el-tabs__item", { hasText: "定时任务" }).first();
  const btn = page.getByRole("button", { name: "新建定时计划" }).first();
  for (let i = 0; i < 3; i++) {
    if (await tab.count()) await tab.click({ force: true }).catch(() => {});
    const shown = await btn
      .waitFor({ state: "visible", timeout: 8_000 })
      .then(() => true)
      .catch(() => false);
    if (shown) break;
    await page.waitForTimeout(500);
  }
  await btn.evaluate((el) => (el as HTMLElement).click());
  await expect(page.locator(".el-dialog")).toBeVisible();
  // 弹窗内部是 TriggerEditor：默认「定时」（每天 09:00），不再直接展示「cron 表达式」文案
  await expect(page.locator(".el-dialog").getByText("触发方式")).toBeVisible();
  await page.keyboard.press("Escape");
});
