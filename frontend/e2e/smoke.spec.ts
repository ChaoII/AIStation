import { test, expect } from "@playwright/test";

// routePath -> 该页面在标签栏中的标题（来自后端菜单 title，确认路由命中目标页面）
const PAGES: Array<[string, string]> = [
  ["/#/annotation/dataset", "数据集管理"],
  ["/#/annotation/task", "标注任务"],
  ["/#/annotation/stats", "工作量统计"],
  ["/#/train/repo", "模型仓库"],
  ["/#/train/task", "训练任务"],
  ["/#/train/eval", "模型评估"],
  ["/#/train/predict", "模型预测"],
  ["/#/train/deploy", "模型部署"],
];

test("登录后可进入主链路各页面且无致命渲染错误", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  for (const [path, title] of PAGES) {
    // 用 domcontentloaded：部分页面有轮询/长连接，networkidle 永不满足
    await page.goto(path, { waitUntil: "domcontentloaded" });
    // 激活标签标题与目标页面一致，确认路由确实解析到该页
    await expect(page.locator(".tags-item.active .tag-text").first()).toHaveText(title);
    // 目标页面组件已挂载（.app-main 内渲染出页面根容器）
    await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
    // 页面不应出现全局异常页
    await expect(page.locator("text=系统异常")).toHaveCount(0);
  }

  expect(consoleErrors, `页面抛出未捕获异常:\n${consoleErrors.join("\n")}`).toEqual([]);
});
