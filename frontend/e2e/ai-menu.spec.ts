import { test, expect, type Page } from "@playwright/test";

// 关闭引导遮罩（Guide 组件无关闭按钮，仅底部「跳过」可退出）
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  const skip = tour.getByRole("button", { name: "跳过" }).first();
  const close = tour.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  await page
    .evaluate(() => {
      document.querySelectorAll(".el-tour").forEach((el) => el.remove());
    })
    .catch(() => {});
}

test("AI 菜单：智能问数为独立目录，展开含 4 个子菜单，数据资产已并入", async ({ page }) => {
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });

  // 「智能问数」应为 AI 下的可展开目录（二级子菜单）
  const group = aiSub.locator(".el-sub-menu", { hasText: /智能问数/ }).first();
  if (!(await group.isVisible().catch(() => false))) {
    await aiSub.locator(":scope > .el-sub-menu__title").first().click();
    await page.waitForTimeout(400);
  }
  await expect(group.locator(":scope > .el-sub-menu__title")).toContainText("智能问数", {
    timeout: 10_000,
  });

  // 展开目录，断言 4 个子菜单均出现
  await group.locator(":scope > .el-sub-menu__title").click();
  await page.waitForTimeout(500);
  for (const item of ["数据与集成", "智能问数", "问数评测", "自定义报表"]) {
    await expect(group.locator(".el-menu-item", { hasText: item }).first()).toBeVisible();
  }

  // 数据资产已并入「数据与集成」，不出现在菜单
  await expect(aiSub.getByText("数据资产", { exact: true })).toHaveCount(0);

  // 已下线页面不出现在菜单中
  for (const removed of ["运行台", "AI报告", "会话记忆"]) {
    await expect(aiSub.getByText(removed, { exact: true })).toHaveCount(0);
  }
});
