import { test, expect, type Page } from "@playwright/test";

// 回归护栏：工作流运行的「停止」能力 + 轨迹合并显示。
// 两个用例分开写：取消用例只断言取消相关 UI/DB；轨迹合并用「正常跑完」判定，
// 避免把两件事耦合在一起变成时序抽奖（实测踩过：等轨迹出现再点停止，运行已结束）。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  const appeared = await tour
    .waitFor({ state: "visible", timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) return;
  const skip = tour.getByRole("button", { name: "跳过" }).first();
  const close = tour.locator(".el-tour__close").first();
  const target = (await skip.count()) ? skip : close;
  if (await target.count()) {
    await target.evaluate((el) => (el as HTMLElement).click()).catch(() => {});
  }
  await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  await page
    .evaluate(() => {
      document.querySelectorAll(".el-tour").forEach((el) => el.remove());
    })
    .catch(() => {});
}

/** 打开工作台里 ccc 的内嵌编辑器，并进入运行抽屉。 */
async function openRunDrawer(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 20_000 });
  await dismissTour(page);

  await page.getByRole("tab", { name: "工作流" }).first().click();
  const card = page.locator(".ws-card", { hasText: "ccc" }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.locator(".ws-card__actions .el-dropdown").first().click();
  await page.locator(".el-dropdown-menu__item", { hasText: "编辑" }).first().click();

  const runBtn = page.getByRole("button", { name: /^运行$/ }).first();
  await expect(runBtn).toBeVisible({ timeout: 20_000 });
  await runBtn.click();
  await expect(page.getByPlaceholder(/输入消息/).first()).toBeVisible({ timeout: 15_000 });
}

/** 发送一条消息（要求长输出，给「停止」留出可中断窗口）。 */
async function sendLongPrompt(page: Page, text: string) {
  await page.getByPlaceholder(/输入消息/).first().fill(text);
  await page.getByRole("button", { name: /^发送$/ }).first().click();
}

test("工作流运行可停止：停止按钮 → 二次确认 → 已取消", async ({ page }) => {
  await openRunDrawer(page);
  await sendLongPrompt(page, "请分 10 段、每段不少于 100 字，详细介绍你自己，逐段输出，不要省略。");

  // 运行中：停止按钮出现（未运行时不存在）
  const stop = page.getByRole("button", { name: /^停止$/ }).first();
  await expect(stop).toBeVisible({ timeout: 25_000 });
  await page.screenshot({ path: "e2e/wf-cancel-1-running.png", fullPage: false });

  // 点击停止 → 必须弹二次确认
  await stop.click();
  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await expect(box).toContainText("已取消");
  await page.screenshot({ path: "e2e/wf-cancel-2-confirm.png", fullPage: false });

  await box.getByRole("button", { name: "停止运行" }).click();
  await box.waitFor({ state: "hidden", timeout: 10_000 }).catch(() => {});

  // 中断后显示「已取消」（不是「运行失败」）
  await expect(page.locator(".chat-msg__cancel").first()).toBeVisible({ timeout: 40_000 });
  await expect(page.locator(".chat-msg__err").first()).toHaveCount(0);

  // 轨迹也不应出现重复行：前端本地标「已取消」+ 服务端补发终态，容易撞出两行
  const cancelledLabels = await page
    .locator(".chat-trace .trace-item__label")
    .allInnerTexts();
  expect(cancelledLabels.length).toBeGreaterThan(0);
  expect(new Set(cancelledLabels).size).toBe(cancelledLabels.length);

  await page.screenshot({ path: "e2e/wf-cancel-3-cancelled.png", fullPage: false });

  // 后端记录应落成 cancelled（直接查运行历史接口核对）
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem("access_token");
    return raw ? (JSON.parse(raw) as string) : "";
  });
  const res = await page.request.get(`${API}/ai/workflows/1/run-logs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.ok()).toBeTruthy();
  const logs = (await res.json()).data as Array<{ id: number; status: string }>;
  // 必须核对**最新一条**：只查"存在 cancelled"会被历史记录蒙混过关（实测踩过——
  // 取消请求根本没发出去，测试却因旧记录里有 cancelled 而通过）
  expect(logs.length).toBeGreaterThan(0);
  expect(logs[0].status).toBe("cancelled");
});

test("流式不被缓冲：运行中即可看到「执行中」节点与增量内容", async ({ page }) => {
  await openRunDrawer(page);
  await sendLongPrompt(page, "请分 10 段、每段不少于 100 字，详细介绍你自己，逐段输出，不要省略。");

  const stop = page.getByRole("button", { name: /^停止$/ }).first();
  await expect(stop).toBeVisible({ timeout: 25_000 });

  // 关键断言：**运行尚未结束**时就能看到「执行中」的节点轨迹行。
  // 若 SSE 被 GZip 缓冲（缺 Content-Encoding: identity），帧会在流结束时才一次性到达，
  // 此处必然超时失败——这就是「流式被缓冲」的浏览器侧回归护栏。
  const runningRow = page.locator(".chat-trace .trace-item__status", { hasText: "执行中" });
  await expect(runningRow).toBeVisible({ timeout: 20_000 });
  // 双保险：此刻仍在运行（停止按钮还在），排除"结束后才到"恰好满足上一条
  await expect(stop).toBeVisible();

  await page.screenshot({ path: "e2e/wf-streaming-inflight.png", fullPage: false });

  // 收尾：停掉本次运行，避免留下长跑
  await stop.click();
  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await box.getByRole("button", { name: "停止运行" }).click();
  await box.waitFor({ state: "hidden", timeout: 10_000 }).catch(() => {});
  await expect(page.locator(".chat-msg__cancel").first()).toBeVisible({ timeout: 40_000 });
});

test("运行轨迹合并：同一节点只占一行，不留「执行中」", async ({ page }) => {
  await openRunDrawer(page);
  await sendLongPrompt(page, "用一句话说明什么是工作流。");

  // 等这次运行**结束**（轨迹行渲染出终态即完成信号）
  const trace = page.locator(".chat-trace .trace-item");
  await expect(trace.first()).toBeVisible({ timeout: 90_000 });

  const labels = await trace.locator(".trace-item__label").allInnerTexts();
  expect(labels.length).toBeGreaterThan(0);
  // 同一节点不应出现「执行中」+「终态」两行（本工作流是线性图；循环/迭代才允许重复）
  expect(new Set(labels).size).toBe(labels.length);
  await expect(
    page.locator(".chat-trace .trace-item__status", { hasText: "执行中" })
  ).toHaveCount(0);
});

test("关页面（断开连接）后服务端停止运行并记「已取消」", async ({ page }) => {
  await openRunDrawer(page);

  const token = await page.evaluate(() => {
    const raw = localStorage.getItem("access_token");
    return raw ? (JSON.parse(raw) as string) : "";
  });
  const auth = { Authorization: `Bearer ${token}` };
  const listRuns = async () => {
    const res = await page.request.get(`${API}/ai/workflows/1/run-logs`, { headers: auth });
    return ((await res.json()).data as Array<{ id: number; status: string }>) ?? [];
  };
  // 先记下当前最大运行记录 id：本次运行必然是更大的 id。
  // （不要直接读 logs[0]——「停止」按钮在运行记录落库前就已显示，
  //   此时读到的可能是上一条记录，断言会假失败。）
  const prevMaxId = Math.max(0, ...(await listRuns()).map((r) => r.id));

  await sendLongPrompt(page, "请分 10 段、每段不少于 100 字，详细介绍你自己，逐段输出，不要省略。");

  let runId = 0;
  await expect
    .poll(async () => {
      const row = (await listRuns()).find((r) => r.id > prevMaxId);
      runId = row?.id ?? 0;
      return row?.status;
    }, { timeout: 20_000, intervals: [500] })
    .toBe("running");
  const stop = page.getByRole("button", { name: /^停止$/ }).first();
  await expect(stop).toBeVisible({ timeout: 15_000 });

  // 模拟「关掉页面 / 关掉标签」：导航离开会中断在途 SSE。
  // 服务端必须**自己**发现断开并把运行停掉——此前它收不到断开通知（BaseHTTPMiddleware
  // 不透传 http.disconnect），会白跑到底、记录一直卡在 running。
  await page.goto("about:blank");

  await expect
    .poll(async () => (await listRuns()).find((r) => r.id === runId)?.status, {
      timeout: 40_000,
      intervals: [1_000],
    })
    .toBe("cancelled");
});
