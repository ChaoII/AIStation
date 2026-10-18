import { test, expect, type Page } from "@playwright/test";

// 冒烟：工作台「多类型条目聚合」在真实浏览器里正常渲染。
// 背景：该聚合原先是 workspace 直读 agent/app/workflow 三张表，现改走各模块的 list_* 接口
// （分类/启用过滤挪到 workspace 侧）——这里锁住「页面照旧、条目照旧」。

async function openWorkspace(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 25_000 });
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    await tour
      .locator(".el-tour__close")
      .first()
      .evaluate((el) => (el as HTMLElement).click())
      .catch(() => {});
    await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  }
}

test("工作台：条目聚合接口返回且卡片渲染（agent/app/workflow/cron）", async ({ page }) => {
  const itemsP = page.waitForResponse((r) => r.url().includes("/ai/workspace/items"));
  await openWorkspace(page);

  const body = (await (await itemsP).json()).data as {
    total: number;
    items: Array<{ type: string; name: string; label: string; enabled: boolean }>;
  };
  expect(body.total).toBeGreaterThan(0);
  // 聚合结果里不应出现未启用条目（过滤由 workspace 侧负责）
  expect(body.items.every((i) => i.enabled)).toBeTruthy();
  expect(new Set(body.items.map((i) => i.label)).size).toBeGreaterThanOrEqual(2);

  const cards = page.locator(".ws-card");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(1);
  await page.screenshot({ path: "e2e/ai-workspace-items.png", fullPage: false });
});
