import { test, expect, type Page } from "@playwright/test";

// 关闭引导遮罩（Guide 组件无关闭按钮，仅底部「跳过」可退出）
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  // 等待引导出现（应用加载后可能延时渲染）；未出现则说明无引导
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (appeared) {
    for (let i = 0; i < 20; i++) {
      const skip = tour.getByRole("button", { name: "跳过" }).first();
      const close = tour.locator(".el-tour__close").first();
      const target = (await skip.count()) ? skip : close;
      if (await target.count()) {
        await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
      }
      await page.waitForTimeout(300);
      if (!(await tour.count())) break;
    }
  }
  // 兜底：页面级移除残留遮罩（不等待元素，避免 locator.evaluate 默认等 30s）
  await page.evaluate(() => {
    document.querySelectorAll(".el-tour").forEach((el) => el.remove());
  }).catch(() => {});
  // 确认遮罩已移除后再返回，避免拦截后续点击
  await tour.waitFor({ state: "detached", timeout: 5_000 }).catch(() => {});
}

test("智能问数：AI 菜单下为独立目录，展开含 4 个子菜单，数据资产不在菜单", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);

  const aiSub = page.locator('.el-sub-menu[data-path="/ai"]').first();
  await expect(aiSub).toBeVisible({ timeout: 10_000 });
  // 若 AI 目录未展开则点击标题展开
  const queryTitle = aiSub.locator(".el-sub-menu__title", { hasText: /智能问数/ });
  if (!(await queryTitle.isVisible().catch(() => false))) {
    await aiSub.locator(".el-sub-menu__title").click();
  }
  // 「智能问数」应为可展开的目录（二级子菜单）
  const group = aiSub.locator(".el-sub-menu", { hasText: /智能问数/ }).first();
  await expect(group.locator(".el-sub-menu__title")).toContainText("智能问数", { timeout: 10_000 });
  // 展开目录
  await group.locator(".el-sub-menu__title").click();
  await page.waitForTimeout(500);
  // 4 个子菜单均可见（同名「智能问数」子项也需出现）
  for (const item of ["数据与集成", "智能问数", "问数评测", "自定义报表"]) {
    await expect(group.locator(".el-menu-item", { hasText: item })).toBeVisible();
  }
  // 数据资产已并入数据与集成，不出现在菜单
  await expect(aiSub.getByText("数据资产", { exact: true })).toHaveCount(0);
});

test("智能问数：/ai/query 渲染独立问数页（无工作台容器）", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);

  await expect(page.locator(".ai-query-page")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".ai-query-workspace")).toHaveCount(0);
});

test("智能问数：/ai/integration 渲染独立数据与集成页", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/integration", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-integration-page")).toBeVisible({ timeout: 20_000 });
});

test("智能问数：/ai/eval 渲染独立问数评测页", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/eval", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-eval-page")).toBeVisible({ timeout: 20_000 });
});

test("智能问数：/ai/query/reports 渲染独立自定义报表页", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query/reports", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-query-reports")).toBeVisible({ timeout: 20_000 });
});

test("智能问数：旧 tab 参数兼容重定向到对应独立页面，非法值留在问数页", async ({ page }) => {
  test.setTimeout(180_000);

  const cases: Array<{ from: string; urlPart: string; marker: string }> = [
    { from: "/#/ai/query?tab=integration", urlPart: "/ai/integration", marker: ".ai-integration-page" },
    { from: "/#/ai/query?tab=eval", urlPart: "/ai/eval", marker: ".ai-eval-page" },
    { from: "/#/ai/query?tab=reports", urlPart: "/ai/query/reports", marker: ".ai-query-reports" },
  ];
  for (const c of cases) {
    await page.goto(c.from, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await dismissTour(page);
    await expect(page.locator(c.marker)).toBeVisible({ timeout: 20_000 });
    expect(page.url()).toContain(c.urlPart);
  }

  // 非法值：留在 /ai/query（问数页）
  await page.goto("/#/ai/query?tab=illegal", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-query-page")).toBeVisible({ timeout: 20_000 });
  expect(page.url()).toContain("/ai/query");
});

test("智能问数：/ai/asset 重定向到数据与集成页", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/asset", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-integration-page")).toBeVisible({ timeout: 20_000 });
  expect(page.url()).toContain("/ai/integration");
});
