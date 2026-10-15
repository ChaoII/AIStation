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

test("AI 菜单：智能问数为唯一问数入口，已合并页面不出现在菜单", async ({ page }) => {
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });

  // 若子菜单未展开则点击标题展开
  const queryItem = aiSub.locator(".el-menu-item", { hasText: /智能问数/ });
  if (!(await queryItem.isVisible().catch(() => false))) {
    await aiSub.locator(".el-sub-menu__title").click();
  }

  // 智能问数必须出现在菜单中（唯一的问数入口）
  await expect(aiSub.getByText("智能问数", { exact: true })).toBeVisible();

  // 已并入工作台的四个功能页不再出现在菜单中
  for (const merged of ["数据与集成", "问数评测", "自定义报表", "数据资产"]) {
    await expect(aiSub.getByText(merged, { exact: true })).toHaveCount(0);
  }

  // 已下线页面不出现在菜单中
  for (const removed of ["运行台", "AI报告", "会话记忆"]) {
    await expect(aiSub.getByText(removed, { exact: true })).toHaveCount(0);
  }
});
