import { expect, test, type Page } from "@playwright/test";

/**
 * 截图核对（无头，不依赖可见桌面）：问数页 + 报表页 + 参数定义/运行弹窗。
 *
 * 复用 `auth.setup.ts` 保存的登录态（storageState），无需重复登录。
 * 产物：`frontend/e2e/shots/*.png`。
 */
async function dismissTour(page: Page) {
  // 首次登录会弹"菜单引导"浮层（localStorage.guideVisible），会挡住截图 → 兜底点掉
  for (let i = 0; i < 3; i++) {
    const skip = page.getByRole("button", { name: "跳过" }).first();
    if ((await skip.count()) && (await skip.isVisible().catch(() => false))) {
      await skip.click({ force: true }).catch(() => {});
      await page.waitForTimeout(400);
      continue;
    }
    break;
  }
}

/** 关掉引导浮层（不依赖它的组件类名）。 */
async function prepare(page: Page, hash: string) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("guideVisible", "false");
    } catch {
      /* ignore */
    }
  });
  await page.goto(hash, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".app-main .app-container", { timeout: 15_000 });
  await dismissTour(page);
  await page.waitForTimeout(1_200);
}

test("截图：问数页（召回证据 / 存为报表 / 反馈）", async ({ page }) => {
  await prepare(page, "/#/ai/query");
  // 慢路径问题：会走本体/语义检索 → 结果下应出现「召回的表」标签
  const ta = page.locator("textarea").first();
  await ta.fill("统计每个摄像头的告警数量");
  await page.getByRole("button", { name: "提问" }).click();
  await page.waitForSelector(".q-msg__fb", { timeout: 90_000 });
  await page.waitForTimeout(1_500);
  await page.screenshot({ path: "e2e/shots/ai-query.png", fullPage: true });
  // 闭环证据：召回标签必须渲染（否则"本体怎么进来"在界面上看不见）
  const recall = page.locator(".q-msg__ont");
  expect(await recall.count()).toBeGreaterThan(0);
});

test("截图：报表页（参数列 + 参数按钮）", async ({ page }) => {
  await prepare(page, "/#/ai/query/reports");
  await page.waitForTimeout(1_000);
  await page.screenshot({ path: "e2e/shots/ai-query-reports.png", fullPage: true });
});

test("截图：报表参数定义弹窗（演示报表，含自动抽取的参数）", async ({ page }) => {
  await prepare(page, "/#/ai/query/reports");
  await page.waitForTimeout(1_000);
  // 演示报表在最后一行（R_DEMO_PARAMS，含 {min_alarm}）
  await page.locator("tbody tr").last().getByRole("button", { name: "参数" }).click();
  await page.waitForSelector(".el-dialog__title", { timeout: 10_000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: "e2e/shots/ai-report-params.png", fullPage: true });
  // 参数编辑器必须**有内容**（自动抽取生效），否则"运行表单是死的"老问题又回来了
  await expect(page.locator(".el-dialog__body tbody tr")).not.toHaveCount(0);
});

test("截图：报表运行弹窗（按类型渲染 + 必填校验）", async ({ page }) => {
  await prepare(page, "/#/ai/query/reports");
  await page.waitForTimeout(1_000);
  await page.locator("tbody tr").last().getByRole("button", { name: "运行" }).click();
  await page.waitForTimeout(800);
  // 不填必填直接执行 → 必须出现前端校验提示（不静默失败）
  await page.getByRole("button", { name: "执行", exact: true }).click();
  await page.waitForTimeout(600);
  await expect(page.locator(".el-dialog .el-alert--error")).toContainText("必填");
  await page.screenshot({ path: "e2e/shots/ai-report-run.png", fullPage: true });
});
