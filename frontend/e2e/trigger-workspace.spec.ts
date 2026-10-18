import { test, expect, type Page, type Locator } from "@playwright/test";

/**
 * Task C3：AI 工作台「新建定时任务」弹窗改用统一触发组件 `TriggerEditor`
 * （同时覆盖 C2 的四类型 / 实时预览 / 非法拦截）。
 *
 * 断言口径：
 * - 弹窗内「描述 / 下次运行」一律来自后端统一层 `POST /ai/workspace/trigger/preview`，前端不自算；
 * - 列表卡片上的「触发方式 / 描述 / 下次运行 / 需人工确认」来自 `GET /ai/workspace/cron/list`
 *   的 `trigger` / `trigger_args` / `next_run_time` / `needs_review`。
 *
 * ⚠️ 用例 2/3/4（间隔 / 单次 / 立即）依赖后端写入接口接受 `trigger` + `trigger_args`
 * 两个新字段（旧字段 `cron` 仍兼容）。若后端只认 `cron`，这三条会因「请先配置触发时间」而失败——
 * 那是后端契约缺口，不是用例问题，详见 C3 报告「顾虑」。
 */

/** 打开工作台并关掉新手引导（引导浮层会挡住点击） */
async function openWorkspace(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".ai-workspace-page").first()).toBeVisible({ timeout: 25_000 });
  const tour = page.locator(".el-tour");
  if (await tour.count()) {
    await tour
      .locator(".el-tour__close")
      .first()
      .evaluate((el) => (el as HTMLElement).click())
      .catch(() => {});
    await tour.waitFor({ state: "hidden", timeout: 5_000 }).catch(() => {});
  }
}

/** 打开「新建定时任务」弹窗（触发方式区域是 TriggerEditor） */
async function openCronDialog(page: Page): Promise<Locator> {
  await page.locator(".ws-tab-actions").getByRole("button", { name: "新建" }).click();
  await page.locator(".el-dropdown-menu__item", { hasText: "定时任务" }).first().click();
  const dialog = page.locator(".el-dialog").filter({ hasText: "新建定时任务" });
  await expect(dialog).toBeVisible({ timeout: 15_000 });
  await expect(dialog.locator(".trigger-editor")).toBeVisible();
  return dialog;
}

/** 切换触发类型（定时 / 间隔 / 单次 / 立即） */
async function pickTriggerType(dialog: Locator, label: string) {
  await dialog.locator(".el-radio-button", { hasText: label }).first().click();
}

/** 点保存，返回创建请求的响应与请求体（无论成功失败都会发出） */
async function clickSave(page: Page, dialog: Locator) {
  const respP = page.waitForResponse((r) => r.url().includes("/ai/workspace/cron/create"));
  await dialog.getByRole("button", { name: "保存" }).click();
  const resp = await respP;
  return { status: resp.status(), body: resp.request().postDataJSON() as Record<string, unknown> };
}

/** 按名称搜索定位卡片（关键字唯一，避免分页/历史数据干扰） */
async function cronCard(page: Page, name: string): Promise<Locator> {
  await page.getByPlaceholder("搜索条目").fill(name);
  const card = page.locator(".ws-card").filter({ hasText: name }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  return card;
}

/** 明天同一时刻（保证「单次」填的是未来时间） */
function tomorrowText(): string {
  const d = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} 09:00:00`;
}

test("C3-1 定时：默认每天 09:00，预览有描述与下次运行，保存后列表展示触发方式/描述/下次运行", async ({
  page,
}) => {
  const name = `e2e-定时-${Date.now()}`;
  await openWorkspace(page);
  const dialog = await openCronDialog(page);
  const preview = dialog.locator(".trigger-editor__preview");

  await dialog.getByPlaceholder("任务名称").fill(name);
  await dialog.getByPlaceholder("任务描述").fill("C3 e2e 定时任务");

  // 预览两行都来自后端统一层：默认表达式 0 9 * * * → 「每天 09:00」，下次运行非空
  await expect(preview).toContainText("每天 09:00", { timeout: 15_000 });
  await expect(preview).toContainText("下次运行：");
  await expect(preview).not.toContainText("下次运行：—");

  await page.screenshot({ path: "e2e/trigger-workspace.png" });

  const { status, body } = await clickSave(page, dialog);
  // 保存体：新字段（统一层口径）+ 兼容字段 `cron` 同时提交
  expect(status).toBe(200);
  expect(body.trigger).toBe("cron");
  expect(body.trigger_args).toBe("0 9 * * *");
  expect(body.cron).toBe("0 9 * * *");
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const card = await cronCard(page, name);
  await expect(card).toContainText("触发方式");
  await expect(card).toContainText("定时");
  // 描述优先展示后端统一层下发的人话描述（`trigger_describe`，A8 起聚合条目也带），
  // 拿不到时才回退原始 `trigger_args`（见 cronArgsText）
  await expect(card).toContainText("描述：每天 09:00");
  await expect(card).toContainText("下次运行：");
  // 健康行不得被误标「需人工确认」
  await expect(card).not.toContainText("需人工确认");
});

test("C3-2 间隔：切「间隔」先提示非法，填 2 小时后预览含「每 2 小时」，保存成功", async ({
  page,
}) => {
  const name = `e2e-间隔-${Date.now()}`;
  await openWorkspace(page);
  const dialog = await openCronDialog(page);
  const preview = dialog.locator(".trigger-editor__preview");

  await dialog.getByPlaceholder("任务名称").fill(name);
  await pickTriggerType(dialog, "间隔");

  // 五项全 0 → 后端判非法并给出可读原因（组件把 reason 上抛，页面据此拦截保存）
  await expect(preview).toContainText("至少需要一项大于 0", { timeout: 15_000 });

  const hourInput = dialog
    .locator(".trigger-editor__interval-item", { hasText: "时" })
    .first()
    .locator("input");
  await hourInput.fill("2");
  await hourInput.press("Tab");
  await expect(preview).toContainText("每 2 小时", { timeout: 15_000 });

  const { status, body } = await clickSave(page, dialog);
  // 间隔参数按存储契约落 JSON 字符串（后端 TriggerUtil 两种形态都认）
  expect(status).toBe(200);
  expect(body.trigger).toBe("interval");
  const args = JSON.parse(String(body.trigger_args)) as Record<string, number>;
  expect(args.hours).toBe(2);
  expect(args.minutes ?? 0).toBe(0);
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const card = await cronCard(page, name);
  await expect(card).toContainText("触发方式");
  await expect(card).toContainText("间隔");
  await expect(card).toContainText("下次运行：");
});

test("C3-3 单次：选未来时间，预览含该时刻，保存成功", async ({ page }) => {
  const name = `e2e-单次-${Date.now()}`;
  const future = tomorrowText();
  await openWorkspace(page);
  const dialog = await openCronDialog(page);
  const preview = dialog.locator(".trigger-editor__preview");

  await dialog.getByPlaceholder("任务名称").fill(name);
  await pickTriggerType(dialog, "单次");

  const dateInput = dialog.locator(".trigger-editor .el-date-editor input").first();
  await dateInput.click();
  await dateInput.fill(future);
  await dateInput.press("Enter");
  // 描述形如「2027-01-01 09:00 执行一次」（取到分钟即可，秒位不参与断言）
  await expect(preview).toContainText(future.slice(0, 16), { timeout: 15_000 });

  const { status, body } = await clickSave(page, dialog);
  expect(status).toBe(200);
  expect(body.trigger).toBe("date");
  expect(body.trigger_args).toBe(future);
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const card = await cronCard(page, name);
  await expect(card).toContainText("触发方式");
  await expect(card).toContainText("单次");
  await expect(card).toContainText("下次运行：");
});

test("C3-4 立即：切「立即」保存成功，列表触发方式为「立即」", async ({ page }) => {
  const name = `e2e-立即-${Date.now()}`;
  await openWorkspace(page);
  const dialog = await openCronDialog(page);
  const preview = dialog.locator(".trigger-editor__preview");

  await dialog.getByPlaceholder("任务名称").fill(name);
  await pickTriggerType(dialog, "立即");
  await expect(preview).toContainText("保存后立即执行一次", { timeout: 15_000 });

  const { status, body } = await clickSave(page, dialog);
  // 「立即」无参数：trigger_args 为 null，兼容字段 cron 留空
  expect(status).toBe(200);
  expect(body.trigger).toBe("now");
  expect(body.trigger_args ?? null).toBeNull();
  expect(body.cron).toBe("");
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const card = await cronCard(page, name);
  await expect(card).toContainText("触发方式");
  await expect(card).toContainText("立即");
});

test("C3-5 非法：间隔全 0 时提示非法原因且保存被拦截（弹窗不关闭）", async ({ page }) => {
  const name = `e2e-非法-${Date.now()}`;
  const createCalls: string[] = [];
  await openWorkspace(page);
  page.on("request", (r) => {
    if (r.url().includes("/ai/workspace/cron/create")) createCalls.push(r.url());
  });

  const dialog = await openCronDialog(page);
  const preview = dialog.locator(".trigger-editor__preview");

  await dialog.getByPlaceholder("任务名称").fill(name);
  await pickTriggerType(dialog, "间隔");
  // 红色原因文本来自后端统一层（前端不自算）
  await expect(preview).toContainText("至少需要一项大于 0", { timeout: 15_000 });

  await dialog.getByRole("button", { name: "保存" }).click();

  // 拦截：给出可读原因的错误提示，且不发出创建请求、弹窗不关闭
  await expect(page.locator(".el-message--error").last()).toContainText("至少需要一项大于 0", {
    timeout: 10_000,
  });
  await expect(dialog).toBeVisible();
  expect(createCalls).toHaveLength(0);
});
