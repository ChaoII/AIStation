import { test, expect, type Page } from "@playwright/test";

// 冒烟：`ai_call_logs` 的**读取路径**在真实浏览器里能正常渲染，且 UI 数字与接口一致。
// 背景：本轮把这张共享表的取数收敛到读 owner（logs_center），Agent 运行看板改走它的
// `stats_by_app` 接口；这里锁住「读 owner 的页面与聚合没被改坏」。

async function openPage(page: Page, hash: string, root: string) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(hash, { waitUntil: "domcontentloaded" });
  await expect(page.locator(root).first()).toBeVisible({ timeout: 25_000 });
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

test("AI 调用日志页：统计卡与明细表正常渲染，数字与接口一致", async ({ page }) => {
  const statsP = page.waitForResponse((r) => r.url().includes("/ai/logs/stats"));
  await openPage(page, "/#/ai/logs", ".ai-logs-page");

  const body = await (await statsP).json();
  const cards = page.locator(".ai-logs-page .el-statistic");
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  expect(await cards.count()).toBeGreaterThanOrEqual(4);
  // 「总调用」必须等于接口返回值（不是初始占位 0）
  await expect(cards.first()).toContainText(String(body.data.total), { timeout: 20_000 });
  // 明细表必须有行渲染出来（库里确有数据；空态会是 el-empty）
  await expect(page.locator(".ai-logs-page .el-table__row").first()).toBeVisible({
    timeout: 20_000,
  });
  await page.screenshot({ path: "e2e/ai-logs-page.png", fullPage: false });
});

test("AI 控制台：Agent 运行看板正常渲染（聚合已收敛到 logs_center）", async ({ page }) => {
  const dashP = page.waitForResponse((r) => r.url().includes("/ai/agents/dashboard"));
  await openPage(page, "/#/ai/overview", ".ai-overview-page");

  const dash = (await (await dashP).json()).data;
  const agentCard = page
    .locator(".ai-overview-page .el-card", { hasText: "Agent 编排运行看板" })
    .first();
  await expect(agentCard).toBeVisible({ timeout: 25_000 });
  // 「累计运行」必须等于接口值：该聚合本轮已改走 logs_center.AiLogService.stats_by_app
  await expect(
    agentCard.locator(".el-statistic", { hasText: "累计运行" }).first()
  ).toContainText(String(dash.total_runs ?? 0), { timeout: 20_000 });
  await agentCard.screenshot({ path: "e2e/ai-agent-dashboard-card.png" });
  await page.screenshot({ path: "e2e/ai-overview-page.png", fullPage: false });
});
