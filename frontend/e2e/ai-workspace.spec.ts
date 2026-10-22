import { test, expect, type Page } from "@playwright/test";

// 冒烟：工作台「智能体家族」渲染在真实浏览器里正常。
// 背景：定时任务已迁出为独立菜单页 /ai/cron、应用归「AI应用」菜单，
// 工作台只服务传统智能体 + 工作流编排；类型 tab 已丢弃，类别并入过滤带的下拉。
// 后端 /ai/workspace/items 仍聚合四类（向后兼容，ALL_TYPES 未动），前端本地收窄。

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

test("工作台：聚合接口返回、卡片渲染，类别下拉只含智能体家族", async ({ page }) => {
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

  // 类别下拉（替代原顶部类型 tab）：仅 全部 / 传统智能体 / 工作流，定时任务与应用已迁出
  await page.locator(".ws-toolbar .el-select").click();
  const options = page.locator(".el-select-dropdown:visible .el-select-dropdown__item");
  await expect(options).toHaveText(["全部", "传统智能体", "工作流"]);
  await page.keyboard.press("Escape");

  // 区域隔离：分类树与内容区各自是独立卡片（参照个人工作空间布局）
  await expect(page.locator(".ws-side.el-card")).toBeVisible();
  await expect(page.locator(".ws-main.el-card")).toBeVisible();

  await page.screenshot({ path: "e2e/ai-workspace-items.png", fullPage: false });
});
