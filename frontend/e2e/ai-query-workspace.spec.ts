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

test("问数工作台：默认落在智能问数页签", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);

  await expect(page.locator(".ai-query-workspace")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".ai-query-page")).toBeVisible({ timeout: 20_000 });
  expect(page.url()).toContain("tab=ask");
});

test("问数工作台：页签切换并保留各页 DOM", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);

  await page.getByRole("tab", { name: "问数评测" }).click();
  await expect(page.locator(".ai-eval-page")).toBeVisible({ timeout: 20_000 });

  await page.getByRole("tab", { name: "数据与集成" }).click();
  await expect(page.locator(".ai-integration-page")).toBeVisible({ timeout: 20_000 });
  // 切走后已渲染页 DOM 保留（v-show），不重新初始化
  await expect(page.locator(".ai-eval-page")).toHaveCount(1);
});

test("问数工作台：tab 参数直达指定页签，非法值回落智能问数", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query?tab=reports", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);
  await expect(page.locator(".ai-query-reports")).toBeVisible({ timeout: 20_000 });

  await page.goto("/#/ai/query?tab=illegal", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await expect(page.locator(".ai-query-page")).toBeVisible({ timeout: 20_000 });
});

test("旧地址重定向：eval/reports/integration/asset 均落到工作台对应页签", async ({ page }) => {
  test.setTimeout(180_000);

  const cases: Array<{ from: string; urlPart: string; marker: string }> = [
    { from: "/#/ai/eval", urlPart: "tab=eval", marker: ".ai-eval-page" },
    { from: "/#/ai/query/reports", urlPart: "tab=reports", marker: ".ai-query-reports" },
    { from: "/#/ai/integration", urlPart: "tab=integration", marker: ".ai-integration-page" },
    { from: "/#/ai/asset", urlPart: "tab=integration", marker: ".ai-integration-page" },
  ];
  for (const c of cases) {
    await page.goto(c.from, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await dismissTour(page);
    await expect(page.locator(c.marker)).toBeVisible({ timeout: 20_000 });
    expect(page.url()).toContain(c.urlPart);
  }
});

test("问数工作台：切换页签保留其它 query 参数", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/#/ai/query?object_code=USER", { waitUntil: "domcontentloaded", timeout: 30_000 });
  await dismissTour(page);

  await page.getByRole("tab", { name: "问数评测" }).click();
  await expect(page.locator(".ai-eval-page")).toBeVisible({ timeout: 20_000 });
  expect(page.url()).toContain("object_code=USER");
  expect(page.url()).toContain("tab=eval");
});
