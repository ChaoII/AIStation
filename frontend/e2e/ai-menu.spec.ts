import { test, expect, type Page } from "@playwright/test";

// 关闭引导遮罩（Guide 组件无关闭按钮，仅底部「跳过」可退出）
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
  const close = page.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
}

test("AI 菜单收敛为 6 项且已下线页面不出现", async ({ page }) => {
  await page.goto("/#/ai/chat", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });

  // 若子菜单未展开则点击标题展开
  const chatItem = aiSub.locator(".el-menu-item", { hasText: /智能助手/ });
  if (!(await chatItem.isVisible().catch(() => false))) {
    await aiSub.locator(".el-sub-menu__title").click();
  }

  // 保留的 6 项（聊天来自种子，其余由 _ensure_ai_menus 创建）
  await expect(aiSub.locator(".el-menu-item .menu-title")).toHaveCount(6);
  for (const title of ["AI智能助手", "模型配置", "提示词", "工具中心", "AI应用", "调用日志"]) {
    await expect(aiSub.getByText(title, { exact: true })).toBeVisible();
  }

  // 已下线页面不出现在菜单中
  for (const removed of ["控制台", "运行台", "提供商", "AI报告", "会话记忆"]) {
    await expect(aiSub.getByText(removed, { exact: true })).toHaveCount(0);
  }
});
