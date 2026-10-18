import { test, expect, type Page } from "@playwright/test";

// 回归护栏：工作流「定时调度」面板改用统一 TriggerEditor 后的端到端行为。
//
// 关注四件事：
//   ① 打开面板即回显统一触发配置（空值规范化默认「每天 09:00」= `0 9 * * *`，与存量一致）；
//   ② 保存体走新契约（`trigger` / `trigger_args`），并保留 `cron` 兼容字段；
//   ③ 选择器改动真的进入保存体（不是「只有默认值能存」）；
//   ④ 关闭后重开，回显来自后端读回而不是内存里的草稿。
//
// 说明：本用例**不开启**「启用」开关 —— 打开会在真实调度器里注册作业，
// 用例结束后作业仍会按时触发；保存动作本身（写入 + 回读）已足够覆盖本次改动。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

/** 关掉引导蒙层（会盖住卡片操作区，与既有 e2e 保持一致） */
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
}

/** 取登录令牌：后端是 Bearer 鉴权（不是 Cookie），接口调用必须显式带 Authorization */
async function authHeaders(page: Page): Promise<Record<string, string>> {
  const token = await page.evaluate(() => {
    const raw = localStorage.getItem("access_token");
    return raw ? (JSON.parse(raw) as string) : "";
  });
  return { Authorization: `Bearer ${token}` };
}

async function readSchedule(page: Page, headers: Record<string, string>, id: number) {
  const res = await page.request.get(`${API}/ai/workflows/${id}/schedule`, { headers });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).data as {
    trigger: string;
    trigger_args: unknown;
    cron: string;
    enabled: boolean;
    next_run_time: string | null;
  };
}

/**
 * 在 cron 选择器里把某个字段改为指定值 —— **已删除**。
 *
 * 原实现依赖 `@vue-js-cron/element-plus` 的**内部类名**（`.vcron-el-spacer .custom-select`、
 * `.vcron-el-col`）与「下拉不自动收起」等实现细节，首跑即失配（C4 审查 Minor 2）。
 * 现在改配置→保存体的验证改用「间隔」分支（`.trigger-editor__interval-item` 是本项目
 * 自己的 DOM，见用例第 ③ 步），不再耦合第三方内部结构。
 */

test("工作流定时调度：TriggerEditor 回显每天 09:00，保存后统一字段为 0 9 * * *", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 25_000 });
  await dismissTour(page);

  const headers = await authHeaders(page);
  // 通过接口建一个专用工作流：不依赖既有数据（如 `ccc`），名字唯一便于搜索定位卡片
  const name = `e2e-调度-${Date.now()}`;
  const created = await page.request.post(`${API}/ai/workflows/create`, {
    headers,
    data: { name, enabled: true },
  });
  expect(created.ok()).toBeTruthy();
  const workflowId = ((await created.json()).data as { id: number }).id;

  try {
    // 重新载入，让新工作流进入工作台聚合列表
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 25_000 });
    await dismissTour(page);

    await page.getByRole("tab", { name: "工作流" }).first().click();
    await page.getByPlaceholder("搜索条目").fill(name);
    const card = page.locator(".ws-card", { hasText: name }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    await card.locator(".ws-card__actions .el-dropdown").first().click();
    await page.locator(".el-dropdown-menu__item", { hasText: "编辑" }).first().click();

    // 工作流编辑器（抽屉）工具栏里的「计划」= 定时调度面板入口
    const planBtn = page.getByRole("button", { name: /^计划$/ }).first();
    await expect(planBtn).toBeVisible({ timeout: 20_000 });
    await planBtn.click();

    const dialog = page.locator(".el-dialog", { hasText: "定时调度" }).first();
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    const editor = dialog.locator(".trigger-editor");
    await expect(editor).toBeVisible();

    // ① 默认即「每天 09:00」：描述来自后端预览接口（前端不自算），
    //    选择器各段则回显 0 / 9 / 每天 / 每月 —— 即 `0 9 * * *` 的可视形态。
    await expect(editor).toContainText("每天 09:00", { timeout: 15_000 });
    await expect(editor).toContainText("每天");
    await expect(editor).toContainText("每月");
    // 注：不再断言选择器内部 DOM（`@vue-js-cron/element-plus` 的类名/按钮结构属第三方内部实现，
    // 首跑即失配）。回显由上面的文案断言 + 下面的接口回读共同锁定，这才是契约本身。

    // ② 保存 → 回读统一字段（原始表达式断言走接口：选择器 UI 不回显裸字符串）
    await dialog.getByRole("button", { name: "保存" }).click();
    await expect(
      page.locator(".el-message--success", { hasText: "调度已保存" }).first()
    ).toBeVisible({ timeout: 15_000 });
    await expect
      .poll(async () => (await readSchedule(page, headers, workflowId)).trigger_args, {
        timeout: 15_000,
      })
      .toBe("0 9 * * *");
    const saved = await readSchedule(page, headers, workflowId);
    expect(saved.trigger).toBe("cron");
    expect(saved.cron).toBe("0 9 * * *"); // 兼容字段与统一字段同值
    expect(saved.enabled).toBe(false);

    // ③ 选择器改动进入保存体：改用「间隔」分支验证（它是**我们自己的 DOM**），
    //    不再驱动第三方 cron 组件的内部结构（`.vcron-el-col` 一类类名属库实现细节，
    //    首跑即失配，见 C4 审查 Minor 2）。契约本身不变：改配置 → 预览变 → 保存体变。
    await dialog.locator(".el-radio-button").filter({ hasText: "间隔" }).first().click();
    const hourInput = dialog
      .locator(".trigger-editor__interval-item")
      .filter({ hasText: "时" })
      .first()
      .locator("input");
    await hourInput.fill("2");
    await hourInput.press("Tab");
    await expect(editor).toContainText("每 2 小时", { timeout: 15_000 });
    await dialog.getByRole("button", { name: "保存" }).click();
    await expect(
      page.locator(".el-message--success", { hasText: "调度已保存" }).first()
    ).toBeVisible({ timeout: 15_000 });
    await expect
      .poll(async () => (await readSchedule(page, headers, workflowId)).trigger, {
        timeout: 15_000,
      })
      .toBe("interval");
    const savedInterval = await readSchedule(page, headers, workflowId);
    expect(savedInterval.trigger_args).toMatchObject({ hours: 2 });
    // 兼容字段在非 cron 类型必须为空（旧前端不会把 interval 误读成 cron）
    expect(savedInterval.cron).toBe("");

    await page.screenshot({ path: "e2e/trigger-workflow.png", fullPage: false });

    // ④ 关掉重开：回显来自后端读回（不是内存残留）
    // 「关闭」按钮在弹窗里不止一个（面板本身 + 抽屉/弹窗框架），用 `.first()` 明确取第一个
    await dialog.getByRole("button", { name: "关闭" }).first().click();
    await dialog.waitFor({ state: "hidden", timeout: 10_000 }).catch(() => {});
    await planBtn.click();
    const reopened = page.locator(".el-dialog", { hasText: "定时调度" }).first();
    await expect(reopened).toBeVisible({ timeout: 10_000 });
    // 上一步保存的是「每 2 小时」，重开后必须回显它（说明值来自后端读回）
    await expect(reopened.locator(".trigger-editor")).toContainText("每 2 小时", {
      timeout: 15_000,
    });
    await reopened.getByRole("button", { name: "关闭" }).first().click();
  } finally {
    // 清场：先清空调度（避免留一行无主调度），再删除本次专用工作流
    await page.request
      .put(`${API}/ai/workflows/${workflowId}/schedule`, {
        headers,
        data: { cron: "", enabled: false },
      })
      .catch(() => {});
    await page.request
      .delete(`${API}/ai/workflows/delete`, { headers, data: [workflowId] })
      .catch(() => {});
  }
});
