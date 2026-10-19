// 无代码应用 Workshop：运行视图的「表格 / 看板 / 表单」形态切换。
//
// 这条用例是"活系统验证"的一部分：本次只改了**类型标注**（RUN_VIEWS 用 as const、
// viewTag 返回联合类型、filteredRunCols 标成 computed<string[]>），
// 但仍然建一个应用、打开运行视图、点一遍三种形态，确认渲染与切换没坏。
// 跑完会把建的应用删掉，不留垃圾数据。
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";

test("工作台运行视图：三种形态开关可渲染可切换", async ({ page, request }) => {
  await login(request);
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  // 注意是「无代码应用」/ai/workshop（不是 /ai/workspace 工作台）
  await page.goto("/#/ai/workshop", { waitUntil: "domcontentloaded" });

  // ---- 建一个应用，保证能走到运行视图 ----
  const name = `e2e-工作台-${Date.now()}`;
  await page.getByRole("button", { name: "新建应用" }).click();
  const createDrawer = page.locator(".el-drawer", { hasText: "新建对象应用" }).first();
  await expect(createDrawer).toBeVisible({ timeout: 20_000 });
  await createDrawer.locator(".el-form-item", { hasText: "应用名称" }).locator("input").fill(name);
  await createDrawer
    .locator(".el-form-item", { hasText: "业务对象" })
    .locator(".el-select")
    .click();
  const objOption = page.locator(".el-select-dropdown__item").first();
  await expect(objOption).toBeVisible({ timeout: 15_000 });
  await objOption.click();
  await createDrawer.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".el-message--success").first()).toBeVisible({ timeout: 20_000 });

  // ---- 打开运行视图，验证三种形态开关 ----
  const card = page.locator(".ws-app-card", { hasText: name }).first();
  await expect(card).toBeVisible({ timeout: 20_000 });
  await card.click();

  const runDrawer = page.locator(".ws-run-drawer").first();
  await expect(runDrawer).toBeVisible({ timeout: 20_000 });
  const items = runDrawer.locator(".ws-run__switch-item");
  await expect(items, "运行视图应有「表格/看板/表单」三种形态开关").toHaveCount(3, {
    timeout: 20_000,
  });
  await expect(items.nth(0)).toHaveClass(/is-active/);
  await expect(runDrawer.locator(".ws-run__table")).toBeVisible();

  await items.nth(1).click();
  await expect(items.nth(1), "点第 2 个形态应切换过去").toHaveClass(/is-active/);
  await expect(runDrawer.locator(".ws-run__kanban")).toBeVisible();

  await items.nth(2).click();
  await expect(items.nth(2)).toHaveClass(/is-active/);
  await expect(runDrawer.locator(".ws-run__form")).toBeVisible();

  await page.screenshot({ path: "e2e/workshop-run-views.png" });
  await runDrawer.locator(".el-drawer__close-btn").first().click();

  // ---- 清理：删掉刚建的应用（走 API，避免下拉 popper 多份 DOM 导致 UI 点击不稳）----
  const headers = await login(request);
  const list = await (await request.get(`${API}/ai/query/workshop/list`, { headers })).json();
  const mine = ((list.data || []) as any[]).find((a) => a.name === name);
  expect(mine, "清理前应能从列表找到刚建的应用").toBeTruthy();
  const del = await request.delete(`${API}/ai/query/workshop/delete`, {
    headers,
    data: { id: mine.id },
  });
  if (!del.ok()) {
    console.log("DELETE resp:", del.status(), await del.text());
  }
  expect(del.ok(), "删除接口应成功").toBeTruthy();
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".ws-app-card", { hasText: name }), "删掉后卡片应消失").toHaveCount(0, {
    timeout: 20_000,
  });
});
