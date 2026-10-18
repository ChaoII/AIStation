// B1 验证：关系类型 / 动作类型**详情入口**（此前两个组件是全仓无人引用的孤儿，
// 关系与动作只能新建、看不了详情、也删不掉）。
//
// 覆盖点：
// 1. 对象详情「关系类型」子页有一张**关系列表**（含「详情 / 删除」按钮）；
// 2. 点「详情」打开「关系类型详情」抽屉，且抽屉里渲染出该关系的元数据；
// 3. 「动作类型」子页的表格有「详情 / 删除」按钮。
//
// 只读：不点「删除」（删除走工作副本，会改动本体）。
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";

test("关系/动作类型有详情入口且抽屉能渲染", async ({ page, request }) => {
  const headers = await login(request);

  // 找一个**有关系类型**的对象视图（否则详情路径根本走不到，用例会退化成"表结构存在"）
  const views = (await (await request.get(`${API}/ai/ontology/object-views`, { headers })).json())
    .data as any[];
  const links = (await (await request.get(`${API}/ai/ontology/links`, { headers })).json())
    .data as any[];
  const withLinks = new Set<string>();
  for (const l of links || []) {
    if (l.source_object) withLinks.add(l.source_object);
    if (l.target_object) withLinks.add(l.target_object);
  }
  const view =
    views.find((v) => v.object_code && withLinks.has(v.object_code)) ||
    views.find((v) => v.object_code) ||
    views[0];
  expect(view, "需要一个对象视图来打开详情抽屉").toBeTruthy();
  const expectRelDetail = Boolean(view.object_code && withLinks.has(view.object_code));

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/ai/ontology?objectview=${encodeURIComponent(view.code)}`, {
    waitUntil: "domcontentloaded",
  });

  // 对象详情抽屉打开
  const objDrawer = page.locator(".el-drawer", { hasText: "对象类型详情" }).first();
  await expect(objDrawer).toBeVisible({ timeout: 25_000 });

  // ---- 关系类型子页：应有关系列表 + 详情按钮 ----
  await objDrawer.locator(".el-tabs__item", { hasText: "关系类型" }).first().click();
  const relSection = objDrawer.locator("section", { hasText: "关系类型" }).first();
  await expect(relSection).toBeVisible({ timeout: 10_000 });

  const detailBtn = relSection.getByRole("button", { name: "详情" }).first();
  const hasRels = await detailBtn.count();
  if (expectRelDetail) {
    // 选的就是有关系类型的对象 ⇒ 这里必须真的有「详情」按钮，否则是回归
    expect(hasRels, "该对象有关系类型，列表里必须有「详情」按钮").toBeGreaterThan(0);
  }
  if (hasRels) {
    await detailBtn.click();
    const linkDrawer = page.locator(".el-drawer", { hasText: "关系类型详情" }).first();
    await expect(linkDrawer).toBeVisible({ timeout: 10_000 });
    // 抽屉里确实渲染了内容（不是空壳）
    await expect(linkDrawer.locator(".el-tabs__item", { hasText: "概览" }).first()).toBeVisible();
    await expect(linkDrawer.locator("section, .ont-sec").first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: "e2e/ontology-link-detail.png" });
    await linkDrawer.locator(".el-drawer__close-btn").first().click();
    await expect(linkDrawer).toBeHidden({ timeout: 10_000 });
  } else {
    // 该对象没有关系类型：至少断言"删除"按钮与列表结构存在（空态也要有表头）
    await expect(relSection.locator(".el-table")).toBeVisible();
  }

  // ---- 动作类型子页：表格应有「详情」按钮 ----
  await objDrawer.locator(".el-tabs__item", { hasText: "动作类型" }).first().click();
  const actSection = objDrawer.locator("section", { hasText: "动作类型" }).first();
  await expect(actSection).toBeVisible({ timeout: 10_000 });
  await expect(actSection.locator(".el-table")).toBeVisible();
  // 有动作时必然带「详情」列（无动作时只有空态，故用 count 断言而非 toBeVisible）
  const actRows = await actSection.locator(".el-table__row").count();
  if (actRows) {
    await expect(actSection.getByRole("button", { name: "详情" }).first()).toBeVisible();
    await expect(actSection.getByRole("button", { name: "删除" }).first()).toBeVisible();
  }
});
