import { test, expect } from "@playwright/test";

// 回归护栏：统计页 /#/annotation/stats 加载时不应因分页参数越界（page_size>100 触发 422）
// 导致 overview/datasetOptions 整体失败、指标卡全空。
// 说明：此处不依赖 waitForResponse —— 浏览器可能对 overview GET 走缓存而不触发 response 事件；
// 改用「捕获所有 annotation 子路径的失败响应 + 全局失败提示」作为回归判据（422 不会被缓存）。

test("统计页指标卡渲染且无请求失败", async ({ page }) => {
  const failedResponses: string[] = [];
  page.on("response", (res) => {
    const url = res.url();
    if (url.includes("/annotation/") && res.status() >= 400) {
      failedResponses.push(`${res.status()} ${url}`);
    }
  });

  // 关闭首次登录引导 tour，避免遮罩层干扰
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });

  await page.goto("/#/annotation/stats", { waitUntil: "domcontentloaded" });

  await expect(page.locator(".annotation-stats-page")).toBeVisible({ timeout: 15_000 });

  // 等待统计页请求收敛（overview + datasetOptions 均已完成，页面无轮询）
  await page.waitForLoadState("networkidle");

  // 4 张指标卡均渲染，且每张卡片渲染出数据驱动的数值（非空白）
  const values = page.locator(".annotation-stats-page .stat-card__value");
  await expect(values).toHaveCount(4);
  for (let i = 0; i < 4; i += 1) {
    await expect(values.nth(i)).toHaveText(/[\d]/);
  }
  // 数据集选择器已就绪
  await expect(page.locator(".annotation-stats-page .el-select")).toBeVisible();

  // 不应弹出全局请求失败提示
  await expect(page.locator("text=请求处理失败")).toHaveCount(0);
  expect(failedResponses, `统计页出现失败请求:\n${failedResponses.join("\n")}`).toEqual([]);
});
