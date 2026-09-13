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

test("智能助手输入框铺满且提示文案正确", async ({ page }) => {
  await page.goto("/#/ai/chat", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  const textarea = page.locator(".message-input textarea");
  await expect(textarea).toBeVisible({ timeout: 10_000 });

  // placeholder 含「输入消息」且不再出现「FA助手」
  const placeholder = await textarea.getAttribute("placeholder");
  expect(placeholder).toContain("输入消息");
  expect(placeholder).not.toContain("FA助手");

  // 输入框铺满聊天区：输入区容器宽度 > 600px
  const box = await page.locator(".message-input").boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(600);
});

test("带未知 app_id 打开智能助手不崩溃", async ({ page }) => {
  await page.goto("/#/ai/chat?app_id=999999", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);

  // 未知应用时应用详情请求失败应被吞掉，页面照常渲染输入框
  await expect(page.locator(".message-input textarea")).toBeVisible({ timeout: 10_000 });
});
