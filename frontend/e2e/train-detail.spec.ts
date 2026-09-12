import { test, expect, type Page } from "@playwright/test";

// 回归护栏：训练详情页指标卡按框架展示。
// 通过拦截任务详情接口注入不同框架任务（避免依赖真实训练产物），
// 覆盖 PaddleX det/rec、YOLO 检测、YOLO 分类四类指标规格。

const TASK_ID = 9001;

function baseTask(overrides: Record<string, any>) {
  return {
    id: TASK_ID,
    name: "e2e-train-detail",
    framework: "paddlex",
    status: "success",
    progress: 100,
    docker_image: "paddlex:latest",
    hyperparams: {},
    metrics_log: [],
    best_metrics: null,
    last_metrics: null,
    model_repo_id: null,
    error_log: null,
    started_at: "2026-09-12 10:00:00",
    finished_at: "2026-09-12 10:05:00",
    ...overrides,
  };
}

async function openMetricCard(page: Page, data: Record<string, any>) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.route(`**/train/task/${TASK_ID}/detail`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "success", data }),
    })
  );
  await page.route(`**/train/task/${TASK_ID}/logs`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 0, msg: "success", data: { logs: "" } }),
    })
  );
  await page.goto(`/#/train/task/${TASK_ID}`, { waitUntil: "domcontentloaded" });
  const card = page.locator(".section-card", { hasText: "训练指标" }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  return card;
}

test("PaddleX det：展示 HMean/Precision/Recall + 单一 Loss", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseTask({
      hyperparams: { mode: "det" },
      last_metrics: { epoch: 2, total_epochs: 10, loss: 2.4, hmean: 0.71, precision: 0.75, recall: 0.95 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^HMean$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Precision$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Recall$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Box Loss$/ })).toHaveCount(0);
  // 0-1 比例转百分比
  await expect(
    card.locator(".metric-item").filter({ hasText: /HMean/ }).locator(".metric-val")
  ).toHaveText("71.0%");
});

test("PaddleX rec：展示 Acc + 单一 Loss", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseTask({
      hyperparams: { mode: "rec" },
      last_metrics: { epoch: 5, total_epochs: 10, loss: 1.2, acc: 0.88 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Acc$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^HMean$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /Acc/ }).locator(".metric-val")
  ).toHaveText("88.0%");
});

test("YOLO 检测：保留 Box/Cls/Dfl Loss + mAP/PR 指标", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseTask({
      framework: "ultralytics",
      docker_image: "ultralytics/ultralytics:latest",
      last_metrics: {
        epoch: 10,
        total_epochs: 10,
        box_loss: 1.2345,
        cls_loss: 2.3456,
        dfl_loss: 3.4567,
        map50: 0.8,
        map5095: 0.6,
        precision: 0.7,
        recall: 0.75,
      },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Box Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Cls Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Dfl Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50:95$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Precision$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Recall$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^HMean$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /mAP@50/ }).first().locator(".metric-val")
  ).toHaveText("80.0%");
});

test("YOLO 分类（运行中）：实时 5 列汇总解析为 Top1/Top5", async ({ page }) => {
  // 通过 WebSocket 推送训练日志：先给出一轮进度行，再给分类验证汇总（5 列）
  await page.routeWebSocket(/train\/ws\/train\/logs/, async (ws) => {
    // 等页面完成 WS onmessage 挂载后再推送
    await new Promise((r) => setTimeout(r, 500));
    ws.send("      1/10      1.2345G      0.5000      0.4000");
    ws.send("                   all        100        100      0.9500      0.9900");
  });
  const card = await openMetricCard(
    page,
    baseTask({
      framework: "ultralytics",
      docker_image: "ultralytics/ultralytics:latest",
      status: "running",
      // 不放 -cls 模型信号，强制依赖实时指标键（top1/top5）推断分类
      hyperparams: {},
      last_metrics: null,
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top1$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top5$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Precision$/ })).toHaveCount(0);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Recall$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /Top1/ }).locator(".metric-val")
  ).toHaveText("95.0%");
});

test("YOLO 分类：展示 Top1/Top5 + 单一 Loss", async ({ page }) => {
  const card = await openMetricCard(
    page,
    baseTask({
      framework: "ultralytics",
      docker_image: "ultralytics/ultralytics:latest",
      last_metrics: { epoch: 10, total_epochs: 10, box_loss: 0.5, top1: 0.9, top5: 0.99 },
    })
  );
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top1$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Top5$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^Loss$/ })).toHaveCount(1);
  await expect(card.locator(".metric-lbl").filter({ hasText: /^mAP@50$/ })).toHaveCount(0);
  await expect(
    card.locator(".metric-item").filter({ hasText: /Top1/ }).locator(".metric-val")
  ).toHaveText("90.0%");
});
