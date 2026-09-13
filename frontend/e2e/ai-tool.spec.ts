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

test("工具中心卡片网格：搜索在上、配置入口与就绪开关", async ({ page }) => {
  await page.goto("/#/ai/tool", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 卡片网格存在（至少一张工具卡片）
  const cards = page.locator(".ai-tool-page .tool-card");
  await expect(cards.first()).toBeVisible({ timeout: 10_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(1);

  // 搜索表单在卡片上方（y 坐标）
  const search = page.locator(".ai-tool-page .tool-search");
  await expect(search).toBeVisible({ timeout: 10_000 });
  const searchBox = await search.boundingBox();
  const cardBox = await cards.first().boundingBox();
  expect(searchBox).not.toBeNull();
  expect(cardBox).not.toBeNull();
  expect(searchBox!.y).toBeLessThan(cardBox!.y);

  // 存在「配置」按钮
  await expect(page.getByRole("button", { name: "配置" }).first()).toBeVisible();

  // 就绪卡片开关可切换且状态变化，随后还原
  const readySwitch = page.locator(".tool-card:not(.is-not-ready) .el-switch").first();
  await expect(readySwitch).toBeVisible({ timeout: 10_000 });
  const before = await readySwitch.getAttribute("aria-checked");
  // 引导遮罩可能拦截指针事件，直接派发 click
  await readySwitch.evaluate((el) => (el as HTMLElement).click());
  await expect(readySwitch).not.toHaveAttribute("aria-checked", before ?? "false", {
    timeout: 10_000,
  });
  await readySwitch.evaluate((el) => (el as HTMLElement).click());

  // 未就绪卡片开关禁用
  const notReadySwitch = page.locator(".tool-card.is-not-ready .el-switch").first();
  await expect(notReadySwitch).toBeVisible({ timeout: 10_000 });
  await expect(notReadySwitch).toHaveClass(/is-disabled/);
});
