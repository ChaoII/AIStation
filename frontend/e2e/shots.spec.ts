import { test, type Page } from "@playwright/test";

/**
 * 截图核对（无头，不依赖可见桌面）：问数页 + 报表页。
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

test("截图：问数页（澄清/存为报表/反馈）", async ({ page }) => {
  await prepare(page, "/#/ai/query");
  // 先提一个**快路径**问题（秒回），让行内按钮（存为报表/有用/没用）渲染出来
  const ta = page.locator("textarea").first();
  await ta.fill("统计每个摄像头的告警数量");
  await page.getByRole("button", { name: "提问" }).click();
  await page.waitForSelector(".q-msg__fb", { timeout: 60_000 });
  await page.waitForTimeout(1_200);
  await page.screenshot({ path: "e2e/shots/ai-query.png", fullPage: true });
});

test("截图：报表页（列表/运行/确认/删除）", async ({ page }) => {
  await prepare(page, "/#/ai/query/reports");
  await page.screenshot({ path: "e2e/shots/ai-query-reports.png", fullPage: true });
});
