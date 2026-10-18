// 训练「定时训练」面板改用统一 TriggerEditor 后的回归用例（Task C5）。
//
// 覆盖点：
// 1. 裸 cron 输入框与停更的 vue3-cron-plus 可视化弹窗已不在表单里（换成 .trigger-editor）；
// 2. 「间隔」分支：填 2 小时 → 预览区显示后端统一层产出的「每 2 小时」（描述由后端给，前端不自算）；
// 3. 保存后列表出现该计划，触发方式列显示「间隔」并带「下次运行」；
// 4. 「定时」分支：默认表达式经统一层规范化后可保存，列表回显触发方式与表达式/描述；
// 5. 删除走二次确认（ElMessageBox），并顺带清理本用例造的数据。
//
// 说明：训练列表接口当前只返回 trigger / trigger_args / next_run_time / needs_review（无 describe），
// 故列表断言对「人话描述」与「trigger_args 原样」两种展示都放行（见 SchedulePanel.triggerDesc 的兜底）。
import { test, expect, type Locator, type Page, type APIRequestContext } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

/** 关闭可能遮挡点击的新手引导 Tour（不用 Escape，避免误关自动打开的弹窗）。
 *  注：`components/Guide/index.vue` 是 `:show-close="false"` ⇒ `.el-tour__close` 永不渲染
 *  （C5 审查 Minor 4，原实现是死代码）。故以「导航前预置 guideVisible/showGuide」为主，DOM 移除兜底。 */
async function dismissTour(page: Page) {
  const tour = page.locator(".el-tour");
  if (!(await tour.count())) return;
  const close = page.locator(".el-tour__close").first();
  if (await close.count()) await close.click({ force: true }).catch(() => {});
  if (await tour.count()) {
    await page.evaluate(() =>
      document.querySelectorAll(".el-tour").forEach((el) => el.remove())
    );
  }
}

/** 建一个数据集：训练计划必须绑数据集，确保下拉里一定有可选项目。 */
async function createDataset(request: APIRequestContext) {
  const auth = await login(request);
  const name = `sched-${Date.now()}`;
  const res = await request.post(`${API}/annotation/dataset/create`, {
    data: { name },
    headers: auth,
  });
  expect(res.ok()).toBeTruthy();
  return { id: (await res.json()).data.id as number, name };
}

/** 进入训练页 → 定时训练 Tab → 打开「新建定时计划」弹窗。 */
async function openScheduleDialog(page: Page) {
  // 引导遮罩（`.el-tour`）会拦截指针事件，而 `components/Guide/index.vue` 是 `:show-close="false"`
  // ⇒ 遮罩上没有关闭按钮（C5 审查 Minor 4）。正解：**导航前**预置开关，让引导根本不渲染。
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/train/task", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await dismissTour(page);
  await page
    .locator(".el-tabs__item:has-text('定时训练')")
    .first()
    .evaluate((el) => (el as HTMLElement).click());
  const btn = page.getByRole("button", { name: "新建定时计划" });
  await btn.waitFor({ state: "visible", timeout: 10_000 });
  await btn.click();
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

/** 填计划名 + 选数据集（优先选本用例新建的那个）。 */
async function fillNameAndDataset(
  page: Page,
  dialog: Locator,
  name: string,
  preferredDataset: string
) {
  await dialog.getByPlaceholder("如：每晚 2 点训练").fill(name);
  await dialog
    .locator(".el-form-item")
    .filter({ hasText: "数据集" })
    .locator(".el-select__wrapper")
    .click();
  const options = page.locator(".el-select-dropdown:visible .el-select-dropdown__item");
  await options.first().waitFor({ state: "visible", timeout: 10_000 });
  const preferred = options.filter({ hasText: preferredDataset }).first();
  // 数据集列表默认按 id 升序分页，数据量大时新建项可能不在第一页：退而选任一数据集
  // （本用例只验证触发方式与保存链路，不依赖具体数据集）
  const target = (await preferred.count()) > 0 ? preferred : options.first();
  await target.click();
}

/** 删除本用例造的计划行（走二次确认），顺带验证删除必须确认。 */
async function deleteRow(page: Page, name: string) {
  const row = page.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  await row.getByRole("button", { name: "删除" }).click();
  const box = page.locator(".el-message-box");
  await expect(box).toBeVisible();
  await expect(box).toContainText(name);
  await box.getByRole("button", { name: "删除" }).click();
  await expect(page.locator(".el-table__row").filter({ hasText: name })).toHaveCount(0);
}

test("定时训练：间隔触发（每 2 小时）预览与保存后列表回显", async ({ page, request }) => {
  const dataset = await createDataset(request);
  const name = `e2e-训练调度-${Date.now()}`;

  const dialog = await openScheduleDialog(page);
  // 统一组件已就位；旧的裸 cron 输入与 vue3-cron-plus 可视化弹窗都不应再出现
  await expect(dialog.locator(".trigger-editor")).toBeVisible();
  await expect(dialog.getByText("cron 表达式")).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "可视化" })).toHaveCount(0);

  await fillNameAndDataset(page, dialog, name, dataset.name);

  // 切「间隔」→ 时 = 2 → 预览区（后端统一层产出）显示「每 2 小时」
  await dialog.locator(".el-radio-button").filter({ hasText: "间隔" }).click();
  const hours = dialog.locator(".trigger-editor__interval-item").nth(2).locator("input");
  await hours.fill("2");
  await hours.press("Enter");
  await expect(dialog.locator(".trigger-editor__preview")).toContainText("每 2 小时", {
    timeout: 15_000,
  });

  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const row = page.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  await expect(row).toContainText("间隔");
  await expect(row).toContainText("下次运行");
  // 人话描述（后端下发时）或 trigger_args 原样兜底，两者取其一
  await expect(row).toHaveText(/每 2 小时|"hours":\s*2/);

  await page.screenshot({ path: "e2e/trigger-train.png" });
  await deleteRow(page, name);
});

test("定时训练：定时触发默认表达式可保存并回显触发方式", async ({ page, request }) => {
  const dataset = await createDataset(request);
  const name = `e2e-训练cron-${Date.now()}`;

  const dialog = await openScheduleDialog(page);
  await fillNameAndDataset(page, dialog, name, dataset.name);

  // 空值由统一组件规范化（0 9 * * *），描述来自后端统一层
  await expect(dialog.locator(".trigger-editor__preview")).toContainText("每天 09:00", {
    timeout: 15_000,
  });

  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  const row = page.locator(".el-table__row").filter({ hasText: name }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  await expect(row).toContainText("定时");
  await expect(row).toHaveText(/0 9 \* \* \*|每天 09:00/);

  await deleteRow(page, name);
});
