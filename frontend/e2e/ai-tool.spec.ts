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

  // 切换到自定义 HTTP 工具标签页，新增按钮可见。
  // 引导遮罩可能拦截指针事件，直接派发 click（与 ai-prompt.spec.ts / ai-model.spec.ts 一致）
  const httpTab = page.getByRole("tab", { name: "自定义 HTTP 工具" });
  await httpTab.evaluate((el) => (el as HTMLElement).click());
  await expect(page.getByRole("button", { name: "新增工具" })).toBeVisible({ timeout: 10_000 });
});
