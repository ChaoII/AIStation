import { test, expect, type Page } from "@playwright/test";

/** 关闭可能遮挡点击的新手引导 Tour（不用 Escape，避免误关自动打开的弹窗）。 */
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    const close = page.locator(".el-tour__close").first();
    if (await close.count()) await close.click({ force: true }).catch(() => {});
  }
}

/** 深链首次加载存在挂载时序竞态：若弹窗未开则 reload 一次再断言。 */
async function expectAutoDialog(page: Page) {
  const container = page.locator(".app-main .app-container").first();
  const dialog = page.locator(".el-dialog");
  await expect(container).toBeVisible({ timeout: 15_000 });
  const opened = await dialog
    .waitFor({ state: "visible", timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (!opened) {
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(container).toBeVisible({ timeout: 15_000 });
  }
  await expect(dialog).toBeVisible({ timeout: 10_000 });
}

test("带 autoCreate 进入预测页会自动打开创建弹窗", async ({ page }) => {
  // 预测页仅在模型列表命中 model_id 时才自动开窗：用路由拦截注入一个模型版本
  await page.route("**/train/model/list*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: 0,
        msg: "ok",
        data: {
          items: [
            {
              id: 42,
              repo_id: 7,
              name: "mock-model",
              version: 1,
              framework: "ultralytics",
              annotation_dataset_id: 1,
            },
          ],
          total: 1,
        },
      }),
    })
  );
  await page.goto("/#/train/predict?model_id=42&model_repo_id=7&autoCreate=1", {
    waitUntil: "domcontentloaded",
  });
  await expectAutoDialog(page);
  await dismissTour(page);
  await page.keyboard.press("Escape");
});
