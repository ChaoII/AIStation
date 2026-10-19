// 版本能力接线验证：版本历史面板此前只有「恢复」，而「发布新版本 / 对比 / 回滚」
// 三个后端能力（/version/publish、/version/diff、/version/rollback）在前端封装了却无人调用，
// 用户根本用不到。本用例验证这三处入口真的接上了。
//
// 覆盖点：
// 1. 对象详情「版本历史」子页有「发布新版本」按钮，点击后能真的发布并给出反馈；
// 2. 版本列表每行有「对比 / 恢复 / 回滚」三个操作；
// 3. 点「对比」能打开版本对比对话框（渲染差异或"无差异"空态，而不是打不开）。
//
// 注意：会真的发布一个版本（这正是被测能力），但**不点回滚**（回滚会直接覆盖当前定义）。
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";

test("版本历史面板：发布新版本 + 版本对比入口可用", async ({ page, request }) => {
  const headers = await login(request);

  const views = (await (await request.get(`${API}/ai/ontology/object-views`, { headers })).json())
    .data as any[];
  const view = views.find((v) => v.object_code) || views[0];
  expect(view, "需要一个对象视图来打开详情抽屉").toBeTruthy();

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/ai/ontology?objectview=${encodeURIComponent(view.code)}`, {
    waitUntil: "domcontentloaded",
  });

  const objDrawer = page.locator(".el-drawer", { hasText: "对象类型详情" }).first();
  await expect(objDrawer).toBeVisible({ timeout: 25_000 });

  // ---- 版本历史子页 ----
  await objDrawer.locator(".el-tabs__item", { hasText: "版本历史" }).first().click();
  const verSection = objDrawer.locator("section", { hasText: "版本历史" }).first();
  await expect(verSection).toBeVisible({ timeout: 10_000 });

  const publishBtn = verSection.getByRole("button", { name: "发布新版本" });
  await expect(publishBtn, "「发布新版本」入口必须存在（此前该能力无 UI 入口）").toBeVisible();

  // ---- 发布：二次确认 + 结果反馈 ----
  await publishBtn.click();
  const box = page.locator(".el-message-box").first();
  await expect(box).toBeVisible({ timeout: 10_000 });
  await box.getByRole("button", { name: "发布" }).click();
  await expect(
    page.locator(".el-message--success, .el-message--warning").first(),
    "发布后必须给出成功/待审批反馈"
  ).toBeVisible({ timeout: 25_000 });

  // ---- 版本列表：每行三个操作 ----
  const firstRow = verSection.locator(".el-table__row").first();
  await expect(firstRow, "发布后版本列表应有记录").toBeVisible({ timeout: 25_000 });
  for (const label of ["对比", "恢复", "回滚"]) {
    await expect(firstRow.getByRole("button", { name: label }), `行内应有「${label}」`).toBeVisible();
  }

  // ---- 对比对话框能打开并渲染 ----
  await firstRow.getByRole("button", { name: "对比" }).click();
  const diffDlg = page.locator(".el-dialog", { hasText: "版本对比" }).first();
  await expect(diffDlg).toBeVisible({ timeout: 15_000 });
  await expect(
    diffDlg.locator(".el-table, .el-empty").first(),
    "对比对话框必须渲染出差异表或「无差异」空态"
  ).toBeVisible({ timeout: 15_000 });
  // 回归：请求封装返回 axios response（业务数据在 data.data），取错层会退回展示整个响应体 JSON
  await expect(
    diffDlg.locator(".ont-ver__raw"),
    "不应退回展示原始响应 JSON（说明取值层错了）"
  ).toHaveCount(0);
  await expect(
    diffDlg.getByText("该版本与当前定义没有差异").or(diffDlg.locator(".el-table__row").first())
  ).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: "e2e/ontology-version-diff.png" });
  await diffDlg.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(diffDlg).toBeHidden({ timeout: 10_000 });
});
