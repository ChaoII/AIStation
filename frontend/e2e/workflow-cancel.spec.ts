import { test, expect, type Page } from "@playwright/test";

// 回归护栏：工作流运行支持「停止」。
// 覆盖：运行中才出现停止按钮 → 点击弹二次确认 → 确认后中断并显示「已取消」。
// 同时把关键界面截图落到 e2e/ 供人工核对。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

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

test("工作流运行可停止：停止按钮 → 二次确认 → 已取消", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 20_000 });
  await dismissTour(page);

  // 切到「工作流」tab，打开 ccc 的内嵌编辑器
  await page.getByRole("tab", { name: "工作流" }).first().click();
  const card = page.locator(".ws-card", { hasText: "ccc" }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.locator(".ws-card__actions .el-dropdown").first().click();
  await page.locator(".el-dropdown-menu__item", { hasText: "编辑" }).first().click();

  // 编辑器打开 → 点「运行」进运行抽屉
  const runBtn = page.getByRole("button", { name: /^运行$/ }).first();
  await expect(runBtn).toBeVisible({ timeout: 20_000 });
  await runBtn.click();

  // 发送一条会持续生成的消息（注意：抽屉里还有「输入变量」textarea，在折叠面板内不可见）
  const ta = page.getByPlaceholder(/输入消息/).first();
  await expect(ta).toBeVisible({ timeout: 15_000 });
  await ta.fill("请写一段 300 字左右的文字介绍你自己");
  await page.getByRole("button", { name: /^发送$/ }).first().click();

  // 运行中：停止按钮出现（未运行时不应存在）
  const stop = page.getByRole("button", { name: /^停止$/ }).first();
  await expect(stop).toBeVisible({ timeout: 25_000 });
  await page.screenshot({ path: "e2e/wf-cancel-1-running.png", fullPage: false });

  // 点击停止 → 必须弹二次确认
  await stop.click();
  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await expect(box).toContainText("已取消");
  await page.screenshot({ path: "e2e/wf-cancel-2-confirm.png", fullPage: false });

  await box.getByRole("button", { name: "停止运行" }).click();

  // 中断后显示「已取消」（不是「运行失败」）
  await expect(page.locator(".chat-msg__cancel").first()).toBeVisible({ timeout: 40_000 });
  await expect(page.locator(".chat-msg__err").first()).toHaveCount(0);
  await page.screenshot({ path: "e2e/wf-cancel-3-cancelled.png", fullPage: false });

  // 后端记录应落成 cancelled（直接查运行历史接口核对）
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem("access_token");
    return raw ? (JSON.parse(raw) as string) : "";
  });
  const res = await page.request.get(`${API}/ai/workflows/1/run-logs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.ok()).toBeTruthy();
  const logs = (await res.json()).data as Array<{ id: number; status: string }>;
  expect(logs.some((l) => l.status === "cancelled")).toBeTruthy();
});
