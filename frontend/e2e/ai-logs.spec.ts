import { test, expect, type Page } from "@playwright/test";

// 关闭引导遮罩。Guide 组件设置了 :show-close="false"，不存在关闭按钮，仅底部「跳过」可退出。
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  // 引导可能在页面加载后才出现，短等一次；无引导则直接返回，避免无谓挂起
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;

  // 优先点「跳过」（关闭按钮在 show-close=false 时不存在，作为兜底）
  const skip = page.locator(".el-tour").getByRole("button", { name: "跳过" }).first();
  const close = page.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    // 直接派发 click，避免遮罩拦截指针事件
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }

  // 等待遮罩真正隐藏/移除，设上限避免无引导时挂住
  await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
}

test("调用日志页可打开并展示表格与筛选", async ({ page }) => {
  await page.goto("/#/ai/logs", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 页面容器与日志表格渲染
  await expect(page.locator(".ai-logs-page")).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".ai-logs-page .el-table").first()).toBeVisible({ timeout: 10_000 });
});
