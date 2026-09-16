import { test, expect, type Page } from "@playwright/test";

// 回归护栏：评估详情页指标卡按框架展示，且导出对话框关联版本 id。
// 通过拦截评估详情接口注入不同框架的评估结果（不依赖真实评估产物），
// 覆盖 PaddleX det/rec、YOLO 分类、YOLO 检测四类指标规格。

const EVAL_ID = 9101;

function baseEval(overrides: Record<string, any>) {
  return {
    id: EVAL_ID,
    model_repo_id: 77,
    model_id: 7788,
    eval_dataset_id: 1,
    framework: "paddlex",
    hyperparams: {},
    metrics: {},
    status: "success",
    progress: 100,
    log: "",
    error_log: null,
    metrics_log: [],
    best_metrics: null,
    last_metrics: null,
    started_at: "2026-09-12 10:00:00",
    finished_at: "2026-09-12 10:05:00",
    created_time: "2026-09-12 09:59:00",
    ...overrides,
  };
}

async function openMetricCard(page: Page, data: Record<string, any>) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.route(`**/train/eval/${EVAL_ID}/detail`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "success", data }),
    })
  );
  await page.route(`**/train/eval/${EVAL_ID}/logs`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "success", data: { logs: "" } }),
    })
  );
  await page.route("**/train/system/tempdir", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "success", data: { tempdir: "/tmp" } }),
    })
  );
  await page.goto(`/#/train/eval/${EVAL_ID}`, { waitUntil: "domcontentloaded" });
  const card = page.locator(".section-card", { hasText: "评估指标" }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  return card;
}

test("PaddleX det：评估详情展示 HMean/Precision/Recall", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseEval({
      framework: "paddlex",
      hyperparams: { mode: "det" },
      metrics: { hmean: 0.71, precision: 0.75, recall: 0.95 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^HMean$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Precision$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Recall$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /HMean/ }).locator(".metric-val")
  ).toHaveText("71.0%");
});

test("PaddleX rec：评估详情展示 Acc", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseEval({
      framework: "paddlex",
      hyperparams: { mode: "rec" },
      metrics: { acc: 0.88 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Acc$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^HMean$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /Acc/ }).locator(".metric-val")
  ).toHaveText("88.0%");
});

test("YOLO 分类：评估详情展示 Top1/Top5", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseEval({
      framework: "ultralytics",
      metrics: { top1: 0.9, top5: 0.99 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top1$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top5$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /Top1/ }).locator(".metric-val")
  ).toHaveText("90.0%");
});

test("YOLO 检测：评估详情展示 mAP/Precision/Recall", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseEval({
      framework: "ultralytics",
      metrics: { map50: 0.8, map5095: 0.6, precision: 0.7, recall: 0.75 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50:95$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Precision$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Recall$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top1$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /mAP@50/ }).first().locator(".metric-val")
  ).toHaveText("80.0%");
});
