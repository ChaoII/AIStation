import { test, expect, type Locator, type Page } from "@playwright/test";

// Task C6：系统定时任务节点页的「调试」弹窗把原先四套触发输入（手写 IntervalTab +
// 停更的 vue3-cron-plus Quartz 选择器 + 日期选择器 + 立即）统一成 TriggerEditor。
//
// 本用例锁住「统一后的前端契约」：
// 1. 四种触发类型（定时 / 间隔 / 单次 / 立即）都能从同一个 TriggerEditor 提交；
// 2. 间隔参数提交的是**新契约的 JSON 字符串**（`{"weeks":0,"days":0,"hours":2,...}`），
//    不再是旧的「秒 分 时 天 周」时长串；
// 3. 触发配置非法（间隔五项全 0）时前端拦截，**不发**调试请求。
//
// 说明：调试接口会真实创建/执行调度作业（立即执行还会真跑一次 handler），
// 故这里用 `page.route` 桩掉 execute 响应，只断言请求体，避免污染调度器状态。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const EXECUTE_ROUTE = "**/api/v1/task/cronjob/node/execute/**";

/** 用例内共用的节点（在 beforeAll 里用接口建好，避免依赖既有数据） */
let nodeName = "";
let nodeId = 0;

test.beforeAll(async ({ request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).data.access_token;

  nodeName = `e2e-trigger-${Date.now()}`;
  const created = await request.post(`${API}/task/cronjob/node/create`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: nodeName,
      code: nodeName.slice(-24),
      jobstore: "default",
      executor: "default",
      func: 'def handler(*args, **kwargs):\n    return "ok"\n',
      coalesce: false,
      max_instances: 1,
    },
  });
  expect(created.ok()).toBeTruthy();
  nodeId = (await created.json()).data.id;
  expect(nodeId).toBeGreaterThan(0);
});

test.afterAll(async ({ request }) => {
  if (!nodeId) return;
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  const token = (await login.json()).data.access_token;
  await request
    .delete(`${API}/task/cronjob/node/delete`, {
      headers: { Authorization: `Bearer ${token}` },
      data: [nodeId],
    })
    .catch(() => {});
});

/** 打开节点页并进入指定节点的「调试」弹窗 */
async function openDebugDialog(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/task/cronjob/node", { waitUntil: "domcontentloaded" });

  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    await tour
      .locator(".el-tour__close")
      .first()
      .evaluate((el) => (el as HTMLElement).click())
      .catch(() => {});
  }

  const row = page.locator(".el-table__row", { hasText: nodeName }).first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.getByRole("button", { name: "调试" }).click();

  const dialog = page.locator(".el-dialog:has-text('调试节点')").first();
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  // TriggerEditor 的四类型按钮是统一入口的标志
  await expect(dialog.locator(".trigger-editor")).toBeVisible();
  return dialog;
}

/** 切换触发类型（TriggerEditor 内的一排按钮） */
async function pickTrigger(dialog: Locator, label: string) {
  await dialog.locator(".trigger-editor .el-radio-button", { hasText: label }).first().click();
}

/** 等一次预览返回，确保「非法拦截」的结论已就绪（组件内防抖 300ms） */
async function waitPreview(page: Page) {
  const res = await page.waitForResponse((r) => r.url().includes("/trigger/preview"), {
    timeout: 15_000,
  });
  return (await res.json()).data as { valid: boolean };
}

/** 点「确认」并捕获调试请求体（若被前端拦截则返回 null） */
async function confirmAndCapture(page: Page) {
  const captured = page
    .waitForRequest((r) => r.method() === "POST" && r.url().includes("/node/execute/"), {
      timeout: 5_000,
    })
    .then((r) => r.postDataJSON())
    .catch(() => null);
  await page
    .locator(".el-dialog:has-text('调试节点')")
    .getByRole("button", { name: "确认" })
    .click();
  return captured;
}

test("定时：默认 5 段 crontab 可直接调试提交", async ({ page }) => {
  await page.route(EXECUTE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 200, msg: "调试节点成功", data: { job_id: nodeId } }),
    })
  );

  const dialog = await openDebugDialog(page);
  await pickTrigger(dialog, "定时");

  const preview = await waitPreview(page);
  expect(preview.valid).toBeTruthy();

  const body = await confirmAndCapture(page);
  expect(body).not.toBeNull();
  expect(body.trigger).toBe("cron");
  // 5 段标准 crontab（不再是 vue3-cron-plus 的 6/7 段 Quartz 串）
  expect(String(body.trigger_args).split(/\s+/)).toHaveLength(5);
  await expect(dialog).toBeHidden({ timeout: 10_000 });
});

test("间隔：参数提交为新契约 JSON 字符串", async ({ page }) => {
  await page.route(EXECUTE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 200, msg: "调试节点成功", data: { job_id: nodeId } }),
    })
  );

  const dialog = await openDebugDialog(page);
  await pickTrigger(dialog, "间隔");

  // 切过去即五项全 0 → 预览判非法 → 前端拦截，不发调试请求
  const invalidPreview = await waitPreview(page);
  expect(invalidPreview.valid).toBeFalsy();
  expect(await confirmAndCapture(page)).toBeNull();
  await expect(dialog).toBeVisible();

  // 填「时 = 2」后变为合法，可提交
  const hourItem = dialog.locator(".trigger-editor__interval-item", { hasText: "时" }).first();
  await hourItem.locator("input").fill("2");
  await hourItem.locator("input").press("Tab");

  const validPreview = await waitPreview(page);
  expect(validPreview.valid).toBeTruthy();

  const body = await confirmAndCapture(page);
  expect(body).not.toBeNull();
  expect(body.trigger).toBe("interval");
  // 新契约：JSON 字符串（旧契约是「秒 分 时 天 周」时长串）
  const args = JSON.parse(String(body.trigger_args));
  expect(args.hours).toBe(2);
  expect(args.weeks ?? 0).toBe(0);
  expect(String(body.trigger_args)).not.toMatch(/^\d+\s+\d+\s+\d+\s+\d+\s+\d+$/);
  await expect(dialog).toBeHidden({ timeout: 10_000 });
});

test("单次：选定时间后可调试提交", async ({ page }) => {
  await page.route(EXECUTE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 200, msg: "调试节点成功", data: { job_id: nodeId } }),
    })
  );

  const dialog = await openDebugDialog(page);
  await pickTrigger(dialog, "单次");

  const input = dialog.locator(".trigger-editor .el-date-editor input").first();
  await input.click();
  await input.fill("2030-01-01 09:00:00");
  await input.press("Enter");

  const preview = await waitPreview(page);
  expect(preview.valid).toBeTruthy();

  const body = await confirmAndCapture(page);
  expect(body).not.toBeNull();
  expect(body.trigger).toBe("date");
  expect(body.trigger_args).toBe("2030-01-01 09:00:00");
  await expect(dialog).toBeHidden({ timeout: 10_000 });
});

test("立即：无参数直接调试提交", async ({ page }) => {
  await page.route(EXECUTE_ROUTE, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: 200, msg: "调试节点成功", data: { job_id: nodeId } }),
    })
  );

  const dialog = await openDebugDialog(page);
  await pickTrigger(dialog, "立即");

  const body = await confirmAndCapture(page);
  expect(body).not.toBeNull();
  expect(body.trigger).toBe("now");
  expect(body.trigger_args ?? null).toBeNull();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
});
