import { test, expect, type Page } from "@playwright/test";

// 回归护栏：工作流运行的「停止」能力 + 轨迹合并显示。
// 两个用例分开写：取消用例只断言取消相关 UI/DB；轨迹合并用「正常跑完」判定，
// 避免把两件事耦合在一起变成时序抽奖（实测踩过：等轨迹出现再点停止，运行已结束）。

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

/** 打开工作台里 ccc 的内嵌编辑器，并进入运行抽屉。 */
async function openRunDrawer(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 20_000 });
  await dismissTour(page);

  await page.getByRole("tab", { name: "工作流" }).first().click();
  const card = page.locator(".ws-card", { hasText: "ccc" }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.locator(".ws-card__actions .el-dropdown").first().click();
  await page.locator(".el-dropdown-menu__item", { hasText: "编辑" }).first().click();

  const runBtn = page.getByRole("button", { name: /^运行$/ }).first();
  await expect(runBtn).toBeVisible({ timeout: 20_000 });
  await runBtn.click();
  await expect(page.getByPlaceholder(/输入消息/).first()).toBeVisible({ timeout: 15_000 });
}

/** 发送一条消息（要求长输出，给「停止」留出可中断窗口）。 */
async function sendLongPrompt(page: Page, text: string) {
  await page.getByPlaceholder(/输入消息/).first().fill(text);
  await page.getByRole("button", { name: /^发送$/ }).first().click();
}

test("工作流运行可停止：停止按钮 → 二次确认 → 已取消", async ({ page }) => {
  await openRunDrawer(page);
  await sendLongPrompt(page, "请分 10 段、每段不少于 100 字，详细介绍你自己，逐段输出，不要省略。");

  // 运行中：停止按钮出现（未运行时不存在）
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
  await box.waitFor({ state: "hidden", timeout: 10_000 }).catch(() => {});

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

test("运行轨迹合并：同一节点只占一行，不留「执行中」", async ({ page }) => {
  await openRunDrawer(page);
  await sendLongPrompt(page, "用一句话说明什么是工作流。");

  // 轨迹在运行结束后才渲染（帧有缓冲），这里就是完成信号
  const trace = page.locator(".chat-trace .trace-item");
  await expect(trace.first()).toBeVisible({ timeout: 90_000 });

  const labels = await trace.locator(".trace-item__label").allInnerTexts();
  expect(labels.length).toBeGreaterThan(0);
  // 同一节点不应出现「执行中」+「终态」两行（本工作流是线性图；循环/迭代才允许重复）
  expect(new Set(labels).size).toBe(labels.length);
  await expect(
    page.locator(".chat-trace .trace-item__status", { hasText: "执行中" })
  ).toHaveCount(0);
});
